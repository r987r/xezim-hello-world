"""Verify source-truth audit fails closed if generated diagrams drift."""
from pathlib import Path
import json
import shutil
import tempfile
import unittest
from tools.ethernet_topology_audit import audit, EthernetTopologyError

ROOT = Path(__file__).resolve().parents[1]
INPUTS = [
    "config/soc.yaml",
    "gen/noc/floonoc/manifest.json",
    "gen/diagrams/graphs.json",
    "gen/diagrams/noc-topology.json",
    "gen/chip/manifest.json",
    "gen/chip/soc_top.sv",
]
for plane in ("data", "config"):
    suffix = "ethernet0/local_" + plane
    INPUTS.extend((
        "gen/noc/floonoc/" + suffix + "/floogen.yaml",
        "gen/noc/floonoc/" + suffix + "/floo_xezim_ethernet0_local_" +
        plane + "_noc.sv",
    ))


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        for name in INPUTS:
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, dest)

    def edit_json(self, name, mutate):
        file = self.root / name
        blob = json.loads(file.read_text())
        mutate(blob)
        file.write_text(json.dumps(blob))

    def test_generated_structural_but_packet_not_connected(self):
        evidence = audit(self.root)
        self.assertEqual(evidence["structural_global_links"], 4)
        self.assertEqual(evidence["packet_attachment"], "reserved_idle")
        self.assertEqual(evidence["config_attachment"], "explicit_axi_error")
        self.assertFalse(evidence["live_packet_data_path"])

    def test_drift_in_diagram_graph_fails(self):
        self.edit_json("gen/diagrams/graphs.json",
                       lambda j: j["noc_hierarchy"]["networks"].pop(
                           "ethernet0_local_data"))
        with self.assertRaisesRegex(EthernetTopologyError, "canonical graph"):
            audit(self.root)

    def test_misleading_diagram_live_packet_link_fails(self):
        def mutate(j):
            for conn in j["connections"]:
                if conn["from"]["instance"] == "ethernet0.ip" and (
                        conn["to"]["instance"] ==
                        "ethernet0_local_data.packet_dma"):
                    conn["status"] = "wired_boot_configuration"
                    conn["type"] = "axi_interconnect"
        self.edit_json("gen/diagrams/noc-topology.json", mutate)
        with self.assertRaisesRegex(EthernetTopologyError, "incorrectly drawn"):
            audit(self.root)

    def test_missing_global_data_bridge_fails(self):
        def mutate(j):
            j["connections"] = [
                c for c in j["connections"]
                if not (c["from"]["instance"] ==
                        "ethernet0_local_data.global_out" and
                        c["to"]["instance"] == "global_data.ethernet0")
            ]
        self.edit_json("gen/diagrams/noc-topology.json", mutate)
        with self.assertRaisesRegex(EthernetTopologyError, "single link"):
            audit(self.root)

    def test_fake_mac_attachment_fails(self):
        self.edit_json("gen/chip/manifest.json",
                       lambda j: next(x for x in j["peripheral_subsystems"]
                                      if x["name"] == "ethernet0").update(
                                          rtl_attachment="instantiated"))
        with self.assertRaisesRegex(EthernetTopologyError, "diagram connection"):
            audit(self.root)


if __name__ == "__main__":
    unittest.main()
