import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import pcie_link_workspace, run_workspace, test_identity

ROOT = Path(__file__).resolve().parents[1]


class DigitalLinkWorkspaceTest(unittest.TestCase):
    def test_each_lane_owns_one_clean_source_bound_runtime_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def git(*args):
                return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()

            git("init", "-q")
            for rel in ("config/soc.yaml", ".gitignore", *test_identity.SOURCE_LOCKS):
                dest = root/rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT/rel, dest)
            git("add", ".")
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.com",
                "commit", "-qm", "fixture")
            revision = git("rev-parse", "HEAD")
            compiler = root/".tools/pcie-cross-fusesoc/core.vc"
            compiler.parent.mkdir(parents=True)
            source_bytes = b"src/original-provider.sv\n"
            compiler.write_bytes(source_bytes)
            with patch.dict(os.environ, {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2",
                                         "GITHUB_SHA": revision}):
                paths = []
                for mode, (target, logical) in pcie_link_workspace.MODES.items():
                    out = pcie_link_workspace.reserve(root, mode, compiler)
                    identity = test_identity.load(out/"identity.json", target=target)
                    self.assertEqual(run_workspace.verify_run(out, identity), out)
                    self.assertEqual(out.parts[-2], logical)
                    self.assertTrue(out.name.startswith("ci-123-a2-"))
                    self.assertEqual(out.joinpath("sources.f").read_bytes(), source_bytes)
                    self.assertFalse(out.joinpath("result.json").exists())
                    paths.append(out)
                self.assertEqual(len(set(paths)), 3)
                root.joinpath("stray.txt").write_text("untracked output")
                with self.assertRaisesRegex(ValueError, "clean exact checkout"):
                    pcie_link_workspace.reserve(root, "l0", compiler)
                self.assertEqual(len(list((root/".tools/runs").rglob("identity.json"))), 3)
