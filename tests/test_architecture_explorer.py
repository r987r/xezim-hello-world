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
