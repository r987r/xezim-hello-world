"""Direct SoC port evidence reuses exact selected-slang memory bit checker."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from soc_netlist_ports import audit, _strict_links
from real_netlist_contract import ConnectivityEvidenceError


class SocDirectPortTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "config").mkdir()
        (self.root / ".tools/regression/chip-probe").mkdir(parents=True)
        self.top = self.root / "chip_top.sv"
        self.top.write_text("module full_chip_tb; endmodule\n")
        source_list = self.root / ".tools/regression/chip-probe/sources.f"
        source_list.write_text("chip_top.sv\n")
        plan = {
            "target":"chip-probe", "top":"full_chip_tb",
            "source_target":"noc", "sources":["chip_top.sv"]
        }
        (source_list.parent / "plan.json").write_text(json.dumps(plan))
        (self.root / "config/regression.yaml").write_text(
            "tests:\n  chip-probe:\n    top: full_chip_tb\n    sources: noc\n")
        self.netlist = self.root / "netlist.json"
        self.meta = self.root / "netlist.meta.json"
        self.contract = self.root / "contract.json"
        self.graph = {"version":3, "fileTable": ["chip_top.sv"], "nodes":[
            {"id":1, "kind":"Port","path":"full_chip_tb.u_source.wdata",
             "name":"wdata", "bounds":[0,63],"direction":"Out"},
            {"id":2, "kind":"Port","path":"full_chip_tb.u_sink.wdata",
             "name":"wdata", "bounds":[0,63],"direction":"In"},
        ], "edges":[{"source":1, "target":2, "bounds":[0,63], "disabled":False}]}
        self.spec = {
            "schema_version":1,"profile":"chip-probe","compiled_top":"full_chip_tb",
            "filelist_sha256":hashlib.sha256(source_list.read_bytes()).hexdigest(),
            "links":[{"name":"source_to_sink_wdata",
                      "source":"full_chip_tb.u_source.wdata",
                      "destination":"full_chip_tb.u_sink.wdata",
                      "width":64, "protocol":"axi4"}],
        }
        self.save()

    def save(self):
        self.netlist.write_text(json.dumps(self.graph))
        self.contract.write_text(json.dumps(self.spec))
        source_list = self.root/".tools/regression/chip-probe/sources.f"
        plan = self.root/".tools/regression/chip-probe/plan.json"
        self.meta.write_text(json.dumps({
            "profile":"chip-probe","top":"full_chip_tb","mode":"netlist",
            "evidence":"elaborated_slang_netlist_inputs_attested",
            "output_sha256":hashlib.sha256(self.netlist.read_bytes()).hexdigest(),
            "filelist_sha256":hashlib.sha256(source_list.read_bytes()).hexdigest(),
            "plan_sha256":hashlib.sha256(plan.read_bytes()).hexdigest(),
            "selected_source_sha256":{
                "chip_top.sv":hashlib.sha256(self.top.read_bytes()).hexdigest()},
        }))

    def check(self):
        return audit(self.root,"chip-probe",netlist=self.netlist,
                     meta=self.meta,contract_path=self.contract)

    def test_full_width_direct_witness_is_explicit_not_routed_proof(self):
        report=self.check()
        self.assertEqual(report["verified_direct_port_bindings"],1)
        self.assertEqual(report["verified_direct_bit_positions"],64)
        self.assertFalse(report["noc_routed_traffic_observed"])
        self.assertFalse(report["cdc_qualified"])
        self.assertEqual(report["checks"][0]["connected_bit_count"],64)

    def test_truncated_swapped_or_disabled_edge_rejected(self):
        for corruption in ("truncated","swapped","disabled","direction"):
            with self.subTest(corruption=corruption):
                self.setUp_graph()
                edge=self.graph["edges"][0]
                if corruption=="truncated": edge["bounds"]=[0,62]
                elif corruption=="swapped": edge["bounds"]=[64,127]
                elif corruption=="disabled": edge["disabled"]=True
                else: self.graph["nodes"][0]["direction"]="In"
                self.save()
                with self.assertRaises(ConnectivityEvidenceError):
                    self.check()

    def setUp_graph(self):
        self.graph["edges"][0]={"source":1,"target":2,"bounds":[0,63],"disabled":False}
        self.graph["nodes"][0]["direction"]="Out"

    def test_selected_source_and_profile_mismatch_rejected(self):
        self.top.write_text("module full_chip_tb; wire changed; endmodule\n")
        with self.assertRaises(ConnectivityEvidenceError):
            self.check()
        self.top.write_text("module full_chip_tb; endmodule\n")
        self.spec["filelist_sha256"]="0"*64
        self.save()
        with self.assertRaisesRegex(ConnectivityEvidenceError, "compiled variant"):
            self.check()

    def test_duplicate_names_and_imaginary_port_rejected(self):
        self.spec["links"].append(dict(self.spec["links"][0]))
        with self.assertRaisesRegex(ConnectivityEvidenceError, "ambiguous"):
            _strict_links(self.spec)
        self.spec["links"]=[dict(self.spec["links"][0],
                                 destination="full_chip_tb.u_sink.imaginary")]
        self.save()
        with self.assertRaisesRegex(ConnectivityEvidenceError,"missing real elaborated port"):
            self.check()

    def test_missing_real_slang_netlist_does_not_fall_back_to_names(self):
        self.netlist.unlink()
        with self.assertRaises(FileNotFoundError):
            self.check()


if __name__=="__main__":
    unittest.main()
