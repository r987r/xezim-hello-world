"""Offline contract tests of the actual-public Pages surface gate."""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from check_published_site import validate


class PublicSiteTests(unittest.TestCase):
    def setUp(self):
        self.sha = "a" * 40
        self.site = {
            "source_sha": self.sha,
            "networks": {"net_data": {"routers": 2}},
            "tests": {"chip": {"engine": "verilator"}},
            "chip": {"top": "soc_top"},
            "entries": [],
        }
        self.fabric = {
            "summary": {"meshes": 1},
            "latency_table": {
                "units": "simulation_reference_clock_cycles",
                "rows": [{"route": "cpu-to-sram"}],
            },
            "matrix": [{"route": "cpu-to-sram"}],
        }
        self.graph = {
            "groups": [{"name": "net_data", "info": {"plane": "data", "router_count": 2}}],
            "nodes": [{"id": "compute0.cpu", "module": "soc_boundary"}],
        }
        self.rtl = {
            "producer": "slang",
            "fabric_contract": {
                "independent_planes": True, "resolved_networks": ["net_data"],
            },
            "modules": [
                {"name": "soc_top", "instances": [
                    {"name": "u_cpu_compute0", "module": "cpu_adapter"}]},
                {"name": "cpu_adapter", "instances": []},
            ],
        }
        self.bindings = {
            "compute0.cpu": {
                "status": "unique_root_instance",
                "instance": "u_cpu_compute0",
                "module": "cpu_adapter",
                "parsed_module_available": True,
                "evidence": "unique_name_correlated_slang_cst_not_elaborated",
            }
        }
        self.intents = {
            "chip": {"phases": {"init": [], "run": [], "check": []}}
        }
        self.html = {
            "runs": 'id="test-flow-plan" id="traffic-run" id="traffic-table"',
            "fabric": (
                'id="fabric-latency-table" id="fabric-interfaces" '
                'id="fabric-evidence-coverage"'),
            "explorer": (
                'id="arch-svg" id="ex-embedded-rtl-bindings" '
                'id="arch-embedded-protocol-links"'),
        }

    def check(self, **overrides):
        data = dict(
            expected_sha=self.sha,
            site=self.site,
            fabric=self.fabric,
            graph=self.graph,
            rtl=self.rtl,
            bindings=self.bindings,
            intents=self.intents,
            html=self.html,
        )
        data.update(overrides)
        return validate(**data)

    def test_valid_static_site_does_not_invent_optional_dfi_evidence(self):
        result = self.check()
        self.assertEqual(result["networks"], 1)
        self.assertEqual(result["routers"], 2)
        self.assertEqual(result["tests"], 1)
        self.assertEqual(result["real_fullchip_dfi_runs"], 0)

    def test_valid_real_fullchip_dfi_is_reported_but_not_hardcoded(self):
        site = copy.deepcopy(self.site)
        site["entries"] = [{
            "source_sha": self.sha, "passed": True,
            "target": "chip-ddr4-real",
            "protocol_links": {"capture_complete": True, "sources": [
                {"protocol": "dfi", "source": "memory0.ddr0.dfi",
                 "clock_domain": "ddr_source_clk", "count": 17,
                 "operations": {"act": 3, "rd": 7, "wr": 7}},
                {"protocol": "dfi", "source": "memory0.ddr0.bankmodel",
                 "clock_domain": "ddr_source_clk", "count": 2,
                 "operations": {"storage_write": 1, "read": 1}}
            ]},
        }]
        self.assertEqual(self.check(site=site)["real_fullchip_dfi_runs"], 1)

        incomplete = copy.deepcopy(site)
        incomplete["entries"][0]["protocol_links"]["capture_complete"] = False
        with self.assertRaisesRegex(ValueError, "incomplete DFI capture"):
            self.check(site=incomplete)
        missing_act = copy.deepcopy(site)
        source = missing_act["entries"][0]["protocol_links"]["sources"][0]
        source["operations"] = {"rd": 10, "wr": 7}
        with self.assertRaisesRegex(ValueError, "ACT/RD/WR"):
            self.check(site=missing_act)
        missing_bank = copy.deepcopy(site)
        source = missing_bank["entries"][0]["protocol_links"]["sources"][1]
        source["operations"] = {"read": 2}
        with self.assertRaisesRegex(ValueError, "BankModel write"):
            self.check(site=missing_bank)
        failed = copy.deepcopy(site)
        failed["entries"][0]["passed"] = False
        self.assertEqual(self.check(site=failed)["real_fullchip_dfi_runs"], 0)

    def test_reject_stale_sha(self):
        site = copy.deepcopy(self.site)
        site["source_sha"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "source SHA"):
            self.check(site=site)

    def test_reject_fabric_and_architecture_source_drift(self):
        graph = copy.deepcopy(self.graph)
        graph["groups"][0]["info"]["router_count"] = 3
        with self.assertRaisesRegex(ValueError, "router count"):
            self.check(graph=graph)
        fabric = copy.deepcopy(self.fabric)
        fabric["summary"]["meshes"] = 3
        with self.assertRaisesRegex(ValueError, "Fabric network count"):
            self.check(fabric=fabric)
        rtl = copy.deepcopy(self.rtl)
        rtl["fabric_contract"]["resolved_networks"] = []
        with self.assertRaisesRegex(ValueError, "compiler-parsed Fabric"):
            self.check(rtl=rtl)

    def test_reject_missing_or_faked_rtl_binding(self):
        with self.assertRaisesRegex(ValueError, "binding inventory"):
            self.check(bindings={})
        bad = copy.deepcopy(self.bindings)
        bad["compute0.cpu"]["module"] = "invented_cpu"
        with self.assertRaisesRegex(ValueError, "root instance changed"):
            self.check(bindings=bad)
        opaque = {"compute0.cpu": {"status": "no_root_instance_match"}}
        self.assertEqual(self.check(bindings=opaque)["networks"], 1)

    def test_reject_missing_test_flow_or_browser(self):
        with self.assertRaisesRegex(ValueError, "intended test flow"):
            self.check(intents={})
        intents = {"chip": {"phases": {"init": [], "run": []}}}
        with self.assertRaisesRegex(ValueError, "intended test phases"):
            self.check(intents=intents)
        html = copy.deepcopy(self.html)
        html["runs"] = ""
        with self.assertRaisesRegex(ValueError, "public runs page"):
            self.check(html=html)

    def test_reject_unqualified_capture_sha(self):
        site = copy.deepcopy(self.site)
        site["entries"] = [{"source_sha": "invalid", "target": "chip"}]
        with self.assertRaisesRegex(ValueError, "lacks tested SHA"):
            self.check(site=site)


if __name__ == "__main__":
    unittest.main()
