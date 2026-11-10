"""Fail-closed CSR runtime reads and exact hierarchy resolution.

Mock handles exercise the API policy; real Xezim/Verilator evidence still
requires a separate exact-DUT integration run.
"""
import unittest
import copy

from tools.csr_runtime import ReadOnlyCsrRuntime, RuntimeEvidence, cocotb_handle
from tools.csr_backdoor import BindingError

BUILD = "ab" * 32


class Value:
    def __init__(self, value):
        self.value = value


def example(policy="backdoor_read_only"):
    catalog = {"schema_version":1,"variant":"cold_boot","instances":[{
        "name":"boot.reset_ctrl","base":"0x40020000","size":"0x1000",
        "status":"implemented","registers":[
            {"name":"cpu_release","offset":"0","size_bytes":4,"fields":[
                {"name":"secondary_release","msb":0,"lsb":0,"backdoor_policy":policy}]}
        ]}]}
    path="tb.dut.u_reset_regs.release_q"
    inventory={"schema_version":1,"variant":"cold_boot","simulator":"verilator",
        "top":"tb","build_sha256":BUILD,
        "objects":[{"path":path,"kind":"logic","width_bits":32,"writable":False}]}
    bind=[{"logical_path":"boot.reset_ctrl.cpu_release.secondary_release",
           "rtl_path":path,"rtl_lsb":0}]
    proof=RuntimeEvidence(simulator="verilator",top="tb",variant="cold_boot",build_sha256=BUILD)
    return catalog,inventory,bind,{path:Value(0)},proof


class MockHierarchy:
    _name="tb"

    def __init__(self):
        self.dut=type("Dut",(),{})()
        self.dut.u_reset_regs=type("Regs",(),{})()
        self.dut.u_reset_regs.release_q=Value(1)


