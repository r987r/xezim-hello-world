"""Connectivity acceptance checks for the single generated NoC DUT."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import floonoc_gen
import noc_diagrams
import supernoc_gen


class SuperNoCConnectivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.soc = yaml.safe_load((ROOT / "config/soc.yaml").read_text())
        cls.knobs = yaml.safe_load((ROOT / "config/interface_contracts.yaml").read_text())

    def emit_profiles(self, soc, mutate=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nets = {}
            for name, design in floonoc_gen.profiles(soc, self.knobs).items():
                config = copy.deepcopy(design["config"])
                if mutate:
                    mutate(name, config)
                dest = root / design["path"] / "floogen.yaml"
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(yaml.safe_dump(config))
                nets[name] = {"config": dest.relative_to(root).as_posix(),
                              "top_module": "floo_xezim_" + name + "_noc",
                              "plane": design["plane"]}
            (root / "manifest.json").write_text(json.dumps({"networks": nets}))
            return supernoc_gen.emit(soc, root, root / "supernoc/supernoc_tb.sv")

    def test_wrapper_connections_match_single_architecture_graph(self):
        meta = self.emit_profiles(self.soc)
        networks = noc_diagrams.read_generated_nocs(ROOT / "gen/noc/floonoc")
        graph = noc_diagrams.diagram_gen_metadata(self.soc, networks)
        edges = {(e["from"]["instance"], e["to"]["instance"])
                 for e in graph["connections"]
                 if e["from"]["instance"].split(".")[0] in networks
                 and e["to"]["instance"].split(".")[0] in networks
                 and e["from"]["instance"].split(".")[0] != e["to"]["instance"].split(".")[0]}
        self.assertEqual({(e["from"], e["to"]) for e in meta["connections"]}, edges)
        self.assertEqual(len(edges), 19)

    def test_every_window_resolves_to_leaf_including_boot_reads(self):
        meta = self.emit_profiles(self.soc)
        targets = {s["name"] for s in meta["slaves"]}
        routes = [r for m in meta["masters"] for r in m["regions"]]
        # Each initiator must have exactly one route per authorized address
        # window; a fixed count silently breaks when more peripheral NoCs are
        # generated. Uniqueness stays a strict source-derived assertion.
        route_keys = [(m["name"], r["base"], r["size"])
                      for m in meta["masters"] for r in m["regions"]]
        self.assertEqual(len(routes), len(set(route_keys)))
        self.assertEqual({r["destination"] for r in routes}, targets)
        self.assertEqual(sum(r["access"] == "read" for r in routes), 4)
        self.assertTrue(any(len(r["networks"]) == 3 for r in routes))

    def test_relocating_sram_below_old_numeric_cutoff_preserves_routes(self):
        soc = copy.deepcopy(self.soc)
        next(x for x in soc["address_map"]["data"] if x["name"] == "compute1.sram")["base"] = "0x08000000"
        meta = self.emit_profiles(soc)
        for m in meta["masters"]:
            if m["plane"] == "data":
                region = next(r for r in m["regions"] if r["base"] == 0x08000000)
                self.assertEqual(region["destination"], "s_compute1_local_data_sram")
                self.assertEqual(region["access"], "read_write")

    def test_broken_remote_decode_is_rejected(self):
        def mutate(name, config):
            if name == "compute1_local_data":
                next(e for e in config["endpoints"] if e["name"] == "sram")["addr_range"]["base"] = 0x12000000
        with self.assertRaisesRegex(ValueError, "missing/ambiguous NoC decode"):
            self.emit_profiles(self.soc, mutate)

    def test_cross_network_width_mismatch_is_rejected(self):
        def mutate(name, config):
            if name == "global_data":
                next(p for p in config["protocols"] if p["name"] == "axi_in")["id_width"] += 1
        with self.assertRaisesRegex(ValueError, "AXI id_width mismatch"):
            self.emit_profiles(self.soc, mutate)

    def test_memory_instance_name_does_not_change_id_widths(self):
        soc = copy.deepcopy(self.soc)
        next(s for s in soc["subsystems"] if s["type"] == "memory")["name"] = "memory_cluster"
        soc["networks"]["global_config"]["reachable_subsystems"][soc["networks"]["global_config"]["reachable_subsystems"].index("memory0")] = "memory_cluster"
        for plane in ("data", "config"):
            for window in soc["address_map"][plane]:
                window["name"] = window["name"].replace("memory0.", "memory_cluster.")
        for output in soc["networks"]["global_data"]["outputs"]:
            output["target"] = output["target"].replace("memory0.", "memory_cluster.")
        for target in soc["memory_targets"]:
            target["name"] = target["name"].replace("memory0.", "memory_cluster.")
        meta = self.emit_profiles(soc)
        sink = next(s for s in meta["slaves"] if s["endpoint"] == "target_crossbar")
        self.assertEqual(sink["id_width"], soc["buses"]["data"]["id_bits"])
        self.assertEqual(sink["network"], "memory_cluster_local_data")


if __name__ == "__main__":
    unittest.main()
