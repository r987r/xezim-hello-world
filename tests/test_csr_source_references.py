"""Source-only CSR catalog tests, dynamic subsystem discovery, fail-closed drift."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import address_map
from csr_source_references import SourceCatalogError, attach_sources
from pcie_source_registers import source_registers as pcie_source_registers, PcieSourceError


class SourceCsrTests(unittest.TestCase):
    def test_sources_are_crosschecked_and_not_marked_active(self):
        catalog = address_map.build()
        report = attach_sources(catalog)
        by_name = {r["name"]: r for r in catalog["regions"]}
        self.assertEqual({n for n in by_name if by_name[n]["plane"] == "config"},
                         {r["instance"] for r in report["instances"]})
        for name in ("compute0.dma", "compute1.dma"):
            r = by_name[name]
            self.assertEqual(len(r["source_registers"]), 4)
            self.assertEqual(r["registers"], [])
            self.assertEqual(r["source_status"], "source_only_attachment_not_qualified")
            head = next(v for v in r["source_registers"] if v["name"] == "head_lo")
            self.assertEqual(head["address"], r["base"])
            self.assertIsNone(head["reset"])
            command = next(v for v in r["source_registers"] if v["name"] == "command")
            self.assertEqual(command["write_semantics"], "one_shot_command")
            self.assertIn("submit", {x["name"] for x in command["fields"]})
        eth = by_name["ethernet0.ctrl"]
        self.assertGreaterEqual(len(eth["source_registers"]), 25)
        self.assertEqual(eth["registers"], [])
        enable = next(v for v in eth["source_registers"] if v["name"] == "enable")
        self.assertEqual(enable["address"], "0x40050008")
        self.assertEqual(enable["access"], "rw")
        self.assertEqual({x["name"] for x in enable["fields"]}, {"rx", "tx"})
        magic = next(v for v in eth["source_registers"] if v["name"] == "magic")
        self.assertEqual(magic["access"], "ro")
        irq = next(v for v in eth["source_registers"] if v["name"] == "irq_status")
        self.assertEqual(irq["write_semantics"], "write_one_to_clear")
        self.assertEqual(eth["source_provenance"]["header"], "sw/ethernet/eth_queue_abi.h")
        self.assertEqual({i["instance"] for i in report["gaps"]},
                         {"boot.reset_ctrl", "memory0.ctrl"})
        self.assertFalse(report["unacknowledged"])
        pcie=by_name["pcie0.ctrl"]
        self.assertEqual(len(pcie["source_registers"]), 22)
        self.assertEqual(pcie["registers"], [])
        self.assertEqual(next(x for x in pcie["source_registers"] if x["name"]=="wr_command")["address"],"0x40040014")
        self.assertEqual(next(x for x in pcie["source_registers"] if x["name"]=="bar0_aperture")["address"],"0x40041000")
        self.assertEqual(next(x for x in pcie["source_registers"] if x["name"]=="host_bar0")["fields"][0]["access"],"r")
        self.assertTrue(all(x["definition_status"]=="PCIe_source_reference_not_build_qualified" for x in pcie["source_registers"]))

    def _extend(self, name, subtype, ip=None):
        config = yaml.safe_load((ROOT / "config/soc.yaml").read_text())
        subsystem = {"name": name, "type": subtype}
        if ip:
            subsystem["ip"] = ip
        config["subsystems"].append(subsystem)
        config["address_map"]["config"].append(
            {"name": name + (".dma" if subtype == "compute" else ".ctrl"),
             "base": "0x40060000", "size": "0x10000"})
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "soc.yaml"
            cfg.write_text(yaml.safe_dump(config))
            # Exercise the source importer separately from RTL generation.
            # The regression generator must validate new subsystem connectivity.
            model = address_map.build()
            source = next(r for r in model["regions"]
                          if r["name"] == ("compute0.dma" if subtype == "compute"
                                          else "ethernet0.ctrl"))
            row = copy.deepcopy(source)
            row["name"] = config["address_map"]["config"][-1]["name"]
            row["owner"] = name
            row["base"] = "0x40060000"
            model["regions"].append(row)
            model["config_sha256"] = hashlib.sha256(cfg.read_bytes()).hexdigest()
            yield model, cfg

    def test_new_compute_inherits_source_without_name_allowlist(self):
        for model, cfg in self._extend("compute2", "compute"):
            coverage = attach_sources(model, config_path=cfg)
            region = next(x for x in model["regions"] if x["name"] == "compute2.dma")
            self.assertEqual(len(region["source_registers"]), 4)
            self.assertEqual(coverage["unacknowledged"], [])

    def test_new_ethernet_inherits_queue_source(self):
        for model, cfg in self._extend("ethernet1", "peripheral",
                                       ip="ethernet_queue_mac"):
            report = attach_sources(model, config_path=cfg)
            region = next(x for x in model["regions"] if x["name"] == "ethernet1.ctrl")
            self.assertGreaterEqual(len(region["source_registers"]), 25)
            self.assertEqual(region["source_status"],
                             "source_only_attachment_not_qualified")
            self.assertFalse(report["unacknowledged"])

    def test_registered_subsystem_without_csr_aperture_fails(self):
        config = yaml.safe_load((ROOT / "config/soc.yaml").read_text())
        config["subsystems"].append({"name": "compute2", "type": "compute"})
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "soc.yaml"
            path.write_text(yaml.safe_dump(config))
            model = address_map.build()
            model["config_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(SourceCatalogError,
                                        "lacks aperture: compute2.dma"):
                attach_sources(model, config_path=path)

    def test_new_unregistered_subsystem_fails_coverage_gate(self):
        for model, cfg in self._extend("mystery0", "peripheral", ip="new_unknown_ip"):
            with self.assertRaisesRegex(SourceCatalogError, "mystery0.ctrl"):
                attach_sources(model, config_path=cfg)

    def test_pcie_source_drift_fails_closed(self):
        rows, provenance = pcie_source_registers()
        self.assertEqual(len(rows), 22)
        self.assertTrue(provenance["rdl_sha256"])
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for relative in ("sw/pcie/pcie_requester.h",
                             "rtl/adapters/pcie_requester_axi_regs.sv",
                             "csr/rdl/pcie_endpoint_prelink_ctrl.rdl"):
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, root / relative)
            hdr = root / "sw/pcie/pcie_requester.h"
            hdr.write_text(hdr.read_text().replace(
                "SOC_PCIE_WR_STATUS = 0x18", "SOC_PCIE_WR_STATUS = 0x1c"))
            with self.assertRaises(PcieSourceError):
                pcie_source_registers(root)
            shutil.copy2(ROOT / "sw/pcie/pcie_requester.h", hdr)
            rdl = root / "csr/rdl/pcie_endpoint_prelink_ctrl.rdl"
            rdl.write_text(rdl.read_text().replace(
                "host_bar0 @0x1010", "host_bar0 @0x1020"))
            with self.assertRaises(PcieSourceError):
                pcie_source_registers(root)

    def test_header_rtl_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for relative in ("config/soc.yaml", "sw/dma/dma.h",
                             "sw/ethernet/eth_queue_abi.h",
                             "rtl/adapters/soc_dma_regs.sv",
                             "rtl/io/ethernet0/ethernet_queue_ctrl.sv",
                             "sw/pcie/pcie_requester.h",
                             "rtl/adapters/pcie_requester_axi_regs.sv",
                             "csr/rdl/pcie_endpoint_prelink_ctrl.rdl"):
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, root / relative)
            shutil.copytree(ROOT / "csr/source-registers",
                            root / "csr/source-registers")
            wrong = root / "sw/ethernet/eth_queue_abi.h"
            wrong.write_text(wrong.read_text().replace(
                "#define ETHQ_REG_ENABLE           0x08u",
                "#define ETHQ_REG_ENABLE           0xb0u"))
            with self.assertRaisesRegex(SourceCatalogError, "mismatch|disagree"):
                attach_sources(address_map.build(), root=root)


if __name__ == "__main__":
    unittest.main()
