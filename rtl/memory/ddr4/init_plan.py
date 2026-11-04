"""Translate pinned upstream LiteDRAM DDR4 init steps for a future WB driver.

No hand-authored DDR4 mode-register values, no custom DDR controller/PHY,
and no claim that emitting this plan performs initialization in RTL.
"""
from __future__ import annotations

import json
from pathlib import Path

# The command names and bit positions are the DFII constants in the pinned
# LiteDRAM init.py, not a replacement for its timing/MR calculation.
DFII_BITS = {
    "DFII_CONTROL_SEL": 0x01,
    "DFII_CONTROL_CKE": 0x02,
    "DFII_CONTROL_ODT": 0x04,
    "DFII_CONTROL_RESET_N": 0x08,
    "DFII_COMMAND_CS": 0x01,
    "DFII_COMMAND_WE": 0x02,
    "DFII_COMMAND_CAS": 0x04,
    "DFII_COMMAND_RAS": 0x08,
    "DFII_COMMAND_WRDATA": 0x10,
    "DFII_COMMAND_RDDATA": 0x20,
}


def encode_operation(expr: str) -> tuple[str, int]:
    if not isinstance(expr, str) or not expr:
        raise ValueError("empty upstream DFII command")
    fields = [s.strip() for s in expr.split("|")]
    if len(fields) != len(set(fields)) or any(s not in DFII_BITS for s in fields):
        raise ValueError(f"unknown/duplicated upstream DFII command: {expr}")
    groups = {s.split("_")[1] for s in fields}
    if len(groups) != 1 or next(iter(groups)) not in {"CONTROL", "COMMAND"}:
        raise ValueError(f"invalid DFII command/control mix: {expr}")
    return next(iter(groups)).lower(), sum(DFII_BITS[s] for s in fields)


def compile_steps(steps: list, sys_clk_hz: int) -> dict:
    if not isinstance(sys_clk_hz, int) or sys_clk_hz <= 0:
        raise ValueError("controller clock must be a positive integer Hz")
    if not steps:
        raise ValueError("no DDR4 initialization steps from upstream")
    records = []
    for step in steps:
        if len(step) != 5:
            raise ValueError(f"malformed upstream DFII init step: {step}")
        name, address, bank, expression, delay = step
        if not isinstance(name, str) or not name:
            raise ValueError("unnamed DDR4 init step")
        if not all(type(n) is int for n in (address, bank, delay)):
            raise ValueError(f"noninteger DDR4 init step: {name}")
        if not (0 <= address <= 0xFFFF and 0 <= bank < 8 and delay >= 0):
            raise ValueError(f"DDR4 init step out of range: {name}")
        kind, mask = encode_operation(expression)
        records.append({"name": name, "address": address, "bank": bank,
                        "kind": kind, "mask": mask,
                        "upstream_delay_units": delay})
    return {
        "status": "plan-only-not-executed",
        "source": "pinned LiteDRAM get_sdram_phy_init_sequence",
        "clock_hz": sys_clk_hz,
        "steps": records,
        "warning": "Upstream delay units are BIOS cdelay counts, not directly simulation clock cycles; verify delays before driving Wishbone",
    }


def from_upstream(profile: dict, module_cls: type) -> dict:
    """Use upstream timing and MR encodings, including the selected sim PHY."""
    from litedram.phy.model import get_sdram_phy_settings
    from litedram.init import get_sdram_phy_init_sequence

    if profile.get("memtype") != "DDR4":
        raise ValueError("DDR4 init plan expected")
    clock = int(float(profile["sys_clk_freq"]))
    device = module_cls(clock, rate="1:4")
    settings = get_sdram_phy_settings(memtype="DDR4",
                                      data_width=profile["sdram_module_nb"] * 8,
                                      clk_freq=clock)
    sequence, _ = get_sdram_phy_init_sequence(settings, device.timing_settings)
    plan = compile_steps(sequence, clock)
    if not any("Mode Register" in s["name"] for s in plan["steps"]):
        raise ValueError("upstream DDR4 initialization missing mode-register steps")
    return plan


def save(plan: dict, output_dir: Path) -> Path:
    path = output_dir / "ddr4_init_plan.json"
    path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    return path
