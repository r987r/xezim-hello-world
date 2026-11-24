"""Exercise native archive custody without replacing the real PCIe test cases."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

from dv.pcie0 import run_noc_smoke as runner
from tools.test_identity import load, relative_path, sha


ROOT = Path(__file__).resolve().parents[1]
HEAD = "1" * 40
ARCHIVED = {"identity.json", "plan.json", "sources.f", "source-head.txt",
            "pcie-noc-inputs.json", "build.log", "simulation.log", "results.xml"}
XML = (b'<testsuites><testsuite><testcase classname="noc_smoke" '
       b'name="host_to_real_floonoc_tc_sram"/></testsuite></testsuites>')


class PcieNocWorkspaceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        for name in ("config/soc.yaml", "config/interface_contracts.yaml", "config/ip.lock.yaml",
                     "config/regression.yaml", "Bender.lock", "Bender.yml",
                     "rtl/adapters/axi_sram_target.sv", "dv/pcie_link/bar0_noc_translate.sv",
                     "dv/pcie0/pcie_noc_tb.sv", "dv/pcie0/upstream.lock.json",
                     "dv/pcie0/discovery.py", "dv/pcie0/noc_smoke.py",
                     "gen/noc/floonoc/package.sv", "gen/noc/floonoc/top.sv",
                     ".tools/verilog_pcie/rtl/example.v", ".tools/verilog_pcie/tb/pcie_if.py"):
            self.write(name, name.encode())
        self.write("gen/noc/floonoc/manifest.json", json.dumps({"networks": {"pcie0_local_data": {
            "status": "real_upstream_structural_RTL", "package": "package.sv", "top": "top.sv",
        }}}).encode())
        self.model_link = self.root / ".tools/verilog_pcie/tb/pcie_axi_master/pcie_if.py"
        self.model_link.parent.mkdir()
        self.model_link.symlink_to("../pcie_if.py")
        self.base = self.write(".tools/floonoc/base.sv", b"base")
        self.header = self.write(".tools/floonoc/include/axi/test.svh", b"header")
        self.outputs = self.root / "github-output.txt"
        self.use(patch.dict(os.environ, {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "4",
                                         "GITHUB_OUTPUT": str(self.outputs)}))
        self.use(patch.object(runner, "ROOT", self.root))
        self.use(patch.object(runner, "_source_state", return_value=(HEAD, False)))
        self.use(patch.object(runner, "source_contract", return_value={
            "rtl_modules": ["rtl/pcie_axi_master.v", "rtl/example.v"],
            "python_models": ["tb/pcie_axi_master/pcie_if.py"],
        }))
        self.use(patch.object(runner, "assert_iverilog_clean", side_effect=self.normalize))
        self.use(patch.object(runner.regress, "load_config", return_value={}))
        self.use(patch.object(runner.regress, "Resolver", return_value=Mock(sources=Mock(
            return_value=([str(self.base)], [str(self.header.parent.parent)], ["OLD", "MODE=7"])))))
        self.sim = Mock()
        self.sim.build.side_effect = self.sim_build
        self.sim.test.side_effect = self.sim_test
        cocotb = ModuleType("cocotb")
        cocotb.runner = ModuleType("cocotb.runner")
        cocotb.runner.get_runner = Mock(return_value=self.sim)
        self.use(patch.dict("sys.modules", {"cocotb": cocotb, "cocotb.runner": cocotb.runner}))
        self.xml, self.wrong_mode, self.mutate, self.foreign_xml = XML, False, False, False

    def use(self, context):
        context.start()
        self.addCleanup(context.stop)

    def write(self, name, contents):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        return path

    def normalize(self, *, output, probe):
        self.write(output, b"original normalized compiler input")
        self.write(probe, b"private Icarus diagnostic")
        return output

    def sim_build(self, **args):
        self.write(args["build_dir"] / "Vpcie_noc_tb", b"private Verilator product")
        self.write(args["log_file"], b"original build log\n")

    def sim_test(self, **args):
        mode = self.sim.build.call_args.kwargs["parameters"]["BAR0_RELOCATE"]
        self.write(args["log_file"], (
            f"PCIE0_RTL_BAR_RELOCATE_SAMPLED={mode ^ self.wrong_mode} after actual clock evaluation\n"
        ).encode())
        if self.mutate:
            self.header.write_bytes(b"modified while simulator ran")
        path = self.root / "earlier/results.xml" if self.foreign_xml else Path(args["results_xml"])
        return self.write(path, self.xml)

    def folders(self):
        entries = dict(line.split("=", 1) for line in self.outputs.read_text().splitlines())
        return {key: self.root / ".tools/runs" / value for key, value in entries.items()}

    def run_case(self, *, relocate):
        logs = io.StringIO()
        with redirect_stderr(logs), redirect_stdout(logs):
            runner.run(bar_relocate=relocate)
        return logs.getvalue()

    def test_distinct_modes_and_exact_inputs_no_binary_or_claim(self):
        self.assertIn("PCIE0_REAL_NOC_SRAM_REGRESSION_PASS", self.run_case(relocate=False))
        self.assertIn("PCIE0_BAR_RELOCATED_NOC_SRAM_PASS", self.run_case(relocate=True))
        folders = self.folders()
        self.assertEqual(set(folders), {"legacy_canonical_id", "relocated_canonical_id"})
        self.assertNotEqual(*folders.values())
        for index, mode in enumerate(("legacy", "relocated")):
            archive = folders[f"{mode}_canonical_id"]
            target, original = runner.selected_plan(bool(index))
            identity = load(archive / "identity.json", target=target, plan=original)
            self.assertEqual(archive.relative_to(self.root / ".tools/runs"), relative_path(identity))
            self.assertTrue(identity["run_id"].startswith("ci-123-a4-"))
            self.assertEqual(set(p.name for p in archive.iterdir()), ARCHIVED)
            self.assertEqual((archive / "results.xml").read_bytes(), XML)
            self.assertEqual((archive / "build.log").read_bytes(), b"original build log\n")
            self.assertEqual((archive / "source-head.txt").read_text().strip(), HEAD)
            filelist = (archive / "sources.f").read_bytes()
            self.assertEqual(sha(filelist), identity["selection"]["filelist_sha256"])
            build = self.sim.build.call_args_list[index].kwargs
            self.assertEqual(filelist.splitlines(), [
                b"-DCOCOTB_SIM=1", b"--top-module", b"pcie_noc_tb",
                b"--timing", b"--assert", b"-Wno-fatal", b"-DOLD=1", b"-DMODE=7",
                f"-I{self.header.parent.parent}".encode(), f"-GBAR0_RELOCATE={index}".encode(),
                *[p.encode() for p in build["sources"]],
            ])
            inputs = json.loads((archive / "pcie-noc-inputs.json").read_text())
            self.assertEqual(inputs["identity_sha256"], identity["identity_sha256"])
            self.assertEqual(inputs["sha256"][self.header.relative_to(self.root).as_posix()],
                             sha(b"header"))
            self.assertIn(".tools/verilog_pcie/tb/pcie_if.py", inputs["sha256"])
            self.assertTrue((build["build_dir"].parent / "pcie_bridge_check.vvp").is_file())
            self.assertTrue((build["build_dir"] / "Vpcie_noc_tb").is_file())
        self.assertFalse((self.root / ".tools/pcie0/noc_build").exists())

    def test_reject_wrong_or_cross_run_native_xml(self):
        self.foreign_xml = True
        with self.assertRaisesRegex(RuntimeError, "missing Cocotb"):
            self.run_case(relocate=False)
        self.foreign_xml = False
        self.xml = XML.replace(b"host_to_real_floonoc_tc_sram", b"other_case")
        with self.assertRaisesRegex(RuntimeError, "real NoC/SRAM regression failed"):
            self.run_case(relocate=True)

    def test_reject_wrong_sampled_mode_and_mutated_inputs(self):
        self.wrong_mode = True
        with self.assertRaisesRegex(ValueError, "never observed the selected BAR mode"):
            self.run_case(relocate=True)
        self.wrong_mode, self.mutate = False, True
        with self.assertRaisesRegex(ValueError, "selected source changed"):
            self.run_case(relocate=False)

    def test_pinned_cocotb_symlink_cannot_be_retargeted(self):
        self.model_link.unlink()
        self.model_link.symlink_to("../unused.py")
        with self.assertRaisesRegex(ValueError, "pinned PCIe Cocotb model link changed"):
            self.run_case(relocate=False)
        self.assertFalse(self.outputs.exists())

    def test_ci_rejects_dirty_or_missing_attempt_before_preparation(self):
        with patch.object(runner, "_source_state", return_value=(HEAD, True)):
            with self.assertRaisesRegex(ValueError, "clean source and exact attempt"):
                self.run_case(relocate=False)
        del os.environ["GITHUB_RUN_ATTEMPT"]
        with self.assertRaisesRegex(ValueError, "clean source and exact attempt"):
            self.run_case(relocate=False)
        self.assertFalse(self.outputs.exists())


if __name__ == "__main__":
    unittest.main()