class CsrRuntimeTests(unittest.TestCase):
    def test_quiescent_reads_only(self):
        catalog,inv,bindings,handles,proof=example()
        runtime=ReadOnlyCsrRuntime(catalog,inv,bindings,handles,proof)
        logical=bindings[0]["logical_path"]
        self.assertEqual(runtime.read(logical,quiescent=True),0)
        handles[next(iter(handles))].value=3
        self.assertEqual(runtime.read(logical,quiescent=True),1)
        with self.assertRaisesRegex(BindingError,"quiescent"):
            runtime.read(logical,quiescent=False)
        with self.assertRaisesRegex(BindingError,"writes are disabled"):
            runtime.write(logical,1)

    def test_snapshot_marks_hdl_reads_unvalidated_and_side_effects_unavailable(self):
        catalog, inv, bindings, handles, proof = example()
        runtime = ReadOnlyCsrRuntime(catalog, inv, bindings, handles, proof)
        handles[next(iter(handles))].value = 3
        evidence = runtime.snapshot(quiescent=True)
        self.assertEqual(evidence["simulator"], "verilator")
        self.assertEqual(evidence["variant"], "cold_boot")
        self.assertEqual(evidence["build_sha256"], BUILD)
        self.assertFalse(evidence["frontdoor_equivalence_proven"])
        self.assertFalse(evidence["protocol_traffic_observed"])
        self.assertEqual(len(evidence["inventory_sha256"]), 64)
        self.assertEqual(evidence["fields"][0]["value"], 1)
        self.assertEqual(evidence["fields"][0]["read_evidence"],
                         "quiescent_live_hdl_read_not_frontdoor_verified")
        with self.assertRaisesRegex(BindingError, "quiescent"):
            runtime.snapshot(quiescent=False)
        handles[next(iter(handles))].value = "X"
        with self.assertRaisesRegex(BindingError, "unresolved"):
            runtime.snapshot(quiescent=True)

    def test_snapshot_never_reads_side_effectful_or_unbound_field(self):
        catalog, inv, bindings, handles, proof = example()
        catalog["instances"][0]["registers"][0]["fields"].append({
            "name": "ack", "lsb": 1, "msb": 1,
            "backdoor_policy": "frontdoor_only",
        })
        runtime = ReadOnlyCsrRuntime(catalog, inv, bindings, handles, proof)
        snapshot = runtime.snapshot(quiescent=True)
        fields = {x["logical_path"]: x for x in snapshot["fields"]}
        ack = fields["boot.reset_ctrl.cpu_release.ack"]
        self.assertIsNone(ack["value"])
        self.assertEqual(ack["read_evidence"], "not_available")
        self.assertEqual(ack["policy"], "frontdoor_only")
        self.assertEqual(ack["binding_status"], "unavailable")

    def test_side_effect_and_missing_handles_fail_closed(self):
        catalog,inv,bindings,handles,proof=example("frontdoor_only")
        with self.assertRaisesRegex(BindingError,"prohibits"):
            ReadOnlyCsrRuntime(catalog,inv,bindings,handles,proof)
        catalog,inv,bindings,handles,proof=example()
        with self.assertRaisesRegex(BindingError,"runtime handles"):
            ReadOnlyCsrRuntime(catalog,inv,bindings,{},proof)

    def test_stale_build_and_unknown_paths_rejected(self):
        catalog,inv,bindings,handles,proof=example()
        wrong=RuntimeEvidence("verilator","tb","cold_boot","cd"*32)
        with self.assertRaisesRegex(BindingError,"build_sha256"):
            ReadOnlyCsrRuntime(catalog,inv,bindings,handles,wrong)
        runtime=ReadOnlyCsrRuntime(catalog,inv,bindings,handles,proof)
        with self.assertRaisesRegex(BindingError,"unknown"):
            runtime.read("boot.reset_ctrl.missing",quiescent=True)
        inv["objects"][0]["width_bits"]=0
        with self.assertRaisesRegex(BindingError,"exceeds RTL signal"):
            ReadOnlyCsrRuntime(catalog,inv,bindings,handles,proof)

    def test_exact_run_frontdoor_matches_real_live_field_at_quiescent_checkpoint(self):
        catalog, inv, bindings, handles, proof = example()
        handle = next(iter(handles.values()))
        handle.value = 1
        runtime = ReadOnlyCsrRuntime(catalog, inv, bindings, handles, proof)
        trace = {
            "schema_version": 2,
            "run": {"commit": "c" * 40, "dirty": False,
                    "engine": "cocotb-verilator", "workflow_run_id": "25",
                    "workflow_attempt": "1", "capture_bound": True,
                    "capture_overflow": False},
            "sections": {"axi": {
                "issues": [],
                "monitors": [{"id": "compute0_local_config.cpu", "plane": "config",
                              "role": "initiator", "data_width": 32}],
                "transactions": [{
                    "uid": "cfg:0:0", "monitor": "compute0_local_config.cpu",
                    "plane": "config", "role": "initiator",
                    "operation": "read", "address": "0x40020000",
                    "start_ps": 100, "end_ps": 120, "status": "complete",
                    "issues": [], "expected_beats": 1, "response": "0x0",
                    "request": {"size": "0x2"},
                    "beats": [{"data": "0x1", "resp": "0x0", "last": "0x1"}]
                }]
            }}
        }
        logical = "boot.reset_ctrl.cpu_release.secondary_release"
        kwargs = {"monitor": "compute0_local_config.cpu",
                  "tested_sha": "c" * 40, "workflow_run_id": "25",
                  "workflow_attempt": "1", "quiescent_start_ps": 90,
                  "snapshot_ps": 130}
        success = runtime.compare_frontdoor_axi_read(logical, trace, **kwargs)
        self.assertEqual(success["frontdoor_value"], 1)
        self.assertEqual(success["backdoor_value"], 1)
        self.assertEqual(success["axi_uid"], "cfg:0:0")
        self.assertIn("not_coverage", success["scope"])
        for mutation in ("wrong_data", "wrong_run", "overflow",
                         "wrong_monitor", "duplicate_read", "write",
                         "interfering_write", "bad_response", "wrong_width",
                         "invalid_beat", "late_completion"):
            with self.subTest(mutation=mutation):
                bad = copy.deepcopy(trace)
                wrong_kwargs = dict(kwargs)
                row = bad["sections"]["axi"]["transactions"][0]
                if mutation == "wrong_data":
                    row["beats"][0]["data"] = "0x0"
                elif mutation == "wrong_run":
                    bad["run"]["commit"] = "d" * 40
                elif mutation == "overflow":
                    bad["run"]["capture_overflow"] = True
                elif mutation == "wrong_monitor":
                    bad["sections"]["axi"]["monitors"][0]["data_width"] = 64
                elif mutation == "duplicate_read":
                    bad["sections"]["axi"]["transactions"].append(copy.deepcopy(row))
                elif mutation == "write":
                    row["operation"] = "write"
                elif mutation == "interfering_write":
                    competitor = copy.deepcopy(row)
                    competitor.update(monitor="compute1_local_config.cpu",
                                      operation="write", start_ps=110)
                    bad["sections"]["axi"]["transactions"].append(competitor)
                elif mutation == "bad_response":
                    row["response"] = "0x2"
                elif mutation == "wrong_width":
                    row["request"]["size"] = "0x3"
                elif mutation == "invalid_beat":
                    row["beats"] = [None]
                else:
                    wrong_kwargs["snapshot_ps"] = 110
                with self.assertRaises(BindingError):
                    runtime.compare_frontdoor_axi_read(logical, bad, **wrong_kwargs)
        handle.value = "X"
        with self.assertRaisesRegex(BindingError, "unresolved"):
            runtime.compare_frontdoor_axi_read(logical, trace, **kwargs)

    def test_unknown_values_are_not_silently_zero(self):
        catalog,inv,bindings,handles,proof=example()
        runtime=ReadOnlyCsrRuntime(catalog,inv,bindings,handles,proof)
        handles[next(iter(handles))].value="X"
        with self.assertRaisesRegex(BindingError,"unresolved"):
            runtime.read(bindings[0]["logical_path"],quiescent=True)

    def test_real_handle_resolver_never_guesses(self):
        root=MockHierarchy()
        self.assertIs(cocotb_handle(root,"tb.dut.u_reset_regs.release_q"),
                      root.dut.u_reset_regs.release_q)
        with self.assertRaisesRegex(BindingError,"top differs"):
            cocotb_handle(root,"other.dut.u_reset_regs.release_q")
        with self.assertRaisesRegex(BindingError,"unavailable"):
            cocotb_handle(root,"tb.dut.u_reset_regs.no_signal")
        with self.assertRaisesRegex(BindingError,"malformed"):
            cocotb_handle(root,"tb.dut.foo;delete()")


if __name__=="__main__":
    unittest.main()
