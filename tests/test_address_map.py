"""Unified architectural address-map tests; CSR is a subset, memory external."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import address_map


class AddressMapTests(unittest.TestCase):
    def test_all_configured_data_and_control_apertures_are_present(self):
        cfg = yaml.safe_load((ROOT / "config/soc.yaml").read_text())
        m = address_map.build()
        expected = {(plane, r["name"]) for plane in ("data", "config")
                    for r in cfg["address_map"][plane]}
        actual = {(r["plane"], r["name"]) for r in m["regions"]}
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), len(m["regions"]))
        self.assertEqual({p["name"] for p in m["planes"]}, {"data", "config"})
        self.assertEqual({p["addr_bits"] for p in m["planes"]}, {32, 64})
        for r in m["regions"]:
            self.assertEqual(int(r["end_exclusive"], 0),
                             int(r["base"], 0) + int(r["size"], 0))
            self.assertEqual(r["architecture_status"], "declared_aperture")
            self.assertEqual(r["implementation_status"], "not_qualified_for_this_variant")
            self.assertFalse(r["registers"])

    def test_ddr_hbm_architecture_vs_bounded_modeled_storage(self):
        regions = {r["name"]: r for r in address_map.build()["regions"]}
        for name, target in (("memory0.ddr0", "litedram"),
                             ("memory0.hbm0", "hisa_hbm")):
            r = regions[name]
            self.assertEqual(r["plane"], "data")
            self.assertEqual(r["size"], "0x40000000")
            self.assertEqual(r["modeled_capacity_bytes"], 65536)
            self.assertEqual(r["physical_controller_declared"], target)
            self.assertEqual(r["modeled_backing_declared"], "axi_ram")
            self.assertFalse(r["cpu32_direct_data_addressable"])
            self.assertEqual(r["implementation_status"], "not_qualified_for_this_variant")
        self.assertEqual(regions["compute0.sram"]["modeled_capacity_bytes"], 16384)
        self.assertEqual(regions["boot.rom"]["kind"], "rom")
        self.assertEqual(regions["boot.flash"]["kind"], "flash")

    def test_emitted_rdl_view_only_describes_external_data_memories(self):
        view = address_map.memory_rdl_view(address_map.build())
        self.assertTrue(view.startswith("// Generated architectural"))
        self.assertEqual(view.count("external mem {"), 8)
        self.assertIn("mementries = 134217728;", view)
        self.assertIn("sw = r;", view)
        self.assertNotIn("boot_reset_ctrl", view)
        self.assertNotIn("axi_lite_regs", view)
        try:
            from systemrdl import RDLCompiler
        except ImportError:
            return  # The pinned standalone CSR CI compiles this as SystemRDL.
        with tempfile.TemporaryDirectory() as tmp:
            rdl = Path(tmp) / "soc_data_memory_view.rdl"
            rdl.write_text(view)
            c = RDLCompiler()
            c.compile_file(str(rdl))
            top = c.elaborate(top_def_name="soc_data_memory_view")
            from systemrdl.node import MemNode
            self.assertEqual(sum(isinstance(n, MemNode) for n in top.top.children()), 8)

    def fixture(self, *, variant="cold_boot"):
        config = ROOT / "config/soc.yaml"
        cfg = yaml.safe_load(config.read_text())
        window = next(r for r in cfg["address_map"]["config"]
                      if r["name"] == "boot.reset_ctrl")
        catalog = {
            "schema_version": 1, "variant": variant,
            "config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
            "instances": [{
                "name": "boot.reset_ctrl", "base": window["base"], "size": window["size"],
                "status": "implemented",
                "registers": [{
                    "name": "cpu_release", "offset": "0x0", "size_bytes": 4,
                    "width_bits": 32, "access": "rw",
                    "fields": [
                        {"name": "secondary_release", "lsb": 0, "msb": 15}
                    ]
                }],
            }]
        }
        return catalog

    def from_fixture(self, catalog, *, variant="cold_boot"):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "csr-map.json"
            path.write_text(json.dumps(catalog))
            return address_map.build(csr_path=path, variant=variant)

    def test_csr_subset_base_relative_and_absolute_are_consistent(self):
        catalog = self.from_fixture(self.fixture())
        self.assertEqual(len(catalog["regions"]), 14)
        r = next(r for r in catalog["regions"] if r["name"] == "boot.reset_ctrl")
        self.assertEqual(r["plane"], "config")
        self.assertEqual(r["kind"], "csr_aperture")
        self.assertEqual(r["base"], "0x40020000")
        self.assertEqual(r["registers"][0]["address"], "0x40020000")
        self.assertEqual(r["registers"][0]["definition_status"],
                         "SystemRDL_defined_not_RTL_proof")
        self.assertFalse(any(r["registers"] for r in catalog["regions"]
                             if r["kind"] != "csr_aperture"))

    def test_stale_csr_variant_and_address_mismatch_fail(self):
        original = self.fixture()
        stale = json.loads(json.dumps(original))
        stale["config_sha256"] = "0" * 64
        with self.assertRaisesRegex(address_map.AddressMapError, "stale/foreign"):
            self.from_fixture(stale)
        with self.assertRaisesRegex(address_map.AddressMapError, "stale/foreign"):
            self.from_fixture(original, variant="cpu_dma")
        wrong = json.loads(json.dumps(original))
        wrong["instances"][0]["base"] = "0x40030000"
        with self.assertRaisesRegex(address_map.AddressMapError, "disagrees"):
            self.from_fixture(wrong)
        duplicate = json.loads(json.dumps(original))
        duplicate["instances"].append(duplicate["instances"][0])
        with self.assertRaisesRegex(address_map.AddressMapError, "duplicate"):
            self.from_fixture(duplicate)

    def test_invalid_and_overlapping_fields_rejected(self):
        original = self.fixture()
        collision = json.loads(json.dumps(original))
        collision["instances"][0]["registers"][0]["fields"].append({
            "name": "alias", "lsb": 8, "msb": 16
        })
        with self.assertRaisesRegex(address_map.AddressMapError, "overlapping"):
            self.from_fixture(collision)
        beyond = json.loads(json.dumps(original))
        beyond["instances"][0]["registers"][0]["offset"] = "0x1000"
        with self.assertRaisesRegex(address_map.AddressMapError, "bounds"):
            self.from_fixture(beyond)

    def test_no_axi_evidence_is_not_coverage(self):
        catalog = self.from_fixture(self.fixture())
        missing = address_map.observe(catalog, [], complete_capture=False)
        self.assertTrue(all(r["observations"]["observation_status"] == "unmeasured"
                            for r in missing["regions"]))
        r = next(r for r in missing["regions"] if r["name"] == "boot.reset_ctrl")
        self.assertEqual(r["registers"][0]["observations"]["status"], "unmeasured")
        empty = address_map.observe(catalog, [], complete_capture=True)
        r = next(r for r in empty["regions"] if r["name"] == "boot.reset_ctrl")
        self.assertEqual(r["registers"][0]["observations"]["status"], "not_accessed")

    def test_only_accepted_real_initiator_traffic_counts(self):
        catalog = self.from_fixture(self.fixture())
        base = "0x40020000"
        def tx(*, role="initiator", plane="config", status="complete", response="0x0"):
            return {"role": role, "plane": plane, "address": base, "operation": "write",
                    "status": status, "response": response, "request": {"size": "0x2"},
                    "expected_beats": 1}
        counted = address_map.observe(catalog, [tx(), tx(role="link"), tx(plane="data")],
                                      complete_capture=True)
        reg = next(r for r in counted["regions"] if r["name"] == "boot.reset_ctrl")
        self.assertEqual(reg["observations"]["writes_ok"], 1)
        self.assertEqual(reg["registers"][0]["observations"]["completed"], 1)
        self.assertEqual(reg["observations"]["observation_status"], "observed_complete")
        failed = address_map.observe(catalog, [tx(response="0x2")], complete_capture=True)
        reg = next(r for r in failed["regions"] if r["name"] == "boot.reset_ctrl")
        self.assertEqual(reg["observations"]["observation_status"], "incomplete_or_error")


if __name__ == "__main__":
    unittest.main()
