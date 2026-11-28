import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import pcie_prelink_workspace as prelink, test_identity as identity


class PrelinkWorkspaceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for rel in (*identity.SOURCE_LOCKS, "config/soc.yaml"):
            f = self.root / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(rel)
        for _, source_names, _ in prelink.LANES.values():
            for name in source_names:
                f = self.root / f"dv/pcie_link/{name}.sv"
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(name)
        self.sha = "e" * 40
        self.output = self.root / "actions-output"
        self.env = {"GITHUB_ACTIONS": "true", "GITHUB_SHA": self.sha,
                    "GITHUB_RUN_ID": "14", "GITHUB_RUN_ATTEMPT": "2",
                    "GITHUB_OUTPUT": str(self.output)}

    def execute(self, lane, *, omit=False, dirty=False, compile_failure=False, env=None, provider=False):
        top, source_names, markers = prelink.LANES[lane]

        if provider:
            markers = (prelink.PROVIDER_MARKERS[lane],)
        prefix = ["iverilog", "-g2012"] + ([] if provider else ["-Wall"]) + ["-s", top, "-o"]

        def simulate(argv, *, cwd, check, stdout, stderr):
            self.assertEqual(cwd, self.root)
            self.assertTrue(check)
            if argv[0] == "iverilog":
                self.assertEqual(argv[:len(prefix)], prefix)
                self.assertEqual(argv[len(prefix) + 1:], [f"dv/pcie_link/{name}.sv" for name in source_names])
                binary = Path(argv[len(prefix)])
                self.assertFalse(binary.is_relative_to(self.root))
                binary.write_bytes(b"simulator product")
                if compile_failure:
                    stdout.write(b"compile diagnostic\n")
                    raise subprocess.CalledProcessError(1, argv)
            else:
                self.assertEqual(argv[0], "vvp")
                self.assertTrue(Path(argv[1]).is_file())
                for marker in markers[:-1] if omit else markers:
                    stdout.write(marker + b" unchanged suffix\n")
                if omit:
                    stderr.write(markers[-1] + b" not stdout\n")

        with patch.object(prelink.subprocess, "check_output", side_effect=[self.sha+"\n", b"M f" if dirty else b""]), \
             patch.object(prelink.subprocess, "run", side_effect=simulate):
            return prelink.execute(lane, root=self.root, env=self.env if env is None else env,
                                   provider=provider)

    def test_native_original_sources_and_selected_top_exist(self):
        for top, sources, _ in prelink.LANES.values():
            design, testbench = (prelink.ROOT / f"dv/pcie_link/{name}.sv" for name in sources)
            self.assertTrue(design.is_file())
            self.assertRegex(testbench.read_text(), rf"(?m)^module {top}\b")

    def test_three_distinct_transcript_workspaces_bind_sources_and_attempt(self):
        lanes = ("device-prelink", "host-bar0", "phy-response")
        dirs = [self.execute(lane) for lane in lanes]
        self.assertEqual(len(set(dirs)), 3)
        for lane, out in zip(lanes, dirs):
            self.assertEqual(out.parent.relative_to(self.root).as_posix(),
                             f".tools/runs/icarus/pcie-prelink-default/{lane}")
            self.assertTrue(out.name.startswith("ci-14-a2-"))
            self.assertEqual({p.name for p in out.iterdir()}, {
                "plan.json", "identity.json", "sources.f", "compile.log",
                "simulation.log", "simulation.stderr.log"})
            plan = json.loads((out / "plan.json").read_text())
            self.assertEqual(plan["source_revision"], self.sha)
            self.assertEqual(plan["identity"], identity.load(out / "identity.json", plan=plan))
            sources = (out / "sources.f").read_bytes()
            self.assertEqual(plan["identity"]["selection"]["filelist_sha256"], identity.sha(sources))
            self.assertEqual(plan["source_sha256"], {
                p: identity.sha((self.root / p).read_bytes()) for p in sources.decode().splitlines()})
            self.assertFalse(Path(plan["simulation_argv"][-1]).exists())
        self.assertEqual(self.output.read_text().splitlines(),
                         [f"execution_id={out.name}" for out in dirs])
        self.assertFalse((self.root / ".tools/pcie-prelink").exists())

    def test_bar_window_stays_separate_and_keeps_original_compiler_order(self):
        lane = "bar0-complete-span"
        first = self.execute(lane)
        second = self.execute(lane, env={**self.env, "GITHUB_RUN_ATTEMPT": "3"})
        self.assertEqual(first.parent.relative_to(self.root).as_posix(),
                         ".tools/runs/icarus/pcie-bar-window-default/bar0-complete-span")
        self.assertTrue(first.name.startswith("ci-14-a2-"))
        self.assertTrue(second.name.startswith("ci-14-a3-"))
        expected = b"dv/pcie_link/bar0_noc_translate.sv\ndv/pcie_link/tb_bar0_noc_translate.sv\n"
        self.assertEqual((first / "sources.f").read_bytes(), expected)
        self.assertEqual((second / "sources.f").read_bytes(), expected)
        self.assertNotEqual(first, second)
        self.assertFalse((first / "result.json").exists())
        self.assertEqual(list(first.glob("*.vvp")), [])
        self.assertFalse((self.root / ".tools/pcie-bar-window").exists())

    def test_missing_stdout_marker_fails_and_preserves_native_transcripts(self):
        with self.assertRaisesRegex(ValueError, "missing original simulator PASS marker"):
            self.execute("device-prelink", omit=True)
        [out] = (self.root / ".tools/runs").glob("*/*/*/*")
        self.assertTrue((out / "simulation.stderr.log").is_file())
        self.assertFalse((out / "result.json").exists())

    def test_compile_failure_retains_diagnostic_without_runtime_claim(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.execute("host-bar0", compile_failure=True)
        [out] = (self.root / ".tools/runs").glob("*/*/*/*")
        self.assertIn("compile diagnostic", (out / "compile.log").read_text())
        self.assertFalse((out / "simulation.log").exists())

    def test_dirty_wrong_source_and_missing_attempt_are_rejected_before_allocation(self):
        for env, dirty in ((self.env, True), ({**self.env, "GITHUB_SHA": "f"*40}, False),
                           ({**self.env, "GITHUB_RUN_ATTEMPT": ""}, False)):
            with self.subTest(env=env, dirty=dirty), self.assertRaisesRegex(ValueError, "clean exact checkout"):
                self.execute("phy-response", dirty=dirty, env=env)
        self.assertFalse((self.root / ".tools").exists())

    def test_provider_mode_keeps_original_order_and_independent_workspaces(self):
        expected = ("pipe-gen1-adapter", "phy-response", "device-prelink",
                    "host-bar0", "bar0-complete-span")
        self.assertEqual(tuple(prelink.PROVIDER_MARKERS), expected)
        with patch("sys.argv", ["workspace", "--provider-contract"]), patch.object(
                prelink, "execute") as execute:
            prelink.main()
        self.assertEqual([call.args for call in execute.call_args_list], [(lane,) for lane in expected])
        self.assertTrue(all(call.kwargs == {"provider": True} for call in execute.call_args_list))
        combined = [self.execute(lane, provider=True) for lane in expected]
        self.assertEqual(len(set(combined)), 5)
        for lane, out in zip(expected, combined):
            plan = json.loads((out / "plan.json").read_text())
            self.assertEqual(plan["execution_context"], "pcie-digital-link-provider-contract")
            self.assertEqual(plan["logical_test"], lane)
            self.assertEqual(plan["compile_argv"][0:3], ["iverilog", "-g2012", "-s"])
            self.assertFalse(Path(plan["simulation_argv"][-1]).exists())
            self.assertNotIn("result.json", {p.name for p in out.iterdir()})
        self.assertEqual(combined[0].parent.relative_to(self.root).as_posix(),
                         ".tools/runs/icarus/pcie-pipe-adapter-default/pipe-gen1-adapter")

    def test_provider_mode_does_not_allow_stderr_to_supply_pass(self):
        with self.assertRaisesRegex(ValueError, "missing original simulator PASS marker"):
            self.execute("pipe-gen1-adapter", omit=True, provider=True)
