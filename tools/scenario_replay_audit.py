"""Fail-closed replay/evidence audit across real CPU0-C and BFM RTL runs.

This is a correlation check, not a replacement for the independent passive
AXI scoreboard and per-run firmware byte/descriptor validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REQUIRED_CHANNELS = ("src_ar", "ddr_aw", "ddr_ar", "return_aw")


class ReplayAuditError(ValueError):
    pass


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReplayAuditError(f"{path}: invalid or missing JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ReplayAuditError(f"{path}: expected JSON object")
    return data


def audit(cpu_dir: Path, bfm_dir: Path) -> dict:
    inputs = []
    for folder, label, rel in (
        (cpu_dir, "real_cpu0_compiled_c", "variant/scenario-plan.json"),
        (bfm_dir, "reset_isolated_cocotb_bfm", "scenario-plan.json"),
    ):
        path = folder / rel
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ReplayAuditError(f"{path}: missing scenario intent") from exc
        plan = _read_json(path)
        evidence = _read_json(folder / "scenario-execution.json")
        result = _read_json(folder / "result.json")
        if plan.get("kind") != "soc_scenario_intent_only" or plan.get("execution_evidence") is not None:
            raise ReplayAuditError(f"{label}: intent must not claim RTL evidence")
        sha = hashlib.sha256(raw).hexdigest()
        if evidence.get("plan_sha256") != sha or evidence.get("scenario_id") != plan.get("scenario_id"):
            raise ReplayAuditError(f"{label}: mismatched plan hash or scenario ID")
        if (type(plan.get("seed")) is not int or not 0 <= plan["seed"] <= 0xffffffff
                or type(evidence.get("scenario_seed")) is not int
                or evidence["scenario_seed"] != plan["seed"]):
            raise ReplayAuditError(f"{label}: resolved random/directed seed differs from real execution")
        # Driver-effective fill pattern is not the scenario RNG selector.
        # The compiled CPU C constants and the BFM executor use the resolved
        # memory.initialize seed. Byte/readback checks independently gate PASS.
        actions = [a for a in plan.get("actions", [])
                   if a.get("action_instance_id") == "init_source"]
        if len(actions) != 1:
            raise ReplayAuditError(f"{label}: missing selected memory initialization")
        pattern = (actions[0].get("args") or {}).get("pattern") or {}
        expected_pattern_seed = pattern.get("seed")
        if (type(expected_pattern_seed) is not int
                or not 0 <= expected_pattern_seed <= 0xffffffff
                or type(evidence.get("executed_pattern_seed")) is not int
                or evidence["executed_pattern_seed"] != expected_pattern_seed):
            raise ReplayAuditError(f"{label}: effective driver pattern seed differs from plan")
        if evidence.get("profile") != label or evidence.get("execution_state") != "rtl_observed":
            raise ReplayAuditError(f"{label}: missing observed execution provenance")
        if evidence.get("intent_is_not_evidence") is not True or result.get("passed") is not True:
            raise ReplayAuditError(f"{label}: unverified RTL run or intent-only evidence")
        checks = result.get("results", [])
        if not isinstance(checks, list) or len(checks) != 1 or checks[0].get("passed") is not True or checks[0].get("exit_code") != 0:
            raise ReplayAuditError(f"{label}: missing or failed RTL test result")
        counts = evidence.get("observed_dma_axi_counts")
        if not isinstance(counts, dict) or any(type(counts.get(k)) is not int or counts[k] < 1
                                               for k in REQUIRED_CHANNELS):
            raise ReplayAuditError(f"{label}: missing independently accepted AXI traffic")
        inputs.append((raw, plan, evidence, result))

    (cpu_raw, cpu_plan, cpu_ev, cpu_result), (bfm_raw, bfm_plan, bfm_ev, bfm_result) = inputs
    if cpu_raw != bfm_raw:
        raise ReplayAuditError("CPU/BFM resolved scenario plans differ byte-for-byte")
    # The real CPU C source selected a full 256-bit plan SHA and wrote eight
    # 32-bit words through the CPU-side AXI initiator. The live Cocotb
    # checkpoint independently correlates original AW/W/B byte lanes.
    witness = cpu_ev.get("cpu_plan_sha_axi_witness")
    expected_witness = next((item["phys"] for item in cpu_plan.get("allocations", [])
                             if item.get("buffer") == "src"), None)
    if (not isinstance(witness, dict)
            or witness.get("status") != "full_sha_observed_on_real_cpu_axi"
            or witness.get("plan_sha256") != hashlib.sha256(cpu_raw).hexdigest()
            or type(expected_witness) is not int
            or witness.get("witness_phys") != hex(expected_witness + 0x1000)):
        raise ReplayAuditError("CPU source-selected full SHA passive AXI witness missing or different")
    if (witness.get("accepted_writes") != 8
            or witness.get("checked_bytes") != 32
            or witness.get("evidence") != "original_passive_axi_aw_w_b_not_firmware_self_report"
            or witness.get("scenario_action_completion_proven") is not False):
        raise ReplayAuditError("CPU plan SHA lacks full independently accepted AXI write coverage")
    # New real CPU C runtime now dispatches from the selected typed SCN-C
    # action table, not the old hardcoded sequence. Its driver-issued/done
    # words must be independently observed as accepted CPU AXI AW/W/B,
    # but are never substituted for DMA/NoC independent byte proof.
    trace = cpu_ev.get("cpu_action_trace")
    selected_ids = [a.get("action_instance_id") for a in cpu_plan.get("actions", [])]
    if (not isinstance(trace, dict) or not selected_ids or
            trace.get("status") != "source_selected_cpu_action_driver_observed_on_real_axi" or
            trace.get("plan_sha256") != hashlib.sha256(cpu_raw).hexdigest() or
            trace.get("trace_phys") != hex(expected_witness + 0x1000 + 32) or
            trace.get("action_ids") != selected_ids or
            trace.get("accepted_writes") != 2 * len(selected_ids) or
            trace.get("checked_bytes") != 8 * len(selected_ids) or
            trace.get("issued") != len(selected_ids) or
            trace.get("driver_done") != len(selected_ids) or
            trace.get("evidence") != "original_passive_axi_aw_w_b_driver_events_only" or
            trace.get("hardware_completion_proven") is not False):
        raise ReplayAuditError("real CPU selected SCN-C action dispatch AXI proof missing")
    if cpu_ev.get("cpu_result_checked") is not True:
        raise ReplayAuditError("CPU real C firmware did not prove returned bytes")
    if bfm_ev.get("independently_readback_bytes") != 64:
        raise ReplayAuditError("BFM independent DDR/SRAM byte readback missing")
    allocations = {a["buffer"]: a["phys"] for a in cpu_plan.get("allocations", [])}
    expected = [allocations.get(x) for x in ("src", "return", "ddr")]
    if any(x is None for x in expected) or cpu_ev.get("observed_cpu_allocations") != expected:
        raise ReplayAuditError("real CPU allocation MMIO differs from resolved plan")
    flow = cpu_result.get("test_flow", {})
    if flow.get("status") != "complete" or flow.get("passed") is not True or flow.get("issues") != 0 or flow.get("steps") != 6:
        raise ReplayAuditError("real CPU INIT/RUN/CHECK v1 test-flow not complete")
    bfm_flow = bfm_result.get("test_flow", {})
    if bfm_flow.get("status") != "unmeasured" or bfm_flow.get("steps") != 0:
        raise ReplayAuditError("BFM falsely claims real firmware phase observations")
    return {"schema_version": 1, "status": "validated_both_real_rtl_profiles",
            "scenario_id": cpu_plan["scenario_id"],
            "plan_sha256": hashlib.sha256(cpu_raw).hexdigest(),
            "profiles": ["real_cpu0_compiled_c", "reset_isolated_cocotb_bfm"],
            "observed_dma_axi_counts": {
                label: ev["observed_dma_axi_counts"]
                for label, ev in (("cpu", cpu_ev), ("bfm", bfm_ev))
            },
            "cpu_test_flow": "complete", "bfm_test_flow": "unmeasured",
            "memory_target": "modeled_ddr_only"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu", type=Path, required=True)
    parser.add_argument("--bfm", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit(args.cpu, args.bfm)
    except ReplayAuditError as exc:
        parser.error(str(exc))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print("PASS SCN-2 replay-audit: identical intent and independent CPU/BFM RTL evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
