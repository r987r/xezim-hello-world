"""Host-only packaging checks for the four existing isolated Icarus tests."""
from fnmatch import fnmatch
import json
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from types import ModuleType
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

import yaml

from dv.ethernet0 import native_workspace as native
from tools.test_identity import SOURCE_LOCKS

ROOT = Path(__file__).resolve().parents[1]


def xunit(module, names):
    xml = ElementTree.Element("testsuites")
    suite = ElementTree.SubElement(xml, "testsuite")
    for name in names:
        ElementTree.SubElement(suite, "testcase", classname=module, name=name)
    return ElementTree.tostring(xml)


class EthernetNativeWorkspaceTests(unittest.TestCase):
    def test_four_native_scopes_get_exact_separate_upload_workspaces(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            inputs = [
                "rtl/io/ethernet0/ip.lock.yml", *SOURCE_LOCKS, "config/soc.yaml",
                *[module.replace(".", "/") + ".py" for _, module, _, _ in native.PROFILES.values()],
            ]
            for name in set(inputs):
                dest = root / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, dest)
            socket = root / "ether-fixture.v"
            socket.write_text("ordered filelist fixture\n")
            following = root / "next-fixture.v"
            following.write_text("another list entry\n")
            simulator = ModuleType("cocotb_test.simulator")
            native_outputs = {}

            def fake_run(**kwargs):
                target = next(k for k, v in native.PROFILES.items() if v[1] == kwargs["module"])
                top, module, _, cases = native.PROFILES[target]
                self.assertEqual(kwargs["simulator"], "icarus")
                self.assertEqual(kwargs["verilog_sources"], [str(socket), str(following)])
                self.assertEqual(kwargs["toplevel"], top)
                self.assertEqual(kwargs["timescale"], "1ns/1ps")
                self.assertFalse(kwargs["waves"])
                work = Path(kwargs["sim_build"])
                self.assertTrue(work.is_relative_to(root / ".tools/ethernet-icarus-builds"))
                original = xunit(module, cases)
                native_outputs[target] = original
                (work / f"{target}_results.xml").write_bytes(original)
                (work / "timescale.f").write_bytes(b"+timescale+1ns/1ps\n")
                (work / f"{top}.vvp").write_bytes(b"private test fixture")

            simulator.run = fake_run
            workflows = {
                "ethernet0-gmii": ("ethernet-standalone", "gmii"),
                "ethernet0-gmii-stage": ("ethernet-gmii-stager", "gmii-stager"),
                "ethernet0-mvp-rx": ("ethernet-mvp", "connected-rx"),
                "ethernet0-mvp-tx": ("ethernet-mvp", "connected-rx"),
            }
            github_output = root / "ci-output"
            workspaces = set()
            with patch.object(native, "ROOT", root), patch.object(native, "_source_state", return_value=("d"*40, False)), \
                    patch.dict(sys.modules, {"cocotb_test": ModuleType("cocotb_test"), "cocotb_test.simulator": simulator}), \
                    patch.dict(os.environ, {"GITHUB_RUN_ID": "100", "GITHUB_RUN_ATTEMPT": "2", "GITHUB_OUTPUT": str(github_output)}):
                for target, (workflow, job) in workflows.items():
                    with self.subTest(target=target):
                        folder = native.run_existing_icarus(target, [socket, following])
                        self.assertNotIn(folder, workspaces)
                        workspaces.add(folder)
                        run = json.loads((folder / "identity.json").read_text())
                        self.assertEqual(run["simulator"], "icarus")
                        self.assertEqual(run["config_target"], "ethernet-standalone-default")
                        self.assertTrue(run["run_id"].startswith("ci-100-a2-"))
                        self.assertEqual((folder / "results.xml").read_bytes(), native_outputs[target])
                        self.assertEqual({p.name for p in folder.iterdir()}, {
                            "identity.json", "plan.json", "sources.f", "source-head.txt",
                            "icarus-inputs.json", "results.xml", "timescale.f",
                        })
                        cfg = yaml.safe_load((ROOT / f".github/workflows/{workflow}.yml").read_text())
                        upload = next(v["with"]["path"] for v in cfg["jobs"][job]["steps"]
                                      if str(v.get("uses", "")).startswith("actions/upload-artifact@"))
                        key = target.replace("-", "_") + "_run_id"
                        selectors = [line for line in upload.splitlines() if f".outputs.{key} " in line]
                        self.assertEqual(len(selectors), 1)
                        prefix, expression = selectors[0].split(chr(36) + "{{", 1)
                        selector = prefix + run["run_id"] + expression.split("}}", 1)[1]
                        self.assertTrue(fnmatch(folder.relative_to(root).as_posix()+"/", selector))
                        self.assertIn(f"{key}={run['run_id']}", github_output.read_text())
            self.assertEqual(len(workspaces), 4)

    def test_fail_closed_on_missing_duplicate_foreign_or_skipped_case(self):
        _, module, _, names = native.PROFILES["ethernet0-gmii"]
        valid = xunit(module, names)
        native.validate_xunit(valid, module, names)
        for data in (xunit(module, names[:-1]), xunit(module, (*names, names[0])),
                     xunit("foreign", names), valid.replace(b"</testsuite>", b"<skipped /></testsuite>"),
                     valid.replace(b"<testsuite>", b'<testsuite errors="1">')):
            with self.assertRaisesRegex(ValueError, "exact passing case set"):
                native.validate_xunit(data, module, names)
