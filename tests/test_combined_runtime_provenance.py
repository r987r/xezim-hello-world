"""Compare against the checked 312-input source bundle, never infer a DUT PASS."""
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import combined_runtime_provenance as runtime
import ddr_split_workspace as split
from test_identity import bind_filelist, relative_path, selected, validate
from run_workspace import uses_canonical_workspace


class CombinedRuntimeTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="combined-runtime-proof-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        cfg = self.root / "config/soc.yaml"
        cfg.parent.mkdir()
        shutil.copyfile(ROOT / "config/soc.yaml", cfg)
        for n in ("config/interface_contracts.yaml", "config/ip.lock.yaml", "Bender.yml", "Bender.lock",
                  "rtl/memory/ddr4/toolchain.lock.yml"):
            (self.root / n).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / n, self.root / n)
        bundle = self.root / runtime.BUNDLE
        shutil.copytree(ROOT / runtime.BUNDLE, bundle)
        self.catalog = yaml.safe_load((ROOT / "config/regression.yaml").read_text())["tests"]
        definition = self.catalog[runtime.PROFILE]
        self.identity = selected(runtime.PROFILE, definition, root=self.root,
                                 run_id="local-012345abcdef")
        self.out = self.root / ".tools/runs" / relative_path(self.identity)
        self.out.mkdir(parents=True)
        self.prefix = self.out.relative_to(self.root).as_posix() + "/"
        expected = self.expected = json.loads((bundle / "manifest.json").read_text())

        def relocated(name):
            if name == runtime.LEGACY_BRIDGE:
                return self.prefix + runtime.BRIDGE
            if name.startswith(runtime.SOURCE_ROOT):
                return self.prefix + name.removeprefix(runtime.SOURCE_ROOT)
            return name

        altered = {}
        for record in expected["files"].values():
            legacy = record["source"]
            if not legacy.startswith(runtime.SOURCE_ROOT):
                continue
            name = relocated(legacy)
            key = name.removeprefix(self.prefix)
            member = expected["portable_source_map"][legacy]
            raw = (bundle / member).read_bytes()
            for image in runtime.IMAGES.get(key, ()):
                raw = raw.replace((runtime.BUNDLE + "/rtl/" + image).encode(),
                                  (self.prefix + "variant/" + image).encode())
            dst = self.root / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(raw)
            altered[legacy] = runtime.digest(raw)
        generated = {relocated(n): sha for n, sha in altered.items()}
        generated[relocated(runtime.LEGACY_BRIDGE)] = expected["selected_source_sha256"][runtime.LEGACY_BRIDGE]
        actual = {relocated(n): altered.get(n, sha) for n, sha in expected["selected_source_sha256"].items()}
        reverse = {f"{runtime.BUNDLE}/{p}": n for n,p in expected["portable_source_map"].items()}
        self.lines = []
        for line in (bundle / "compiler/sources.f").read_text().splitlines():
            if line.startswith("+define+"):
                self.lines.append(line)
                continue
            include = line.startswith("+incdir+")
            name = line.removeprefix("+incdir+") if include else line
            # Externals are attested by their planned manifest here; this
            # fixture exercises the equivalence projection, not generation.
            prefix = "+incdir+" if include else ""
            actual_path = self.root / relocated(reverse.get(name, name))
            self.lines.append(prefix + str(actual_path))
        raw = ("\n".join(self.lines) + "\n").encode()
        (self.out / "sources.f").write_bytes(raw)
        self.manifest = {
            "profile": runtime.PROFILE,
            "compiled_top": "full_chip_tb",
            "selected_soc_top": self.prefix + "variant/soc_top.sv",
            "source_count": 312,
            "definition_sha256": expected["selection_sha256"],
            "include_headers_sha256": expected["include_headers_sha256"],
            "defines": expected["defines"],
            "args": expected["compiler_args"],
            "network_filelists": expected["network_filelists"],
            "generated_sha256": generated,
            "source_sha256": actual,
            "filelist_sha256": runtime.digest(raw),
            "compiler_input_sha256": "f" * 64,
        }

    def verify(self, value=None):
        return runtime.verify_runtime_inputs(self.root, self.out, value or self.manifest)

    def set_list(self, lines):
        raw = ("\n".join(lines) + "\n").encode()
        (self.out / "sources.f").write_bytes(raw)
        self.manifest["filelist_sha256"] = runtime.digest(raw)

    def test_runtime_and_source_replay_are_distinct_modes(self):
        profile, test = runtime.PROFILE, self.catalog[runtime.PROFILE]
        self.assertFalse(uses_canonical_workspace(profile, test))
        self.assertFalse(uses_canonical_workspace(profile, test, stage="files"))
        for stage in ("all","build","run"):
            self.assertTrue(uses_canonical_workspace(profile, test, stage=stage))
        report = split.plan_report(self.root, self.out, test["report"], target=profile)
        plan = {**test, "report": report, "identity": self.identity, "target": profile}
        self.assertEqual(validate(self.identity, plan=plan), self.identity)
        self.assertEqual(report["axi"]["catalog"], self.prefix + "ddr_noc/supernoc/axi_monitors.json")
        self.assertTrue(test["report"]["axi"]["catalog"].startswith(runtime.SOURCE_ROOT))

    def test_exact_runtime_inputs_match_without_rewriting_actual_hashes(self):
        before = copy.deepcopy(self.manifest)
        proof = self.verify()
        self.assertEqual(self.manifest, before)
        self.assertEqual(proof["source_count"], 312)
        self.assertEqual(proof["actual_filelist_sha256"], before["filelist_sha256"])
        self.assertEqual(proof["portable_compiler_input_sha256"], self.expected["portable_compiler_input_sha256"])

    def test_combined_exact_continuation_binds_equivalence_and_run_selection(self):
        from test_identity import save, sha

        target, definition = runtime.PROFILE, self.catalog[runtime.PROFILE]
        proof = self.verify()
        proof_file = self.out / runtime.PROOF
        proof_file.write_text(json.dumps(proof))
        raw = proof_file.read_bytes()
        identity = bind_filelist(self.identity, (self.out/"sources.f").read_bytes())
        save(self.out/"identity.json", identity)
        command = lambda p: [[target, ["/bin/python", str(p)]]]
        plan = {**definition, "stage": "run", "target": target, "identity": identity,
                "build": str(Path(definition["build"])/identity["run_id"]),
                "results_xml": str(self.out/"results.xml"),
                "report": split.plan_report(self.root,self.out,definition["report"],target=target),
                "commands": command(self.out/"plan.json")}
        (self.out/"plan.json").write_text(json.dumps(plan))
        (self.out/"selected-rtl-manifest.json").write_text(json.dumps(self.manifest))
        for path in (*split.DDR_INPUTS, *split.BUILD_RECORDS):
            f = self.out/path
            if not f.exists():
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text("fixture")
        for path in (*split.PINNED_INPUTS, 'config/selected-rtl-reference/ethernet-ddr-pcie.json',
                     'dv/integration/test_combined.py', 'dv/pcie0/upstream.lock.json',
                     'rtl/io/ethernet0/ip.lock.yml'):
            f = self.root/path
            f.parent.mkdir(parents=True, exist_ok=True)
            if not f.exists():
                f.write_text("fixture")
        exe = self.root/plan["build"]/plan["top"]
        exe.parent.mkdir(parents=True)
        exe.write_text("fixture executable")
        exe.chmod(0o700)
        (exe.parent/"regression-build.json").write_text(json.dumps({
            "binary_sha256": sha(exe.read_bytes()), "signature": "c" * 64}))
        split.seal(self.root,self.out,plan,split.input_snapshot(self.root,self.out,plan))
        use_archive = Mock()
        def resume(token):
            return split.prepare_continuation(self.root,definition,token,
                verify_archive=use_archive, command=command, fingerprint=lambda p:"c"*64,target=target)
        with patch.dict(os.environ):
            os.environ.pop("GITHUB_RUN_ID",None)
            with self.assertRaisesRegex(ValueError,"missing or unsafe"):
                resume("local-111111111111")
            proof_file.write_bytes(raw+b"\n")
            with self.assertRaisesRegex(ValueError,"changed before continuation"):
                resume(identity["run_id"])
            use_archive.assert_not_called()
            self.assertFalse((self.out/split.CLAIM).exists())
            proof_file.write_bytes(raw)
            self.assertEqual(resume(identity["run_id"]), (self.out,identity,plan))
            use_archive.assert_called_once_with(self.root,target,definition,directory=self.out)

    def test_refuses_duplicate_rom_locator_with_recomputed_actual_hashes(self):
        name = "variant/soc_top.sv"
        p = self.out / name
        raw = p.read_bytes() + (self.prefix + "variant/flash.hex").encode()
        p.write_bytes(raw)
        got = runtime.digest(raw)
        self.manifest["generated_sha256"][self.prefix + name] = got
        self.manifest["source_sha256"][self.prefix + name] = got
        with self.assertRaisesRegex(ValueError, "isn't uniquely run-owned"):
            self.verify()

    def test_refuses_actual_source_header_flag_or_definition_drift(self):
        for key, value, why in (
            ("definition_sha256", "0" * 64, "definition"),
            ("include_headers_sha256", {}, "headers"),
            ("args", ["extra-argument"], "flags"),
            ("defines", ["different"], "flags"),
        ):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, why):
                self.verify({**self.manifest, key: value})
        sources = self.manifest["source_sha256"]
        sources[self.prefix + runtime.BRIDGE] = "0" * 64
        with self.assertRaisesRegex(ValueError, "inventory or bytes drifted"):
            self.verify()

    def test_refuses_manifest_or_order_drift_with_all_sources_present(self):
        path = self.root/runtime.BUNDLE/"manifest.json"
        original = path.read_bytes()
        tampered = json.loads(original)
        tampered["files"]["rtl/soc_top.sv"]["generated_sha256"] = "0" * 64
        path.write_text(json.dumps(tampered))
        with self.assertRaisesRegex(ValueError, "digest changed"):
            self.verify()
        path.write_bytes(original)
        lines = self.lines.copy()
        lines[-1],lines[-2] = lines[-2],lines[-1]
        self.set_list(lines)
        with self.assertRaisesRegex(ValueError, "ordered compiler filelist"):
            self.verify()

    def test_refuses_runtime_using_original_replay_path_as_its_source(self):
        sources = self.manifest["source_sha256"]
        sources[runtime.LEGACY_BRIDGE] = sources.pop(self.prefix + runtime.BRIDGE)
        with self.assertRaisesRegex(ValueError, "borrows another run or replay file"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
