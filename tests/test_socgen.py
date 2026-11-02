import copy
import json
import re
from pathlib import Path
import sys
import tempfile
import unittest
import yaml
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import socgen
import diagram_gen
import generate


class SocConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=yaml.safe_load((ROOT/'config/soc.yaml').read_text())

    def test_baseline_two_different_memories_and_cpus(self):
        m=socgen.validate(copy.deepcopy(self.base))
        self.assertEqual(m['ingress'],2)
        self.assertEqual([x['name'] for x in m['targets']],['memory0.hbm0','memory0.ddr0'])
        self.assertEqual([x['kind'] for x in m['targets']],['hbm','ddr'])
        self.assertEqual([x['base'] for x in m['targets']],[0x100000000,0x140000000])
        self.assertEqual([x['ip'] for x in m['cpu_instances']],['picorv32','serv'])
        self.assertEqual(m['common_dma'],'pulp_idma')
        self.assertEqual(len(m['subsystems']),3)

    def test_deterministic_generation_and_noc_ir(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'memory'
            cfg=ROOT/'config/soc.yaml'
            socgen.run(cfg,out)
            first=(out/'memory_tb.sv').read_bytes()
            manifest=json.loads((out/'manifest.json').read_text())
            ir=json.loads((out.parent/'noc/fabric_ir.json').read_text())
            socgen.run(cfg,out)
            self.assertEqual((out/'memory_tb.sv').read_bytes(),first)
            self.assertIn(b'axi_crossbar',first)
            self.assertIn(b'axi_memory_target_model',first)
            self.assertIn(b'N_IN = 2',first)
            self.assertEqual(manifest['targets'][1]['sim_pipeline'],True)
            self.assertEqual(ir['memory']['targets'],['memory0.hbm0','memory0.ddr0'])
            self.assertEqual(ir['fabrics']['global_data']['backend'],'floonoc')
            self.assertFalse(ir['fabrics']['global_data']['emitter_available'])

    def test_boot_generator_uses_real_cpu_programs(self):
        import bootgen
        fw = bootgen.build(copy.deepcopy(self.base))
        self.assertEqual(fw['addresses']['bootrom'], 0)
        self.assertEqual(fw['addresses']['sram0'], 0x10000000)
        self.assertEqual(fw['addresses']['sram1'], 0x11000000)
        self.assertEqual(fw['addresses']['reset_ctrl'], 0x40020000)
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / 'boot'
            bootgen.emit(self.base, out)
            words = [int(w, 16) for w in (out/'bootrom.hex').read_text().split()]
            flash = [int(w, 16) for w in (out/'flash.hex').read_text().split()]
            self.assertEqual(words[0], 0x200002b7)  # LUI t0, FLASH_BASE
            self.assertEqual(words[-1], 0x00028067)  # JALR x0, 0(t0)
            self.assertEqual(len(flash), 128)
            self.assertNotEqual(flash[0], 0)
            self.assertNotEqual(flash[64], 0)
            self.assertEqual(flash[4], 0)
            self.assertEqual(json.loads((out/'manifest.json').read_text())['sram_initialization'],
                             'none: CPU0 copies both images with AXI-Lite stores')

    def test_boot_missing_reset_controller_rejected(self):
        doc = copy.deepcopy(self.base)
        doc['address_map']['config'] = [r for r in doc['address_map']['config']
                                         if r['name'] != 'boot.reset_ctrl']
        with self.assertRaisesRegex(socgen.ConfigError, 'missing boot.reset_ctrl'):
            socgen.validate(doc)


    def test_overlap_rejected(self):
        doc=copy.deepcopy(self.base)
        doc['address_map']['data'][3]['base']='0x100000000'
        with self.assertRaisesRegex(socgen.ConfigError,'overlap'): socgen.validate(doc)

    def test_unknown_subsystem_rejected(self):
        doc=copy.deepcopy(self.base)
        doc['subsystems'][0]['type']='typo'
        with self.assertRaisesRegex(socgen.ConfigError,'unknown subsystem'): socgen.validate(doc)

    def test_changed_ingress_requires_agent_count(self):
        doc=copy.deepcopy(self.base)
        doc['subsystem_types']['memory']['data_ingress_ports']=3
        with self.assertRaisesRegex(socgen.ConfigError,'master agents'): socgen.validate(doc)

    def test_extra_compute_needs_no_new_memory_sv(self):
        doc=copy.deepcopy(self.base)
        doc['subsystems'].append({'name':'compute2','type':'compute','cpu':{'ip':'serv','bus':'wishbone','adapter':'serv_wishbone'}})
        doc['networks']['global_config']['reachable_subsystems'].append('compute2')
        m=socgen.validate(doc)
        self.assertEqual(len(m['subsystems']),4)
        self.assertEqual(len(m['targets']),2)

    def test_missing_output_target_rejected(self):
        doc=copy.deepcopy(self.base)
        doc['networks']['global_data']['outputs'][1]['target']='missing.ddr'
        with self.assertRaisesRegex(socgen.ConfigError,'missing target'): socgen.validate(doc)

    def test_wrong_cpu_adapter_rejected(self):
        doc=copy.deepcopy(self.base)
        doc['subsystems'][1]['cpu']['adapter']='picorv32_axi'
        with self.assertRaisesRegex(socgen.ConfigError,'incorrect bus/adapter'): socgen.validate(doc)

    def test_unknown_noc_backend_rejected(self):
        doc=copy.deepcopy(self.base)
        doc['fabrics']['global_data']['backend']='unknown'
        with self.assertRaisesRegex(socgen.ConfigError,'unknown NoC backend'): socgen.validate(doc)

    def test_noc_backend_replacement_needs_implementation(self):
        doc=copy.deepcopy(self.base)
        doc['fabrics']['memory_data']['backend']='pulp_axi'
        with self.assertRaisesRegex(socgen.ConfigError,'No RTL generator implemented'): socgen.validate(doc)

    def test_unknown_controller_or_model_rejected(self):
        doc=copy.deepcopy(self.base)
        doc['memory_targets'][0]['controller']='vendor_hbm'
        with self.assertRaisesRegex(socgen.ConfigError,'unsupported hbm controller'): socgen.validate(doc)
        doc=copy.deepcopy(self.base)
        doc['memory_targets'][1]['simulation']['backend']='litedram'
        with self.assertRaisesRegex(socgen.ConfigError,'only axi_ram behavioral'): socgen.validate(doc)

    def test_config_unreachable_rejected(self):
        doc=copy.deepcopy(self.base)
        doc['networks']['global_config']['reachable_subsystems'].remove('compute1')
        with self.assertRaisesRegex(socgen.ConfigError,'each subsystem exactly once'): socgen.validate(doc)

    def test_pin_present_for_real_ip(self):
        locked=yaml.safe_load((ROOT/'config/ip.lock.yaml').read_text())['third_party']
        for ip in ('verilog_axi','picorv32','serv','pulp_idma','litedram','hisa_hbm','pulp_axi'):
            self.assertIn(ip,locked)
            self.assertRegex(locked[ip]['commit'],r'^[a-f0-9]{40}$')

    def test_diagram_generation_and_readme_markers(self):
        meta = socgen.validate(copy.deepcopy(self.base))
        with tempfile.TemporaryDirectory() as tmp:
            diagrams = diagram_gen.render(copy.deepcopy(self.base), meta, Path(tmp) / "diagrams", ROOT / "gen/noc/floonoc")
            for name in ("architecture", "rtl-connectivity", "verification", "boot", "noc-hierarchy"):
                self.assertIn("flowchart", diagrams[name])
                self.assertTrue((Path(tmp)/"diagrams"/f"{name}.mmd").is_file())
            self.assertIn("picorv32", diagrams["architecture"])
            self.assertIn("memory0.hbm0", diagrams["architecture"])
            self.assertIn("memory_tb", diagrams["rtl-connectivity"])
            self.assertIn("memory_fabric", diagrams["verification"])
            self.assertIn("subsystems/compute0", diagrams)
            self.assertIn("subsystems/compute1", diagrams)
            self.assertIn("subsystems/memory0", diagrams)
            for name in diagrams:
                image_path = Path(tmp) / "diagrams" / f"{name}.svg"
                self.assertTrue(image_path.is_file(), image_path)
                self.assertEqual(ET.parse(image_path).getroot().tag,
                                 "{http://www.w3.org/2000/svg}svg")
                self.assertIn(f"{Path(name).name}.svg", (Path(tmp)/"diagrams"/f"{name}.md").read_text())
            graphs = json.loads((Path(tmp)/"diagrams"/"graphs.json").read_text())
            for section in ("architecture", "rtl_connectivity"):
                nodes = {n["id"] for n in graphs[section]["nodes"]}
                self.assertTrue(all(e["from"] in nodes and e["to"] in nodes
                                    for e in graphs[section]["connections"]))
            self.assertIn(generate.START, (ROOT/"README.md").read_text())
            self.assertIn(generate.END, (ROOT/"README.md").read_text())

    def test_readme_embeds_real_images_that_exist(self):
        readme = (ROOT / "README.md").read_text()
        section = readme.split(generate.START, 1)[1].split(generate.END, 1)[0]
        image_paths = re.findall(r"!\[[^]]+\]\((gen/diagrams/[^)]+\.svg)\)", section)
        self.assertEqual(len(image_paths), 5)
        for relative in image_paths:
            path = ROOT / relative
            self.assertTrue(path.is_file(), f"missing README image {relative}")
            self.assertEqual(ET.parse(path).getroot().tag,
                             "{http://www.w3.org/2000/svg}svg")
        for name in ("architecture", "rtl-connectivity", "verification", "boot"):
            self.assertIn(f"gen/diagrams/{name}.svg", image_paths)
            self.assertTrue((ROOT / "gen" / "diagrams" / f"{name}.mmd").is_file())

    def test_complete_generated_tree_and_stale_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/"gen"
            readme = Path(tmp)/"README.md"
            readme.write_text((ROOT/"README.md").read_text())
            cfg = ROOT/"config/soc.yaml"
            self.assertEqual(generate.execute(cfg,out,readme),0)
            first = generate.tree_files(out)
            self.assertEqual(generate.execute(cfg,out,readme,check=True),0)
            (out/"obsolete.sv").write_text("not generated anymore")
            self.assertEqual(generate.execute(cfg,out,readme,check=True),1)
            self.assertEqual(generate.execute(cfg,out,readme),0)
            self.assertFalse((out/"obsolete.sv").exists())
            self.assertEqual(first, generate.tree_files(out))
            self.assertEqual(generate.execute(cfg,out,readme,check=True),0)
            (out/"memory"/"memory_tb.sv").write_text("incorrect")
            self.assertEqual(generate.execute(cfg,out,readme,check=True),1)
            self.assertEqual(generate.execute(cfg,out,readme),0)
            self.assertEqual(first, generate.tree_files(out))

    def test_stale_subsystem_diagram_deleted_when_configuration_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/"gen"
            readme = Path(tmp)/"README.md"
            readme.write_text((ROOT/"README.md").read_text())
            cfg_path = Path(tmp)/"soc.yaml"
            doc = copy.deepcopy(self.base)
            doc["subsystems"].append({"name":"compute2", "type":"compute", "cpu":
                                      {"ip":"serv", "bus":"wishbone", "adapter":"serv_wishbone"}})
            doc["networks"]["global_config"]["reachable_subsystems"].append("compute2")
            # Each new compute subsystem supplies its own mapped SRAM
            # and CSR apertures; FlooGen derives the NoC wires automatically.
            doc["address_map"]["data"].append({
                "name": "compute2.sram", "base": "0x12000000", "size": "0x00100000"})
            doc["address_map"]["config"].append({
                "name": "compute2.dma", "base": "0x40040000", "size": "0x10000"})
            cfg_path.write_text(yaml.safe_dump(doc,sort_keys=False))
            self.assertEqual(generate.execute(cfg_path,out,readme),0)
            extra = out/"diagrams"/"subsystems"/"compute2.mmd"
            self.assertTrue(extra.exists())
            extra_svg = out / "diagrams" / "subsystems" / "compute2.svg"
            self.assertTrue(extra_svg.exists())
            cfg_path.write_text(yaml.safe_dump(self.base,sort_keys=False))
            self.assertEqual(generate.execute(cfg_path,out,readme,check=True),1)
            self.assertEqual(generate.execute(cfg_path,out,readme),0)
            self.assertFalse(extra.exists())
            self.assertFalse(extra_svg.exists())
            self.assertEqual(generate.execute(cfg_path,out,readme,check=True),0)

    def test_unmarked_gen_tree_is_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/"gen"
            out.mkdir()
            (out/"valuable.txt").write_text("keep me")
            readme = Path(tmp)/"README.md"
            readme.write_text((ROOT/"README.md").read_text())
            with self.assertRaisesRegex(generate.GenerationError,"unmarked"):
                generate.execute(ROOT/"config/soc.yaml",out,readme)
            self.assertEqual((out/"valuable.txt").read_text(),"keep me")


if __name__=='__main__': unittest.main()
