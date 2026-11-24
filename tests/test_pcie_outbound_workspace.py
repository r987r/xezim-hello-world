"""Check original outbound evidence custody, not additional RTL stimulus."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

from dv.pcie0 import run_outbound_smoke as producer
from tools.test_identity import load, relative_path, sha


ROOT = Path(__file__).resolve().parents[1]
HEAD = "1" * 40
RAW = b'{"passed":true,"tx_mem_write_tlps":15,"tx_mem_read_tlps":8,"rx_completion_tlps":15,"host_bytes_verified":1369,"device_bytes_verified":1369}\n'
XML = (b'<testsuites><testsuite><testcase classname="outbound_smoke" '
       b'name="outbound_bidirectional_real_tlps"/></testsuite></testsuites>')


class OutboundWorkspaceTests(unittest.TestCase):
    def setUp(self):
        area = tempfile.TemporaryDirectory()
        self.addCleanup(area.cleanup)
        self.root = Path(area.name).resolve()
        self.here = self.root / "dv/pcie0"
        self.vendor = self.root / ".tools/verilog_pcie"
        self.outputs = self.root / ".tools/github-output"
        self.rtl = ["rtl/dma_if_pcie.v", "rtl/dma_if_pcie_rd.v", "rtl/dma_if_pcie_wr.v",
                    "rtl/priority_encoder.v", "rtl/pulse_merge.v"]
        for name in ("config/soc.yaml", "config/ip.lock.yaml", "config/interface_contracts.yaml",
                     "Bender.yml", "Bender.lock", "dv/pcie0/outbound_smoke.py",
                     "dv/pcie0/upstream.lock.json"):
            self.write(self.root / name, name.encode())
        for name in self.rtl:
            self.write(self.vendor / name, name.encode())
        for name, link in producer.MODEL_LINKS.items():
            path = self.vendor / name
            self.write(path.parent.parent / Path(link).name, link.encode())
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(link)
        self.use(patch.multiple(producer, ROOT=self.root, HERE=self.here, VENDOR=self.vendor))
        self.use(patch.object(producer, "source_state", return_value=(HEAD, False)))
        self.use(patch.object(producer, "source_contract", return_value={
            "commit": "2" * 40, "outbound_rtl_modules": self.rtl,
            "outbound_python_models": ["tb/dma_if_pcie_wr/dma_psdp_ram.py"],
        }))
        self.use(patch.dict(os.environ, {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2",
                                         "GITHUB_OUTPUT": str(self.outputs)}))
        package = ModuleType("cocotb_test")
        package.simulator = ModuleType("cocotb_test.simulator")
        package.simulator.run = self.simulate
        self.use(patch.dict("sys.modules", {"cocotb_test": package,
                                          "cocotb_test.simulator": package.simulator}))
        self.mutate = self.foreign = False
        self.xml = XML

    def use(self, scope):
        scope.start()
        self.addCleanup(scope.stop)

    def write(self, path, raw):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path

    def simulate(self, **args):
        build = Path(args["sim_build"])
        self.write(build / "private.vvp", b"must never archive")
        self.write(build / "timescale.f", f'+timescale+{args["timescale"]}\n'.encode())
        self.write(Path(args["extra_env"]["SOC_PCIE_OUTBOUND_RESULT"]), RAW)
        native = self.write(build / "native_results.xml", self.xml)
        if self.mutate:
            self.write(self.vendor / self.rtl[-1], b"changed compiler input")
        return str(native if not self.foreign else self.root / "earlier_results.xml")

    def exercise(self):
        with redirect_stdout(io.StringIO()):
            producer.run()

    def test_immutable_original_native_files_and_scoreboard_only(self):
        self.exercise()
        self.exercise()
        dirs = [self.root / line.removeprefix("archive_dir=")
                for line in self.outputs.read_text().splitlines()]
        self.assertEqual(len(set(dirs)), 2)
        for path in dirs:
            identity = load(path / "identity.json")
            self.assertEqual(path.relative_to(self.root / ".tools/runs"), relative_path(identity))
            self.assertTrue(identity["run_id"].startswith("ci-123-a2-"))
            self.assertEqual(set(p.name for p in path.iterdir()), {
                "identity.json", "plan.json", "outbound-inputs.json", "source-head.txt",
                "rtl-sources.json", "sources.f", "timescale.f", "results.xml", producer.SCOREBOARD})
            self.assertEqual((path / producer.SCOREBOARD).read_bytes(), RAW)
            self.assertEqual((path / "results.xml").read_bytes(), XML)
            self.assertEqual(sha((path / "sources.f").read_bytes()),
                             identity["selection"]["filelist_sha256"])
            inputs = json.loads((path / "outbound-inputs.json").read_text())
            self.assertEqual(len(inputs["sha256"]), 9)
            self.assertEqual(inputs["identity_sha256"], identity["identity_sha256"])
            self.assertTrue((self.root / ".tools/pcie0/outbound-builds"
                             / identity["run_id"] / "private.vvp").is_file())
        self.assertFalse((self.root / ".tools/pcie0/outbound").exists())

    def test_reject_foreign_xml_and_changed_input(self):
        self.foreign = True
        with self.assertRaisesRegex(ValueError, "foreign results"):
            self.exercise()
        self.foreign, self.mutate = False, True
        with self.assertRaisesRegex(ValueError, "selected inputs changed"):
            self.exercise()

    def test_reject_corrupt_native_case_and_vendor_link(self):
        self.xml = XML.replace(b"outbound_bidirectional_real_tlps", b"other")
        with self.assertRaisesRegex(ValueError, "passing outbound case"):
            self.exercise()
        name = next(iter(producer.MODEL_LINKS))
        (self.vendor / name).unlink()
        (self.vendor / name).symlink_to("../unreviewed.py")
        with self.assertRaisesRegex(ValueError, "model link changed"):
            self.exercise()

    def test_no_external_xml_path_or_engine_override(self):
        for env in ({"COCOTB_RESULTS_FILE": "result.xml"}, {"SIM": "verilator"}):
            with patch.dict(os.environ, env):
                with self.assertRaisesRegex(ValueError, "run-owned XML"):
                    self.exercise()
        self.assertFalse(self.outputs.exists())


if __name__ == "__main__":
    unittest.main()
