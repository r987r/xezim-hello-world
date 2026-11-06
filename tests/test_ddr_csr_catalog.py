"""DDR-B pinned LiteDRAM/LiteX CSR import and variant address-map tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
import address_map
import ddr_chip
from ddr_csr_catalog import DdrCsrError, generate


class NativeDdrCsrTests(unittest.TestCase):
    def setUp(self):
        self.cfg=yaml.safe_load((ROOT/"config/soc.yaml").read_text())
        self.real=ddr_chip.variant_configuration(self.cfg)
        self.native={
            "csr_registers":{
                "ddrctrl_init_done":{"addr":0x2000,"size":1,"type":"rw"},
                "ddrctrl_init_error":{"addr":0x2004,"size":1,"type":"rw"},
                "sdram_dfii_control":{"addr":0x2008,"size":1,"type":"rw"},
                "sdram_dfii_pi0_command_issue":{"addr":0x200c,"size":1,"type":"rw"},
                "sdram_dfii_pi0_wrdata":{"addr":0x2010,"size":2,"type":"rw"},
                "ddrctrl_status":{"addr":0x2018,"size":1,"type":"ro"},
                "foreign_unrouted":{"addr":0xa000,"size":1,"type":"rw"},
            }
        }
        self.transport={
            "target_csr":"memory0.ctrl",
            "controller":"memory0.ddr0",
            "config_plane":"global_config -> memory0.local_config",
            "config_base":0x40030000,
            "configured_window_bytes":16384,
            "window_bytes":16384,
            "generated_wb_base":0x2000,
            "actions":[{"csr":name} for name in
                       ("ddrctrl_init_done","ddrctrl_init_error",
                        "sdram_dfii_control","sdram_dfii_pi0_command_issue")]
        }

    def generate(self,native=None,transport=None,variant=None):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            config=root/"soc.yaml"
            csr=root/"csr.json"
            steps=root/"init.json"
            output=root/"ddr-csr-map.json"
            config.write_text(yaml.safe_dump(variant or self.real))
            csr.write_text(json.dumps(self.native if native is None else native))
            steps.write_text(json.dumps(self.transport if transport is None else transport))
            generated=generate(config,csr,steps,output)
            merged=address_map.build(config,csr_path=output,variant="ddr_real")
            return generated,merged

    def test_full_variant_and_native_multiword_registers(self):
        generated,merged=self.generate()
        self.assertEqual(generated["register_count"],7)
        self.assertEqual(generated["native_unmapped_registers"],["foreign_unrouted"])
        self.assertEqual(len(merged["regions"]),14)
        ctrl=next(r for r in merged["regions"] if r["name"]=="memory0.ctrl")
        self.assertEqual((ctrl["base"],ctrl["size"]),("0x40030000","0x4000"))
        self.assertEqual([r["address"] for r in ctrl["registers"]],
                         ["0x40030000","0x40030004","0x40030008","0x4003000c",
                          "0x40030010","0x40030014","0x40030018"])
        self.assertEqual(ctrl["registers"][4]["name"],"sdram_dfii_pi0_wrdata[0]")
        self.assertEqual(ctrl["registers"][5]["name"],"sdram_dfii_pi0_wrdata[1]")
        self.assertEqual(ctrl["registers"][-1]["access"],"r")
        self.assertFalse(any(r["fields"] for r in ctrl["registers"]))
        self.assertTrue(all(r["reset"] is None for r in ctrl["registers"]))
        self.assertTrue(all(r["definition_status"] ==
                            "native_LiteDRAM_generated_CSR_not_bus_coverage"
                            for r in ctrl["registers"]))
        ddr=next(r for r in merged["regions"] if r["name"]=="memory0.ddr0")
        self.assertEqual(ddr["size"],"0x40000000")
        self.assertEqual(ddr["modeled_capacity_bytes"],32*1024*1024)
        self.assertEqual(ddr["modeled_backing_declared"],"litedram_sim")
        default={r["name"]:r for r in address_map.build()["regions"]}
        self.assertEqual(default["memory0.ctrl"]["size"],"0x1000")
        self.assertEqual(default["memory0.ddr0"]["modeled_capacity_bytes"],65536)

    def test_native_registers_are_not_traffic_evidence(self):
        _,merged=self.generate()
        missing=address_map.observe(merged,[],complete_capture=True)
        ctrl=next(r for r in missing["regions"] if r["name"]=="memory0.ctrl")
        self.assertEqual(ctrl["observations"]["observation_status"],"not_accessed")
        self.assertTrue(all(r["observations"]["status"]=="not_accessed"
                            for r in ctrl["registers"]))
        counted=address_map.observe(merged,[{
            "role":"initiator","plane":"config","address":"0x40030008",
            "operation":"write","status":"complete","response":"0x0",
            "request":{"size":2},"expected_beats":1,
        }],complete_capture=True)
        ctrl=next(r for r in counted["regions"] if r["name"]=="memory0.ctrl")
        self.assertEqual(ctrl["observations"]["writes_ok"],1)
        self.assertEqual(sum(r["observations"]["completed"] for r in ctrl["registers"]),1)

    def test_reject_duplicate_missing_invalid_vendor_registers(self):
        native=copy.deepcopy(self.native)
        native["csr_registers"]["ddrctrl_init_error"]["addr"]=0x2000
        with self.assertRaisesRegex(DdrCsrError,"overlapping"):
            self.generate(native=native)
        native=copy.deepcopy(self.native)
        del native["csr_registers"]["ddrctrl_init_done"]
        with self.assertRaisesRegex(DdrCsrError,"required"):
            self.generate(native=native)
        native=copy.deepcopy(self.native)
        native["csr_registers"]["ddrctrl_init_done"]["type"]="invalid"
        with self.assertRaisesRegex(DdrCsrError,"access"):
            self.generate(native=native)
        native=copy.deepcopy(self.native)
        native["csr_registers"]["ddrctrl_init_done"]["size"]=0
        with self.assertRaisesRegex(DdrCsrError,"word size"):
            self.generate(native=native)

    def test_reject_stale_and_incompatible_variant(self):
        broken=copy.deepcopy(self.real)
        broken["address_map"]["config"][-1]["size"]="0x2000"
        with self.assertRaises((DdrCsrError,address_map.AddressMapError)):
            self.generate(variant=broken)
        transport=copy.deepcopy(self.transport)
        transport["generated_wb_base"]=0x4000
        with self.assertRaisesRegex(DdrCsrError,"required"):
            self.generate(transport=transport)
        transport=copy.deepcopy(self.transport)
        transport["window_bytes"]=4096
        with self.assertRaisesRegex(DdrCsrError,"aperture"):
            self.generate(transport=transport)
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            config=d/"soc.yaml"
            config.write_text(yaml.safe_dump(self.real))
            csr=d/"csr.json";csr.write_text(json.dumps(self.native))
            contract=d/"init.json";contract.write_text(json.dumps(self.transport))
            catalog=d/"map.json";generate(config,csr,contract,catalog)
            config.write_text(config.read_text()+"\n# Untracked variant drift\n")
            with self.assertRaisesRegex(address_map.AddressMapError,"stale/foreign"):
                address_map.build(config,csr_path=catalog,variant="ddr_real")


if __name__=="__main__":
    unittest.main()
