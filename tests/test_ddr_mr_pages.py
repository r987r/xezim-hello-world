"""DDR4 mode-register web views: source-only, observed runs, and rejection gates."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"tools"))
sys.path.insert(0, str(ROOT/"rtl/memory/ddr4"))
from ddr_mr_report import layout, read_evidence, annotate_protocol
from publish_site import ddr_mr_views
from mrs_check import verify_observed
from test_mrs_contract import fixture


def recorded_run(root, target="chip-ddr4-real"):
    plan, events = fixture()
    result = verify_observed(plan, events)
    result["capture_scope"] = "fullchip_litedram_dfi_sim"
    result["captured_cycles"] = 1000
    location = root/"runs"/"888-1"/target
    location.mkdir(parents=True, exist_ok=True)
    (location/"ddr4_mrs_evidence.json").write_text(json.dumps(result))
    trace = {
        "schema_version": 1, "capture_complete": True,
        "records": [
            {"source": "memory0.ddr0.dfi", "operation": "mrs",
             "kind": "event", "status": "observed",
             "start_ps": e["time_ps"], "fields": {
                 "bank": e["bank"], "address": e["address"],
                 "cycle": e["cycle"], "dfi_phase": 0,
                 "origin_event": "dfi_mrs"
             }}
            for e in events if e["kind"] == "dfi_mrs"
        ],
    }
    (location/"protocol-transactions.json").write_text(json.dumps(trace))
    entry = {
        "target": target, "passed": True, "axi": True,
        "run_id": 888, "source_sha": "ab"*20,
        "path": str((location.relative_to(root)/"report.html").as_posix()),
    }
    return entry, location, trace, result


class DdrMRPages(unittest.TestCase):
    def test_source_catalog_is_not_mmio_or_runtime_state(self):
        src = layout(ROOT/"csr/rdl/ddr4_mode_registers.rdl")
        self.assertEqual(src["kind"], "virtual_ddr4_device_mode_registers_not_mmio")
        self.assertEqual(len(src["registers"]), 7)
        self.assertEqual(src["registers"][0]["fields"][0]["name"], "burst_length")

    def test_qualified_run_and_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entry, folder, _, _ = recorded_run(root)
            checked = read_evidence(folder/"ddr4_mrs_evidence.json",
                                    folder/"protocol-transactions.json")
            self.assertEqual(checked["observed_writes"], 7)
            self.assertEqual(checked["after_init_writes"], 0)
            self.assertFalse(checked["model_enforces_mr_state"])
            views = ddr_mr_views([entry], root)
            self.assertEqual(len(views), 1)
            self.assertEqual(views[0]["source_sha"], "ab"*20)
            self.assertEqual(views[0]["evidence"]["records"][0]["mr"], 3)
            self.assertIn("ddr4_mrs_evidence.json", views[0]["evidence_href"])

    def test_unobserved_or_failed_run_not_green(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entry, folder, _, _ = recorded_run(root)
            self.assertEqual(ddr_mr_views([{**entry, "passed": False}], root), [])
            self.assertEqual(ddr_mr_views([{**entry, "target": "chip-boot"}], root), [])
            (folder/"ddr4_mrs_evidence.json").unlink()
            self.assertEqual(ddr_mr_views([entry], root), [])

    def test_mutation_of_independent_pin_trace_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entry, folder, trace, evidence = recorded_run(root)
            trace["records"][3]["fields"]["address"] ^= 1
            (folder/"protocol-transactions.json").write_text(json.dumps(trace))
            with self.assertRaisesRegex(ValueError, "differs from captured"):
                ddr_mr_views([entry], root)
            (folder/"protocol-transactions.json").write_text(json.dumps({
                **trace, "capture_complete": False}))
            with self.assertRaisesRegex(ValueError, "completed"):
                ddr_mr_views([entry], root)
            (folder/"protocol-transactions.json").write_text(json.dumps({
                **trace, "capture_complete": True, "records": []}))
            with self.assertRaisesRegex(ValueError, "count disagree"):
                read_evidence(folder/"ddr4_mrs_evidence.json",
                              folder/"protocol-transactions.json")

    def test_forged_fields_and_after_init_mutations_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, folder, trace, original = recorded_run(root)
            for change, phrase in [
                ({"observed_mrs_count": 6}, "unqualified"),
                ({"subsequent_mrs_count": 1}, "unqualified"),
                ({"model_enforces_mr_state": True}, "unqualified"),
                ({"rdl_sha256": "x"}, "unqualified"),
            ]:
                bad={**original, **change}
                (folder/"ddr4_mrs_evidence.json").write_text(json.dumps(bad))
                with self.assertRaisesRegex(ValueError, phrase):
                    read_evidence(folder/"ddr4_mrs_evidence.json")
            bad=copy.deepcopy(original)
            bad["records"][0]["fields"]["fine_refresh"] ^= 1
            (folder/"ddr4_mrs_evidence.json").write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError, "decoded DDR4 fields"):
                read_evidence(folder/"ddr4_mrs_evidence.json")


    def test_unified_traffic_has_verified_rdl_decode(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            _,folder,original,_=recorded_run(root)
            verified=read_evidence(folder/"ddr4_mrs_evidence.json",
                                   folder/"protocol-transactions.json")
            source=copy.deepcopy(original)
            for event in source["records"]:
                event["protocol"]="dfi"
            decoded=annotate_protocol(source,verified)
            self.assertNotIn("mr_register",source["records"][0]["fields"])
            self.assertEqual([r["fields"]["mr_register"] for r in decoded["records"]],
                             ["MR3","MR6","MR5","MR4","MR2","MR1","MR0"])
            mr5=decoded["records"][2]["fields"]
            self.assertEqual(mr5["mr_programmed_value"],"0x0400")
            self.assertEqual(mr5["mr_match"],"MATCH")
            self.assertEqual(mr5["mr_decoded_fields"][0]["field"],"data_mask")
            self.assertEqual(mr5["mr_decoded_fields"][0]["value"],1)
            self.assertEqual(mr5["mr_programming_phase"],"INIT")
            self.assertEqual(mr5["mr_decode_scope"],
                             "observed_DFI_command_not_DRAM_device_readback")
            self.assertFalse(mr5["mr_model_applies_settings"])

    def test_unified_overlay_rejects_corrupted_raw_capture(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            _,folder,original,_=recorded_run(root)
            verified=read_evidence(folder/"ddr4_mrs_evidence.json",
                                   folder/"protocol-transactions.json")
            source=copy.deepcopy(original)
            for event in source["records"]:
                event["protocol"]="dfi"
            variants=[]
            bad=copy.deepcopy(source)
            bad["records"][0],bad["records"][1]=bad["records"][1],bad["records"][0]
            variants.append(bad)
            bad=copy.deepcopy(source)
            bad["records"][1]["fields"]["address"] ^= 1
            variants.append(bad)
            bad=copy.deepcopy(source)
            bad["records"][0]["fields"]["mr_match"]="MATCH"
            variants.append(bad)
            bad=copy.deepcopy(source)
            bad["records"][0]["protocol"]="axi4"
            variants.append(bad)
            for i,variant in enumerate(variants):
                with self.subTest(mutation=i):
                    with self.assertRaisesRegex(ValueError,"MR decode|untrusted MR annotations"):
                        annotate_protocol(variant,verified)

    def test_unified_traffic_view_and_publish_paths(self):
        published=(ROOT/"tools/publish_site.py").read_text()
        site=(ROOT/"tools/templates/site_runs_traffic.js").read_text()
        run=(ROOT/"tools/templates/site_runs.html").read_text()
        detail=(ROOT/"tools/templates/protocol_report.html").read_text()
        self.assertIn("protocol-transactions-decoded.json",published)
        self.assertIn("visible_protocol = annotate_protocol(protocol_data, mr_view)",published)
        self.assertIn("protocol_decode_href",site)
        self.assertIn("traffic-mrs-decode",site)
        self.assertIn("traffic-mrs-decode",run)
        self.assertIn("mrs-decoded",detail)
        self.assertIn("mr_decoded_fields",detail)

    def test_templates_have_explicit_statuses(self):
        address=(ROOT/"tools/templates/site_address-map.html").read_text()
        report=(ROOT/"tools/templates/run_report.html").read_text()
        for word in ('ddr-mr-browser','mr-test-select','mr-compare-select',
                     '__DDR_MR_CATALOG__','__DDR_MR_RUNS__'):
            self.assertIn(word, address)
        for word in ('ddr-mrs-section','mrEvidence','UNMEASURED',
                     'Changed after INIT?', 'Not memory-mapped CSRs'):
            self.assertIn(word, report)


if __name__ == "__main__":
    unittest.main()
