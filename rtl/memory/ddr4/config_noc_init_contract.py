"""DDR-B: map pinned LiteDRAM DFII init script to the independent Config NoC.

This is a transport / address-decoder contract, NOT a second INIT/RUN/CHECK
engine, driver, or proof of hardware initialization. The existing standalone
wishbone_script() is the only authority for upstream command ordering.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import yaml

from init_plan import wishbone_script

TARGET = "memory0.ctrl"
DDR = "memory0.ddr0"


def integer(value: object) -> int:
    if type(value) is int:
        return value
    if isinstance(value, str):
        return int(value, 0)
    raise ValueError("expected integer configuration address")


def config_window(soc: dict) -> tuple[int, int]:
    bus = soc.get("buses", {}).get("config", {})
    if bus != {"protocol": "axi4_lite", "addr_bits": 32, "data_bits": 32}:
        raise ValueError("DDR init requires independent 32-bit AXI-Lite Config NoC")
    plane = soc.get("networks", {}).get("global_config", {})
    if plane.get("protocol") != "axi4_lite" or "memory0" not in plane.get("reachable_subsystems", []):
        raise ValueError("Memory0 DDR control not reachable from global Config NoC")
    if soc.get("fabrics", {}).get("global_config", {}).get("backend") != "floonoc":
        raise ValueError("unknown global Config NoC backend")
    regions = [entry for entry in soc.get("address_map", {}).get("config", [])
               if entry.get("name") == TARGET]
    if len(regions) != 1:
        raise ValueError("DDR control region must exist exactly once")
    base = integer(regions[0]["base"])
    size = integer(regions[0]["size"])
    if size < 4 or size & (size - 1) or base < 0 or base % size:
        raise ValueError("invalid/alignment-unsafe DDR control aperture")
    if base + size > 2**32:
        raise ValueError("DDR control address exceeds 32-bit Config NoC")
    return base, size


def compile_transport(soc: dict, upstream_plan: dict, csr: dict, *,
                      delay_multiplier: int = 2,
                      generated_wb_base: int | None = None,
                      generated_wb_adr_bits: int | None = None,
                      proposed_window_bytes: int | None = None) -> dict:
    """Produce explicit AXI-Lite-to-Wishbone address mappings, no side effects.

    The generated LiteX CSR addresses are authoritative. A physical write
    to config_base+offset must be translated back to the original Wishbone
    byte address, *not* passed as an unmodified global physical address.
    """
    base, configured_size = config_window(soc)
    size = configured_size
    if proposed_window_bytes is not None:
        size = integer(proposed_window_bytes)
        if (size <= configured_size or size & (size - 1)
                or base % size or base + size > 2**32):
            raise ValueError("proposed Config NoC aperture must enlarge the configured aligned window")
        for region in soc.get("address_map", {}).get("config", []):
            if region.get("name") == TARGET:
                continue
            other_base = integer(region["base"])
            other_end = other_base + integer(region["size"])
            if base < other_end and other_base < base + size:
                raise ValueError(f"proposed DDR control aperture overlaps {region['name']}")
    targets = [v for v in soc.get("memory_targets", [])
               if v.get("name") == DDR]
    if len(targets) != 1 or targets[0].get("controller") != "litedram":
        raise ValueError("DDR target absent or not LiteDRAM")
    if targets[0].get("simulation", {}).get("backend") not in ("axi_ram", "litedram_sim"):
        raise ValueError("unexpected SoC DDR backend")
    actions = wishbone_script(upstream_plan, csr, delay_multiplier=delay_multiplier)
    writes = [a for a in actions if a["op"] == "write"]
    if not writes or writes[-1].get("csr") != "ddrctrl_init_done" or writes[-1]["value"] != 1:
        raise ValueError("missing final LiteDRAM software-control handoff")
    registry = csr.get("csr_registers", {})
    readback_names = ("ddrctrl_init_done", "ddrctrl_init_error", "sdram_dfii_control")
    needed = {a["csr"] for a in writes} | set(readback_names)
    addresses = []
    for name in sorted(needed):
        reg = registry.get(name)
        if not isinstance(reg, dict) or reg.get("type") != "rw" or reg.get("size") != 1:
            raise ValueError(f"missing generated Wishbone CSR {name}")
        value = reg.get("addr")
        if type(value) is not int or value < 0 or value % 4:
            raise ValueError(f"invalid generated Wishbone CSR address for {name}")
        addresses.append(value)
    if len(set(addresses)) != len(addresses):
        raise ValueError("generated controller CSR addresses alias")
    # Inference is only an unexecuted proposal; RTL must implement the
    # corresponding offset translation, preserving the raw Wishbone address.
    wb_base = ((min(addresses) // size) * size
               if generated_wb_base is None else integer(generated_wb_base))
    if wb_base < 0 or wb_base % size:
        raise ValueError("generated Wishbone translation base not aligned")
    if any(not wb_base <= addr < wb_base + size for addr in addresses):
        raise ValueError("generated LiteDRAM CSR map exceeds Config NoC 4-KiB aperture")
    if generated_wb_adr_bits is not None:
        if type(generated_wb_adr_bits) is not int or not 1 <= generated_wb_adr_bits <= 32:
            raise ValueError("invalid generated Wishbone ADR pin width")
        if any((addr // 4) >= (1 << generated_wb_adr_bits) for addr in addresses):
            raise ValueError("generated Wishbone ADR width would truncate controller CSR address")

    def route(name: str, address: int) -> dict:
        offset = address - wb_base
        if offset < 0 or offset + 4 > size or offset % 4:
            raise ValueError(f"unsafe Wishbone to Config NoC offset for {name}")
        return {
            "csr": name,
            "config_addr": base + offset,
            "wishbone_byte_addr": address,
            "wishbone_word_addr": address // 4,
            "byte_strobes": 0xF,
        }

    commands = []
    for seq, action in enumerate(actions):
        if action["op"] == "wait":
            cycles = action["cycles"]
            if type(cycles) is not int or cycles < 1:
                raise ValueError("invalid DFII initialization wait cycles")
            commands.append({"seq": seq, "phase": "init", "op": "wait_cycles",
                             "cycles": cycles, "source": action.get("source", "")})
        elif action["op"] == "write":
            item = route(action["csr"], action["byte_address"])
            value = action["value"]
            if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
                raise ValueError("invalid 32-bit DFII control value")
            item.update({"seq": seq, "phase": "init", "op": "config_write32",
                         "value": value, "required_axi_response": "OKAY"})
            commands.append(item)
        else:
            raise ValueError("unsupported standalone initialization operation")

    for name in readback_names:
        read = route(name, registry[name]["addr"])
        read.update({"seq": len(commands), "phase": "init",
                     "op": "config_read32", "required_axi_response": "OKAY",
                     "expect_mask": 1 if name != "sdram_dfii_control" else 1,
                     "expect_value": 0 if name == "ddrctrl_init_error" else 1})
        commands.append(read)
    return {
        "schema_version": 1,
        "status": ("proposed_aperture_not_in_soc" if proposed_window_bytes is not None
                   else "contract_only_not_driven_in_full_chip"),
        "configured_window_bytes": configured_size,
        "proposed_window_bytes": size if proposed_window_bytes is not None else None,
        "ready_for_full_chip": False,
        "requires_config_change": proposed_window_bytes is not None,
        "reuse": "init_plan.wishbone_script; standard INIT/RUN/CHECK host coordinator",
        "config_plane": "global_config -> memory0.local_config",
        "data_plane": "global_data -> memory0.local_data (independent)",
        "controller": DDR, "target_csr": TARGET,
        "config_base": base, "window_bytes": size,
        "generated_wb_base": wb_base,
        "generated_wb_base_status": "derived_from_csr_map" if generated_wb_base is None else "explicit",
        "requires_hardware_translator": True,
        "actions": commands,
        "run_check_requirements": [
            "real controller init_done AND init_error status checked on pins",
            "CPU/iDMA AXI data NoC writes/reads reach real LiteDRAM RTL",
            "independent checker validates data and completed AXI responses",
            "continuous passive AXI/DFI and modeled bank capture",
        ],
        "evidence": "planned transport mapping only; no RTL wishbone bridge or firmware execution",
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--soc", type=Path, default=Path("config/soc.yaml"))
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--csr", type=Path, required=True)
    parser.add_argument("--generated-verilog", type=Path)
    parser.add_argument("--proposed-window-bytes", type=lambda x: int(x, 0),
                        help="test proposed larger SoC CSR window WITHOUT changing config/soc.yaml")
    parser.add_argument("--output", type=Path)
    options = parser.parse_args()
    soc = yaml.safe_load(options.soc.read_text())
    plan = json.loads(options.plan.read_text())
    csr = json.loads(options.csr.read_text())
    wb_adr_bits = None
    if options.generated_verilog:
        from port_contract import emitted_port_widths
        wb_adr_bits = emitted_port_widths(options.generated_verilog.read_text())["wb_ctrl_adr"]
    result = compile_transport(soc, plan, csr,
                               generated_wb_adr_bits=wb_adr_bits,
                               proposed_window_bytes=options.proposed_window_bytes)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(text)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
