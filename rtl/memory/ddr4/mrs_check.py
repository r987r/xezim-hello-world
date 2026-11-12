"""DDR4 device MR catalog and independent DFI MRS scoreboard.

MR0..MR6 are JEDEC DEVICE state, not software-visible LiteDRAM CSRs.
Use the virtual SystemRDL field catalog without synthesizing a second MMIO
bank. An upstream-derived DDR4 init plan is the EXPECTATION; observed, passive
DFI commands are the EVIDENCE. The current SDRAMPHYModel does not implement
mode-register state or enforce MR-derived timing; this checker cannot claim it.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
RDL = ROOT / "csr" / "rdl" / "ddr4_mode_registers.rdl"
ORDER = (3, 6, 5, 4, 2, 1, 0)
# Independent pin-level shape sanity, not a hardcoded source for MR bitfields.
DFI_MRS_COMMAND = 0x0f
FIELDS = re.compile(r"\}\s*([a-z][a-z0-9_]*)\[(\d+):(\d+)\]\s*;")
REGISTERS = re.compile(r"\breg\s*\{(.*?)\}\s*mr([0-6])\s*@\s*(0x[0-9a-f]+)\s*;", re.S | re.I)


class MRValidationError(ValueError):
    pass


def catalog(path: Path = RDL) -> dict:
    """Extract the complete, narrowly constrained, non-MMIO RDL layout.

    Full SystemRDL compilation is checked separately in CI against this
    catalog. This stdlib extraction keeps RTL regressions independent of a
    Python CSR-generator installation.
    """
    src = Path(path).read_text()
    if "addrmap ddr4_mode_registers" not in src:
        raise MRValidationError("missing DDR4 SystemRDL addrmap")
    regs = {}
    for match in REGISTERS.finditer(src):
        body, index_raw, offset_raw = match.groups()
        idx, offset = int(index_raw), int(offset_raw, 16)
        if idx in regs or offset != idx * 4:
            raise MRValidationError("duplicate/unaligned DDR4 MR virtual offset")
        items = []
        used = 0
        for field in FIELDS.finditer(body):
            name, high_raw, low_raw = field.groups()
            hi, lo = int(high_raw), int(low_raw)
            if not 0 <= lo <= hi < 16:
                raise MRValidationError(f"MR{idx}.{name}: invalid DDR4 bit range")
            mask = ((1 << (hi - lo + 1)) - 1) << lo
            if mask & used:
                raise MRValidationError(f"MR{idx}: overlapping RDL field bits")
            used |= mask
            items.append({"name": name, "lsb": lo, "msb": hi, "mask": mask})
        if not items:
            raise MRValidationError(f"MR{idx}: no SystemRDL fields")
        regs[idx] = {"offset": offset, "fields": items, "known_mask": used}
    if set(regs) != set(range(7)) or len(src.split("reg {")) != 8:
        raise MRValidationError("DDR4 RDL must contain exactly MR0-MR6")
    return {
        "schema_version": 1,
        "kind": "virtual_ddr4_device_mode_registers_not_mmio",
        "rdl_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "registers": regs,
    }


def expected_mrs(plan: dict, layout: dict) -> list[dict]:
    if plan.get("status") != "plan-only-not-executed":
        raise MRValidationError("expected actual upstream-generated DDR4 init plan")
    found = []
    for step in plan.get("steps", []):
        if not str(step.get("name", "")).startswith("Load Mode Register "):
            continue
        bank, value = step.get("bank"), step.get("address")
        if type(bank) is not int or type(value) is not int or bank not in layout["registers"]:
            raise MRValidationError("unsupported DDR4 MR index/value in upstream plan")
        if type(step.get("mask")) is not int or step["mask"] != DFI_MRS_COMMAND or step.get("kind") != "command":
            raise MRValidationError("upstream MR step must issue full DFI MRS command")
        if value < 0 or value > 0x7fff:
            raise MRValidationError(f"MR{bank}: invalid command address width")
        known = layout["registers"][bank]["known_mask"]
        if value & ~known:
            raise MRValidationError(
                f"MR{bank}: upstream value {value:#x} sets undocumented SystemRDL bits {(value & ~known):#x}")
        found.append({"mr": bank, "value": value, "source": step["name"]})
    if tuple(x["mr"] for x in found) != ORDER:
        raise MRValidationError(f"incorrect DDR4 MR programming order: {[x['mr'] for x in found]}")
    return found


def verify_observed(plan: dict, events: list[dict], *, path: Path = RDL) -> dict:
    """Require exact pin-level MRS order, values and phase during startup.

    Missing commands, double commands, wrong CS/RAS/CAS/WE decode, wrong bank,
    unexpected MRS after init and premature DFI READ/WRITE all fail closed.
    """
    layout = catalog(path)
    expected = expected_mrs(plan, layout)
    actual = [e for e in events if e.get("kind") == "dfi_mrs"]
    if len(actual) != len(expected):
        raise MRValidationError(
            f"observed {len(actual)} DFI MRS commands; expected {len(expected)}")
    result = []
    for want, seen in zip(expected, actual):
        bank = seen.get("bank")
        value = seen.get("address")
        if bank != want["mr"] or value != want["value"]:
            raise MRValidationError(
                f"DFI MRS mismatch: expected MR{want['mr']}={want['value']:#06x}, "
                f"observed MR{bank}={value!r}")
        if (seen.get("dfi_phase") != 0 or
                seen.get("test_phase") not in ("initialization", "pre_init")):
            raise MRValidationError(f"MR{bank}: wrong DFI phase or test phase")
        fields = {
            f["name"]: (value & f["mask"]) >> f["lsb"]
            for f in layout["registers"][bank]["fields"]
        }
        result.append({"mr": bank, "value": f"0x{value:04x}",
                       "cycle": seen.get("cycle"), "time_ps": seen.get("time_ps"),
                       "fields": fields})
    cutoff = max(int(e.get("time_ps", 0)) for e in actual)
    early = [e for e in events if e.get("kind") in ("dfi_read", "dfi_write") and
             int(e.get("time_ps", 0)) <= cutoff]
    if early:
        raise MRValidationError("DDR memory traffic observed before MR initialization finished")
    return {
        "status": "pass", "scope": "observed_dfi_mrs_sequence_and_values",
        "device_mode_registers_not_mmio": True, "rdl_sha256": layout["rdl_sha256"],
        "observed_mrs_count": len(actual), "records": result,
        "model_enforces_mr_state": False,
        "mr_derived_read_write_latency_verified": False,
        "jedec_mrs_timing_verified": False,
        "physical_ddr4_model": False,
    }


def verify_capture(folder: Path, plan_path: Path, output_path: Path | None = None) -> dict:
    folder, plan_path = Path(folder), Path(plan_path)
    summary = json.loads((folder / "ddr4_dfi_summary.json").read_text())
    if summary.get("status") != "pass" or summary.get("sampled_cycles", 0) < 1:
        raise MRValidationError("MRS verification requires successful continuous DFI capture")
    raw = [json.loads(s) for s in (folder / "ddr4_dfi_events.jsonl").read_text().splitlines()]
    if not raw or raw[0].get("kind") != "probe_start" or raw[-1].get("kind") != "probe_end":
        raise MRValidationError("MRS verification requires complete DFI capture")
    if raw[-1].get("status") != "pass" or raw[-1].get("sampled_cycles") != summary["sampled_cycles"]:
        raise MRValidationError("MRS DFI capture summary/end mismatch")
    if sum(1 for e in raw if e.get("kind") == "dfi_mrs") != summary.get("counters", {}).get("dfi_mrs", 0):
        raise MRValidationError("MRS DFI capture counters mismatch")
    plan = json.loads(plan_path.read_text())
    result = verify_observed(plan, raw[1:-1])
    result["capture_scope"] = raw[0]["scope"]
    result["captured_cycles"] = summary["sampled_cycles"]
    if output_path is not None:
        Path(output_path).write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result
