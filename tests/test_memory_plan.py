"""Cross-check virtual Python plans with runtime C allocator physical layout."""
from pathlib import Path
import copy
import unittest
import yaml
from tools.memory_plan import configured_regions, validate_cpu_allocation, VirtualRegion

ROOT=Path(__file__).resolve().parents[1]

class MemoryPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg=yaml.safe_load((ROOT/"config/soc.yaml").read_text())

    def test_configured_models_and_boot_live_are_disjoint(self):
        regions=configured_regions(self.cfg)
        self.assertEqual(regions["compute0.sram.descriptors"].base,0x10001000)
        self.assertEqual(regions["compute0.sram.payload"].base,0x10002000)
        self.assertEqual(regions["memory0.ddr0"].base,0x140000100)
        self.assertEqual(regions["memory0.hbm0"].base,0x100000100)
        self.assertEqual(regions["memory0.ddr0"].capacity,65536-256)
        self.assertFalse(regions["memory0.ddr0"].cpu_visible)
        for a in regions.values():
            for b in regions.values():
                if a is b:
                    continue
                self.assertFalse(max(a.base,b.base)<min(a.base+a.capacity,b.base+b.capacity),
                                 (a.name,b.name))

    def test_python_plan_matches_c_physical_addresses(self):
        regions=configured_regions(self.cfg)
        src=regions["compute0.sram.payload"].allocate(64,64,owner="CPU0",phase="run")
        desc=regions["compute0.sram.descriptors"].allocate(32,32,owner="CPU0",phase="run")
        ddr=regions["memory0.ddr0"].allocate(64,64,owner="CPU0_DMA",phase="run")
        hbm=regions["memory0.hbm0"].allocate(64,64,owner="CPU0_DMA",phase="run")
        self.assertEqual([a.phys for a in (src,desc,ddr,hbm)],
                         [0x10002000,0x10001000,0x140000100,0x100000100])
        for item in (src,desc,ddr,hbm):
            validate_cpu_allocation(item.phys,item)
        with self.assertRaises(AssertionError):
            validate_cpu_allocation(ddr.phys+64,ddr)
        with self.assertRaises(RuntimeError):
            regions["memory0.ddr0"].release(ddr,consumers_quiesced=False)
        regions["memory0.ddr0"].release(ddr,consumers_quiesced=True)
        with self.assertRaises(RuntimeError):
            regions["memory0.ddr0"].release(ddr,consumers_quiesced=True)
        newer=regions["memory0.ddr0"].allocate(64,64,owner="CPU0_DMA",phase="run")
        self.assertEqual(newer.phys,ddr.phys)
        self.assertNotEqual(newer.token,ddr.token)
        with self.assertRaises(RuntimeError):
            regions["memory0.ddr0"].release(ddr,consumers_quiesced=True)

    def test_live_boot_and_dma_only_never_alias_policy(self):
        live=configured_regions(self.cfg,profile="boot_live")
        only=configured_regions(self.cfg,profile="dma_only")
        self.assertEqual(live["compute0.sram.descriptors"].base,0x10001000)
        self.assertEqual(only["compute0.sram.descriptors"].base,0x10000000)
        self.assertNotIn("compute0.sram.boot_scratch",only)

    def test_overflow_alignment_stale_and_relocated(self):
        cfg=copy.deepcopy(self.cfg)
        next(r for r in cfg["address_map"]["data"]
             if r["name"]=="compute0.sram")["base"]="0x12000000"
        regions=configured_regions(cfg)
        self.assertEqual(regions["compute0.sram.payload"].base,0x12002000)
        d=regions["memory0.ddr0"]
        with self.assertRaises(ValueError):
            d.allocate(1,3,owner="CPU0",phase="run")
        with self.assertRaises(ValueError):
            d.allocate(1,8,owner="",phase="run")
        with self.assertRaises(MemoryError):
            d.allocate(1<<20,64,owner="CPU0",phase="run")
        a=d.allocate(4,4,owner="CPU0",phase="run")
        with self.assertRaises(RuntimeError):
            d.reset(consumers_quiesced=False)
        d.reset(consumers_quiesced=True)
        with self.assertRaises(RuntimeError):
            d.release(a,consumers_quiesced=True)
        with self.assertRaises(ValueError):
            VirtualRegion("bad","ddr",(1<<64)-4,1024,False)
        with self.assertRaises(ValueError):
            VirtualRegion("bad","hbm",0,1024,True)
