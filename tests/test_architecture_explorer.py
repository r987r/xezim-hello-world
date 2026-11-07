"""Exercise 2D architecture hierarchy, not a flat list of unrelated blocks."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from design_explorer import catalog


class ArchitectureExplorerTests(unittest.TestCase):
    def setUp(self):
        self.graph=catalog(ROOT)
        self.script=(ROOT/"tools/templates/site_arch_explorer.js").read_text()
        self.markup=(ROOT/"tools/templates/site_explorer.html").read_text()

    def test_full_chip_has_subsystem_groups_and_global_meshes(self):
        groups={g["name"]:g for g in self.graph["groups"]}
        chip=[k for k in groups if k.endswith("_subsystem")]
        self.assertGreaterEqual(len(chip),3)
        for name in chip:
            sub=name.removesuffix("_subsystem")
            self.assertTrue(any(n.startswith(sub+"_") for n in groups))
        for fabric in ("global_data","global_config"):
            self.assertIn(fabric,groups)
        self.assertIn("Full chip",self.script)
        self.assertIn("subsystem",self.script)
        self.assertIn("network",self.script)

    def test_router_positions_and_real_links_preserved(self):
        nodes={n["id"] for n in self.graph["nodes"]}
        groups={g["name"]:g for g in self.graph["groups"]}
        router_total=0
        for name, group in groups.items():
            if (group.get("info") or {}).get("plane") not in ("data","config"):
                continue
            routers=[n for n in group["instances"] if ".router_" in n]
            router_total+=len(routers)
            self.assertEqual(len(routers),group["info"]["router_count"])
            for router in routers:
                self.assertIn(router,nodes)
                self.assertTrue(any(e["from"]["instance"]==router or
                                    e["to"]["instance"]==router
                                    for e in self.graph["edges"]))
        generated=json.loads((ROOT/'gen/noc/floonoc/manifest.json').read_text())['networks']
        self.assertEqual(router_total,sum(net['routers'] for net in generated.values()))
        self.assertIn("router_",self.script)
        self.assertIn("NI-to-router link",self.script)

    def test_single_canonical_2d_view_and_signal_detail(self):
        self.assertIn("__GRAPH_DATA__",self.markup)
        self.assertIn("__SIGNAL_DATA__",self.markup)
        self.assertIn("__ARCH_JS__",self.markup)
        self.assertIn("arch-crumbs",self.markup)
        self.assertIn("arch-svg",self.markup)
        self.assertIn("ex-signal-rows",self.markup)
        self.assertIn("arch-export",self.markup)
        self.assertNotIn("perspective:",self.markup)
        self.assertNotIn("THREE.",self.markup)
        self.assertIn("navigate",self.script)
        self.assertIn("function network(",self.script)

    def test_generated_peripheral_connections_visible_in_single_svg(self):
        import math
        import yaml
        import xml.etree.ElementTree as ET

        cfg=yaml.safe_load((ROOT/"config/soc.yaml").read_text())
        svg=ET.parse(ROOT/"gen/diagrams/noc-hierarchy.svg").getroot()
        lines=[e.attrib for e in svg.iter() if e.tag.endswith("polyline")]
        points={e["points"]:e for e in lines}
        periph=[s for s in cfg["subsystems"] if s["type"]=="peripheral"]
        rows=math.ceil(sum(s["type"]=="compute" for s in cfg["subsystems"])/2)
        gy=172+rows*285+32+len(periph)*270
        for i,sub in enumerate(periph):
            py=158+rows*285+i*270
            with self.subTest(peripheral=sub["name"]):
                expected=[
                    (f"250.0,{py+122}.0 250.0,{py+145}.0",True),
                    (f"630.0,{py+122}.0 630.0,{py+145}.0",False),
                    (f"1180.0,{py+122}.0 1180.0,{py+145}.0",False),
                ]
                for point,dashed in expected:
                    self.assertIn(point,points)
                    self.assertEqual("stroke-dasharray" in points[point],dashed)
                self.assertTrue(any(p.startswith(f"746.0,{py+180}.0 ")
                                    and p.endswith(f",{gy}.0") for p in points))
                self.assertTrue(any(p.startswith(f"830.0,{py+180}.0 ")
                                    and p.endswith(f",{gy}.0") for p in points))
        self.assertIn('class="topology-pan"',(ROOT/"tools/templates/site_index.html").read_text())
        self.assertIn("min-width:1050px",(ROOT/"tools/templates/site.html").read_text())
        self.assertIn("Math.max(.48",self.script)
        self.assertIn("PERIPHERAL SUBSYSTEM",self.script)

    def test_multi_subsystem_graph_is_not_hardcoded_in_viewer(self):
        # The renderer derives subtype membership from generated groups.
        self.assertIn('endsWith("_subsystem")',self.script)
        self.assertIn('new Map(g.groups',self.script)
        self.assertIn('function fullChip()',self.script)
        self.assertIn('for(const s of subs)',self.script)
        self.assertIn('const rtlBindings=',self.script)
        self.assertIn('rtlBindings[id]',self.script)
        self.assertNotIn('const preferred=',self.script)
        self.assertNotIn('moduleCandidates=',self.script)


if __name__=="__main__":
    unittest.main()
