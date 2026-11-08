"""Fail-closed contract tests for real supernoc wrapper and actual graph nodes.

These synthetic unit inputs only verify rejection logic. The CI job must
separately compile and inspect the real generated supernoc RTL.
"""
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import supernoc_netlist_contract as sc


def wrapper(width=4):
    return ("module supernoc_tb (\n"
            "input logic clk_i,\n"
            "input logic rst_ni,\n"
            f"input logic [{width - 1}:0] m_compute0_local_data_cpu_awid\n"
            ");\n"
            "soc_noc u_noc (\n"
            ".clk_i(clk_i),\n"
            ".rst_ni(rst_ni),\n"
            ".m_compute0_local_data_cpu_awid(m_compute0_local_data_cpu_awid)\n"
            ");\nendmodule\n")


def core(width=4):
    return ("module soc_noc (\n"
            "input logic clk_i,\n"
            "input logic rst_ni,\n"
            f"input logic [{width - 1}:0] m_compute0_local_data_cpu_awid\n"
            ");\nendmodule\n")


class SupernocContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for path in sc.SELECTED_SOURCES:
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
        self.wrapper = self.root / sc.SELECTED_SOURCES[0]
        self.core = self.root / sc.SELECTED_SOURCES[1]
        self.wrapper.write_text(wrapper())
        self.core.write_text(core())
        self.netlist = self.root / "netlist.json"
        self.meta = self.root / "netlist.json.meta.json"
        self.graph = {"version": 3, "fileTable": ["source.sv"], "nodes": [], "edges": []}
        for i, (pin, width) in enumerate((("clk_i", 1), ("rst_ni", 1),
                                          ("m_compute0_local_data_cpu_awid", 4))):
            base = 2*i + 1
            for node_id, path in ((base, f"supernoc_tb.{pin}"),
                                  (base + 1, f"supernoc_tb.u_noc.{pin}")):
                self.graph["nodes"].append({"id": node_id, "kind": "Port",
                                            "path": path, "name": pin,
                                            "direction": "In",
                                            "bounds": [0, width - 1]})
            self.graph["edges"].append({"source": base, "target": base + 1,
                                        "bounds": [0, width - 1], "disabled": False})
        self.write()

    def write(self):
        self.netlist.write_text(json.dumps(self.graph))
        sources = {path: hashlib.sha256((self.root / path).read_bytes()).hexdigest()
                   for path in sc.SELECTED_SOURCES}
        self.meta.write_text(json.dumps({
            "profile": "supernoc", "top": "supernoc_tb", "mode": "netlist",
            "evidence": "elaborated_slang_netlist_inputs_attested",
            "plan_sha256": "a"*64, "selected_source_sha256": sources,
            "output_sha256": hashlib.sha256(self.netlist.read_bytes()).hexdigest(),
        }))

    def test_malformed_sources_bad_binding_and_duplicate_pin(self):
        # The real-source parser never treats a source-only name as a graph PASS.
        self.wrapper.write_text(wrapper().replace(
            ".m_compute0_local_data_cpu_awid(m_compute0_local_data_cpu_awid)",
            ".m_compute0_local_data_cpu_awid(rst_ni)"))
        with self.assertRaisesRegex(sc.SupernocConnectivityError, "binding direction/width/name mismatch"):
            sc.expected_contract(self.wrapper.read_text(), self.core.read_text())
        self.wrapper.write_text(wrapper().replace(
            ".rst_ni(rst_ni),", ".rst_ni(rst_ni),\n.rst_ni(rst_ni),"))
        with self.assertRaisesRegex(sc.SupernocConnectivityError, "duplicate soc_noc binding"):
            sc.expected_contract(self.wrapper.read_text(), self.core.read_text())
        self.wrapper.write_text(wrapper())
        self.core.write_text(core(5))
        with self.assertRaisesRegex(sc.SupernocConnectivityError, "binding direction/width/name mismatch"):
            sc.expected_contract(self.wrapper.read_text(), self.core.read_text())

    def test_ledger_hash_and_source_fingerprint_fail_closed(self):
        self.netlist.write_text(self.netlist.read_text() + " ")
        with self.assertRaisesRegex(sc.SupernocConnectivityError, "hash mismatch"):
            sc.audit(self.netlist, self.meta, self.root)
        self.write()
        self.wrapper.write_text(self.wrapper.read_text() + "// tampered")
        with self.assertRaisesRegex(sc.SupernocConnectivityError, "unselected/changed source"):
            sc.audit(self.netlist, self.meta, self.root)

    def test_graph_port_width_and_disabled_edge_fail_closed(self):
        # Unit fixtures have three pins; patch minimum only for this test
        # by verifying lower-level checks directly, not fabricating full RTL.
        port_groups = {}
        for port in self.graph["nodes"]:
            port_groups.setdefault(port["path"], []).append(port)
        self.assertEqual(len(sc._group(port_groups, "supernoc_tb.clk_i", 1)), 1)
        with self.assertRaisesRegex(sc.SupernocConnectivityError, "wrong elaborated port width"):
            sc._group(port_groups, "supernoc_tb.u_noc.m_compute0_local_data_cpu_awid", 5)
        self.assertEqual(len(self.graph["edges"]), 3)
        self.graph["edges"][0]["disabled"] = True
        self.write()
        _, _, adjacency = sc.read_graph(self.netlist)
        self.assertEqual(adjacency[1], [])


if __name__ == "__main__":
    unittest.main()
