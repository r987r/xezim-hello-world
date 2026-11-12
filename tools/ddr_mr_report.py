"""Source-qualified, read-only DDR4 MR image views for existing test reports.

MRS values are DEVICE protocol values (DFI bank/address), never memory mapped.
Do not publish simulated register storage, inferred readback, reset values,
firmware writes, or JEDEC timing as if observed. This accepts only the
completed per-run scoreboard and corroborating passive protocol stream.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

ORDER = (3, 6, 5, 4, 2, 1, 0)
SOURCE = "memory0.ddr0.dfi"


def read_evidence(source: Path, protocol: Path | None = None) -> dict:
    raw = json.loads(Path(source).read_text())
    if (raw.get("status") != "pass" or
            raw.get("scope") != "observed_dfi_mrs_sequence_and_values" or
            raw.get("device_mode_registers_not_mmio") is not True or
            raw.get("observed_mrs_count") != 7 or
            raw.get("programmed_during_init") is not True or
            raw.get("subsequent_mrs_count") != 0 or
            raw.get("subsequent_reprogramming_observed") is not False or
            raw.get("model_enforces_mr_state") is not False or
            raw.get("physical_ddr4_model") is not False or
            raw.get("jedec_mrs_timing_verified") is not False or
            not re.fullmatch("[a-f0-9]{64}", str(raw.get("rdl_sha256", "")))):
        raise ValueError("unqualified or misleading DDR4 MRS evidence")
    definitions = raw.get("field_definitions")
    if not isinstance(definitions, dict) or set(definitions) != {str(x) for x in range(7)}:
        raise ValueError("MRS evidence lacks complete source RDL fields")
    rows = raw.get("records")
    if not isinstance(rows, list) or [r.get("mr") for r in rows] != list(ORDER):
        raise ValueError("DDR4 MRS observed command order incomplete")
    stamps = []
    for row in rows:
        index = row["mr"]
        definition = definitions[str(index)]
        if definition.get("offset") != index * 4:
            raise ValueError("invalid virtual DDR4 MR index")
        want = row.get("expected_value")
        got = row.get("value")
        if (not isinstance(got, str) or not re.fullmatch(r"0x[0-9a-f]{4}", got) or
                got != want or row.get("matched") is not True or
                row.get("programming") != "initialization_mrs" or
                row.get("dfi_phase") != 0 or
                type(row.get("time_ps")) is not int or
                type(row.get("cycle")) is not int):
            raise ValueError(f"unverified observed MRS value/phase for MR{index}")
        expected_fields = {}
        used = 0
        for f in definition.get("fields", []):
            name, lo, hi, mask = f.get("name"), f.get("lsb"), f.get("msb"), f.get("mask")
            if (not isinstance(name, str) or type(lo) is not int or
                    type(hi) is not int or type(mask) is not int or
                    not 0 <= lo <= hi < 16 or
                    mask != (((1 << (hi - lo + 1)) - 1) << lo) or
                    mask & used):
                raise ValueError("invalid source RDL MR field")
            used |= mask
            expected_fields[name] = (int(got, 16) & mask) >> lo
        if not expected_fields or expected_fields != row.get("fields"):
            raise ValueError("decoded DDR4 fields disagree with observed command")
        if int(got, 16) & ~used:
            raise ValueError("DDR4 MRS command sets field bits undocumented by RDL")
        stamps.append(row["time_ps"])
    if stamps != sorted(stamps) or len(set(stamps)) != 7:
        raise ValueError("DDR4 MRS commands have nonmonotonic timestamps")
    if protocol is not None:
        p = json.loads(Path(protocol).read_text())
        if p.get("schema_version") != 1 or p.get("capture_complete") is not True:
            raise ValueError("MRS evidence requires a completed passive DFI protocol capture")
        observed = [r for r in p.get("records", [])
                    if r.get("source") == SOURCE and r.get("operation") == "mrs"]
        if len(observed) != len(rows):
            raise ValueError("MRS evidence and passive protocol count disagree")
        for a, b in zip(observed, rows):
            fields = a.get("fields") or {}
            if (a.get("kind") != "event" or a.get("status") != "observed" or
                    a.get("start_ps") != b["time_ps"] or
                    fields.get("bank") != b["mr"] or
                    fields.get("address") != int(b["value"], 16) or
                    fields.get("cycle") != b["cycle"] or
                    fields.get("dfi_phase") != b["dfi_phase"] or
                    fields.get("origin_event") != "dfi_mrs"):
                raise ValueError("DDR4 MR scoreboard differs from captured DFI pins")
    return {
        "schema_version": 1,
        "kind": "device_mrs_not_mmio",
        "status": "observed_matching_commands",
        "rdl_sha256": raw["rdl_sha256"],
        "observed_writes": len(rows),
        "during_init": True,
        "after_init_writes": 0,
        "device_storage_readback_available": False,
        "model_enforces_mr_state": False,
        "jedec_mrs_timing_verified": False,
        "records": rows,
        "field_definitions": definitions,
    }


def layout(path: Path) -> dict:
    """Current repository catalog, explicitly *not* device/test evidence."""
    from sys import path as module_path
    directory = str(Path(__file__).resolve().parents[1] / "rtl" / "memory" / "ddr4")
    if directory not in module_path:
        module_path.insert(0, directory)
    from mrs_check import catalog
    data = catalog(path)
    return {"schema_version": 1, "kind": data["kind"],
            "rdl_sha256": data["rdl_sha256"],
            "registers": data["registers"],
            "qualification": "SystemRDL_device_protocol_definitions_not_runtime_proof"}
