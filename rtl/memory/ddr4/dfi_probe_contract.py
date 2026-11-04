"""Targeted, read-only DFI/BankModel visibility for pinned LiteDRAM Verilog.

No vendor source patching, no generated RTL rewriting, no global
--public-flat-rw (that would expose large modeled DRAM arrays).
Verilator control directives expose *only* validated flattened signals.
"""
from __future__ import annotations

from pathlib import Path
import json
import re

PHASES = 4
BANKS = 16
DFI_FIELDS = ("cs_n", "act_n", "ras_n", "cas_n", "we_n",
              "bank", "address", "rddata_en", "rddata_valid", "wrdata_en")
BANK_FIELDS = ("read", "write_port_we")


def signal_names() -> list[str]:
    names = [
        f"soc_ddrphy_dfi_p{phase}_{field}"
        for phase in range(PHASES) for field in DFI_FIELDS
    ]
    names += [
        f"soc_ddrphy_bankmodel{bank}_{field}"
        for bank in range(BANKS) for field in BANK_FIELDS
    ]
    return names


def verify_generated_signals(verilog: str) -> list[str]:
    """Fail closed if the generator renames/changes requested probe nets."""
    if not re.search(r"\bmodule\s+soc_ddr4_sim\s*\(", verilog):
        raise ValueError("unexpected LiteDRAM generated module")
    missing = []
    for name in signal_names():
        # All pinned Migen outputs are flat top-level reg/wire declarations.
        matches = re.findall(
            r"(?m)^\s*(?:wire|reg)\s+(?:\[[^\]\n]+\]\s+)?"
            + re.escape(name) + r"\s*(?:=|;)",
            verilog,
        )
        if len(matches) != 1:
            missing.append(name)
    if missing:
        raise ValueError("generated DDR4 DFI/BankModel probe contract changed: "
                         + ", ".join(missing[:8]))
    return signal_names()



def top_level_port_names(verilog: str) -> list[str]:
    """Explicit top-level VPI port list, never global internal/array access."""
    match = re.search(r"\\bmodule\\s+soc_ddr4_sim\\s*\\((.*?)\\)\\s*;", verilog, re.S)
    if not match:
        raise ValueError("missing DDR4 top-level port header")
    header = match.group(1)
    ports = re.findall(
        r"\\b(?:input|output|inout)\\s+"
        r"(?:(?:wire|reg|logic|signed)\\s+)*"
        r"(?:\\[\\s*\\d+\\s*:\\s*\\d+\\s*\\]\\s+)?"
        r"([A-Za-z_][A-Za-z0-9_]*)\\b",
        header,
    )
    if not ports or len(ports) > 256 or len(ports) != len(set(ports)) or "clk" not in ports:
        raise ValueError("unreviewed DDR4 top-level VPI port declaration")
    return ports


def write_control_file(source: Path, output: Path) -> Path:
    verilog = source.read_text()
    names = verify_generated_signals(verilog)
    ports = top_level_port_names(verilog)
    if output.is_symlink() or output.resolve() == source.resolve():
        raise ValueError("invalid DFI probe control output")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "`verilator_config\n"
        "// Simulation-only, read-only visibility into pinned LiteDRAM nets.\n"
        "// No public access to backing memory arrays or controller state.\n"
        + "".join(
            f'public_flat_rd -module "soc_ddr4_sim" -var "{name}"\\n'
            for name in names
        )
        + "".join(
            f'public_flat_rw -module "soc_ddr4_sim" -var "{name}"\\n'
            for name in ports
        )
    )
    (output.parent / "ddr4_probe_contract.json").write_text(
        json.dumps({
            "model": "LiteDRAM SDRAMPHYModel and BankModel (not silicon PHY/DRAM)",
            "top": "soc_ddr4_sim", "net_count": len(names),
            "top_port_count": len(ports), "ports": ports,
            "signals": names, "control_file": output.name
        }, indent=2) + "\n"
    )
    return output
