"""P2: source-derived per-run NoC/actor provenance, never fake elaboration."""
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

import variant_connectivity as vc
from noc_diagrams import read_generated_nocs, diagram_gen_metadata


class VariantConnectivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg=yaml.safe_load((ROOT/"config/soc.yaml").read_text())
        cls.networks=read_generated_nocs(ROOT/"gen/noc/floonoc")
        cls.graph=diagram_gen_metadata(cls.cfg,cls.networks)
        cls.chip=json.loads((ROOT/"gen/chip/manifest.json").read_text())
        cls.monitors=json.loads((ROOT/"gen/supernoc/axi_monitors.json").read_text())["monitors"]
        cls.actors=cls.chip["axi_actors"]
        cls.super=ROOT/"gen/supernoc/soc_noc.sv"
        cls.top=ROOT/"gen/chip/soc_top.sv"
        cls.tb=ROOT/"gen/chip/full_chip_tb.sv"

    def scenario(self):
        return {
            "top":"full_chip_tb",
            "sources":[str(self.top),str(self.tb),str(self.super)],
            "report":{"axi":{
                "catalog":"gen/supernoc/axi_monitors.json",
                "actors":"gen/chip/manifest.json",
            }},
        }

    def test_default_catalog_has_all_taps_and_reserved_peripherals(self):
        with tempfile.TemporaryDirectory() as out:
            inventory,graph=vc.collect(ROOT,"chip-boot",self.scenario(),Path(out))
        self.assertEqual(inventory["chip_variant"],"checked_in_default")
        self.assertEqual(inventory["summary"]["meshes"],12)
        self.assertEqual(inventory["summary"]["routers"],68)
        self.assertEqual(inventory["summary"]["monitors"],len(self.monitors))
        self.assertFalse(inventory["elaborated"])
        self.assertFalse(inventory["observed_protocol_traffic"])
        self.assertEqual(inventory["summary"]["declared_live_peripherals"],0)
        self.assertEqual(inventory["peripherals"]["pcie0"]["data_status"],"reserved_no_packet_engine")
        self.assertEqual(inventory["peripherals"]["ethernet0"]["csr_status"],"error_responder")
        self.assertTrue(all(b["monitor_prefix"] and b["max_pending_reads_budget"]>0
                            and b["fabric_shared_MaxTxns"]>0 for b in inventory["boundaries"]))
        self.assertTrue(all(b["observed_requests"] is None for b in inventory["boundaries"]))
        self.assertIn("not_elaborated",graph["status"])

    def test_source_diagram_visualizes_generated_links_and_escapes_names(self):
        with tempfile.TemporaryDirectory() as out:
            inventory,graph=vc.collect(ROOT,"chip-boot",self.scenario(),Path(out))
        page=vc.render_html(inventory,graph)
        for token in ("<svg","pcie0","ethernet0","global_data","global_config",
                      "Source-only","variant-chip-manifest.json","AXI monitor"):
            self.assertIn(token,page)
        tampered=copy.deepcopy(inventory)
        tampered["peripherals"]["pcie0"]["ip"]="<script>alert(1)</script>"
        html=vc.render_html(tampered,graph)
        self.assertNotIn("<script>",html)
        self.assertIn("&lt;script&gt;",html)
        publisher=(ROOT/"tools/publish_site.py").read_text()
        self.assertIn("variant AXI monitor inventory differs from accepted per-run report",publisher)
        self.assertIn("variant-architecture.html",publisher)

    def test_reconcile_source_declared_pcie_without_claiming_bare_mgmt_link(self):
        chip=copy.deepcopy(self.chip)
        actors=copy.deepcopy(self.actors)
        p=next(s for s in chip["peripheral_subsystems"] if s["name"]=="pcie0")
        p["rtl_attachment"]="live_pcie_tlp_axi_bridge"
        actors["pcie0_local_data.host"]={"kind":"rtl_pcie_bridge","label":"Pinned PCIe bridge"}
        # Resolve initiator name from the SoC contract rather than assume host.
        actual=next(s for s in self.cfg["subsystems"] if s["name"]=="pcie0")
        endpoint="pcie0_local_data."+actual["data_initiator"]
        actors.pop("pcie0_local_data.host",None)
        actors[endpoint]={"kind":"rtl_pcie_bridge","label":"Pinned PCIe bridge"}
        graph=copy.deepcopy(self.graph)
        states=vc.reconcile(graph,self.cfg,chip,actors,self.monitors)
        self.assertEqual(states["pcie0"]["data_status"],"generated_source_declared_live_not_elaborated")
        self.assertEqual(vc.declared_edge(graph,"pcie0.ip",endpoint)["status"],
                         "generated_variant_declared_live_not_elaborated")
        mgmt="pcie0_local_config."+actual["config_initiator"]
        self.assertEqual(vc.declared_edge(graph,"pcie0.ip",mgmt)["status"],
                         "planned_integration")

    def test_ethernet_config_csr_live_and_monitor_required(self):
        chip=copy.deepcopy(self.chip);actors=copy.deepcopy(self.actors)
        s=next(s for s in self.cfg["subsystems"] if s["name"]=="ethernet0")
        record=next(s for s in chip["peripheral_subsystems"] if s["name"]=="ethernet0")
        record["rtl_attachment"]="live_ethernet_gmii_queue_axi_mvp"
        record["csr_attachment"]="live_ethernet_queue_axi4_lite"
        packet="ethernet0_local_data."+s["data_initiator"]
        csr="ethernet0_local_config.controller_regs"
        actors[packet]={"kind":"rtl_ethernet_dma","label":"GMII MAC + DMA"}
        actors[csr]={"kind":"rtl_registers","label":"Queue AXI-Lite CSR"}
        graph=copy.deepcopy(self.graph)
        states=vc.reconcile(graph,self.cfg,chip,actors,self.monitors)
        self.assertEqual(states["ethernet0"]["csr_status"],"generated_source_declared_live_not_elaborated")
        self.assertEqual(vc.declared_edge(graph,csr,"ethernet0.csr")["status"],
                         "generated_variant_declared_live_not_elaborated")
        with self.assertRaisesRegex(vc.VariantEvidenceError,"CSR missing AXI target monitor"):
            vc.reconcile(copy.deepcopy(self.graph),self.cfg,chip,actors,
                         [m for m in self.monitors if m["id"]!=csr])
        with self.assertRaisesRegex(vc.VariantEvidenceError,"no RTL actor declaration"):
            bad=copy.deepcopy(actors);bad[packet]={"kind":"reserved_idle"}
            vc.reconcile(copy.deepcopy(self.graph),self.cfg,chip,bad,self.monitors)

    def test_configured_gmii_tlp_dfi_source_metadata_is_not_observed(self):
        spec=self.scenario()
        spec["report"]["protocols"]={"sources":{
            "ethernet0.gmii_rx":{
                "protocol":"ethernet","clock_domain":"gmii_rx_clock",
                "role":"stimulus","implementation":"cocotbext_eth",
                "modeling":"vip_injected_to_rtl_mac"}
        }}
        with tempfile.TemporaryDirectory() as out:
            view,graph=vc.collect(ROOT,"chip-boot",spec,Path(out))
        self.assertEqual(view["summary"]["declared_non_axi_protocol_sources"],1)
        self.assertEqual(view["protocol_sources"][0]["id"],"ethernet0.gmii_rx")
        self.assertEqual(view["protocol_sources"][0]["source_status"],"declared_not_observed")
        self.assertIn("Declared native protocol monitors",vc.render_html(view,graph))
        self.assertIn("passing native protocol source differs",(
            ROOT/"tools/publish_site.py").read_text())

    def test_bad_selected_filelist_fails_before_simulator(self):
        plan=self.scenario()
        plan["sources"].remove(str(self.super))
        with tempfile.TemporaryDirectory() as out:
            with self.assertRaisesRegex(vc.VariantEvidenceError,"selected RTL file not in exact run filelist"):
                vc.collect(ROOT,"chip-boot",plan,Path(out))

    def test_source_manifest_mutation_fails_closed(self):
        wrong=copy.deepcopy(self.chip)
        wrong["peripheral_subsystems"].pop()
        with self.assertRaisesRegex(vc.VariantEvidenceError,"peripheral inventory"):
            vc.reconcile(copy.deepcopy(self.graph),self.cfg,wrong,self.actors,self.monitors)

    def test_real_ddr_source_graph_distinguished_from_default(self):
        chip=copy.deepcopy(self.chip)
        chip["real_ddr_controller"]=True
        graph=copy.deepcopy(self.graph)
        vc.reconcile(graph,self.cfg,chip,self.actors,self.monitors)
        self.assertEqual(vc.declared_edge(
            graph,"memory0_local_config.controller_regs","memory0.ctrl")["status"],
            "generated_variant_declared_live_not_elaborated")
        self.assertEqual(vc.declared_edge(
            graph,"memory0.internal_target_crossbar","memory0.ddr0")["status"],
            "generated_variant_declared_live_not_elaborated")

    def test_regression_publishes_before_simulator_and_no_phy_claims(self):
        src=(ROOT/"tools/regress.py").read_text()
        self.assertLess(src.index("publish_variant_connectivity(ROOT"),
                        src.index("run_process(command",src.index("publish_variant_connectivity(ROOT")))
        viewer=(ROOT/"tools/variant_connectivity.py").read_text()
        self.assertIn('"elaborated":False',viewer)
        self.assertIn('"observed_protocol_traffic":False',viewer)
        self.assertIn("behavioral PHY",viewer)


if __name__=="__main__":
    unittest.main()
