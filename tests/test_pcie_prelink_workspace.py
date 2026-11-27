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

    def execute(self, lane, *, omit=False, dirty=False, compile_failure=False, env=None):
        top, source_names, markers = prelink.LANES[lane]

        def simulate(argv, *, cwd, check, stdout, stderr):
            self.assertEqual(cwd, self.root)
            self.assertTrue(check)
            if argv[0] == "iverilog":
                self.assertEqual(argv[:6], ["iverilog", "-g2012", "-Wall", "-s", top, "-o"])
                self.assertEqual(argv[7:], [f"dv/pcie_link/{name}.sv" for name in source_names])
                binary = Path(argv[6])
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
            return prelink.execute(lane, root=self.root, env=self.env if env is None else env)

    def test_native_original_sources_and_selected_top_exist(self):
        for top, sources, _ in prelink.LANES.values():
            design, testbench = (prelink.ROOT / f"dv/pcie_link/{name}.sv" for name in sources)
            self.assertTrue(design.is_file())
            self.assertRegex(testbench.read_text(), rf"(?m)^module {top}\b")

    def test_three_distinct_transcript_workspaces_bind_sources_and_attempt(self):
        dirs = [self.execute(lane) for lane in prelink.LANES]
        self.assertEqual(len(set(dirs)), 3)
        for lane, out in zip(prelink.LANES, dirs):
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
