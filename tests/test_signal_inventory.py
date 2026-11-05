"""Real RTL declaration inventory and auto-grouping tests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import signal_inventory


class SignalInventoryTests(unittest.TestCase):
    def test_real_generated_soc_axi_ports(self):
        inventory = signal_inventory.build(ROOT)
        self.assertGreater(inventory["counts"]["ports"], 100)
        self.assertGreater(inventory["counts"]["mapped"], 100)
        self.assertEqual(inventory["counts"]["ports"],
                         inventory["counts"]["mapped"] + inventory["counts"]["unbound"])
        ep = inventory["endpoints"]["compute0_local_data.cpu"]
        signals = ep["signals"]
        awaddr = next(x for x in signals if x["logical_name"] == "awaddr")
        self.assertEqual(awaddr["channel"], "AW")
        self.assertEqual(awaddr["width"], 64)
        self.assertEqual(awaddr["direction"], "input")
        self.assertTrue(awaddr["location"].startswith("gen/supernoc/soc_noc.sv:"))
        self.assertEqual(inventory["limits"]["bit_level_wiring_proven"], False)
        self.assertIn("AW", ep["protocols"]["axi4:axi"]["channels"])
        self.assertIn("R", ep["protocols"]["axi4:axi"]["channels"])

    def test_raw_source_contains_real_clock_reset(self):
        inventory = signal_inventory.build(ROOT)
        self.assertTrue(any(x["protocol"] == "clock" for x in inventory["unbound_ports"]))
        self.assertTrue(any(x["protocol"] == "reset" for x in inventory["unbound_ports"]))

    def test_protocol_inference(self):
        examples = {
            "awaddr": ("axi4", "AW"),
            "m_axi_arvalid": ("axi4", "AR"),
            "axi4_lite_bresp": ("axi4", "B"),
            "dfi_rddata_valid": ("dfi", "READ"),
            "dfi_wrdata_en": ("dfi", "WRITE"),
            "pcie_cfg_status": ("pcie", "PCIe"),
            "pipe_txdata": ("pcie", "PIPE"),
            "s_axis_rq_tdata": ("pcie", "RQ"),
            "rgmii_txd": ("ethernet", "LINK"),
            "aclk": ("clock", "CLOCK"),
            "rst_ni": ("reset", "RESET"),
            "custom_req": ("generic", "HANDSHAKE"),
            "txdata": ("discrete", "OTHER"),
        }
        for port, expected in examples.items():
            with self.subTest(port=port):
                obj = signal_inventory.infer_protocol(port)
                self.assertEqual((obj["protocol"], obj["channel"]), expected)

    def test_unknown_block_is_generic_without_viewer_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "gen/supernoc").mkdir(parents=True)
            (root / "gen/diagrams").mkdir(parents=True)
            (root / "gen/supernoc/soc_noc.sv").write_text(
                "module soc_noc (\n"
                "  input logic clk_i,\n"
                "  input logic [31:0] m_pcie47_rq_awaddr,\n"
                "  output logic m_pcie47_rq_awready,\n"
                "  output logic [7:0] s_ethernet9_dma_dfi_rddata,\n"
                "  input logic rst_ni\n"
                ");\nendmodule\n"
            )
            # final ANSI declaration without trailing comma is not accepted by
            # generator format, which is intentionally strict. Give it comma.
            sv = root / "gen/supernoc/soc_noc.sv"
            sv.write_text(sv.read_text().replace("rst_ni\n", "rst_ni,\n"))
            nodes = [{"name": "pcie47.rq", "module": "unknown_pcie_ip"},
                     {"name": "ethernet9.dma", "module": "unknown_eth_ip"}]
            topo = {"schema_version": 1, "instances": nodes, "connections": [
                {"id": "new", "from": {"instance": "pcie47.rq", "port": "o"},
                 "to": {"instance": "ethernet9.dma", "port": "i"},
                 "signals": [{"name": "AXI4"}]}
            ]}
            (root / "gen/diagrams/noc-topology.json").write_text(json.dumps(topo))
            inventory = signal_inventory.build(root)
            self.assertEqual(len(inventory["endpoints"]["pcie47.rq"]["signals"]), 2)
            self.assertEqual(inventory["counts"]["unbound"], 2)
            self.assertEqual(inventory["declared_connections"][0]["connection_evidence"],
                             "generator_declared_not_slang_traced")

    def test_slang_report_normalizes_external_ports(self):
        rows = [{"name": "tb.dut.u_dma.axi_awvalid",
                 "direction": "Out", "width": 1,
                 "location": "rtl/u_dma.sv:11:4"}]
        result = signal_inventory.report_ports(rows)
        self.assertEqual(result[0]["evidence"], "elaborated_slang_report_port")
        self.assertEqual(result[0]["direction"], "output")
        with self.assertRaisesRegex(ValueError, "slang-report"):
            signal_inventory.report_ports([{"name": "fake", "width": "not_int"}])

    def test_optional_slang_port_report_discovers_unknown_hierarchy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ports.json"
            path.write_text(json.dumps([
                {"name": "chip.dut.pcie_custom0.m_axi_awaddr",
                 "width": 48, "direction": "In", "location": "rtl/pcie.sv:3:2"},
                {"name": "chip.dut.ethernet77.dfi_rddata_valid",
                 "width": 1, "direction": "Out", "location": "rtl/ethernet.sv:5:2"},
            ]))
            graph = signal_inventory.build(ROOT, slang_ports=path)
            self.assertIn("chip.dut.pcie_custom0", graph["endpoints"])
            self.assertIn("chip.dut.ethernet77", graph["endpoints"])
            self.assertEqual(
                graph["endpoints"]["chip.dut.pcie_custom0"]["signals"][0]["width"], 48)
            self.assertEqual(graph["source"], "elaborated_slang_report")

    def test_rejects_malformed_real_decl(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "soc_noc.sv"
            p.write_text("module soc_noc (\n  parameter int AW=10\n);\n")
            with self.assertRaisesRegex(ValueError, "unsupported generated ANSI"):
                signal_inventory.source_ports(p, Path(temp))


if __name__ == "__main__":
    unittest.main()
