#!/usr/bin/env python3
"""Generate C-only existing DMA shim CSR definitions from SystemRDL.

No custom register RTL generation; PULP axi_lite_regs and the existing
soc_dma_regs shim remain the hardware implementation. The config file owns
absolute instance base addresses; this RDL owns only local offsets/fields.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from systemrdl import RDLCompiler
import yaml

ROOT = Path(__file__).resolve().parents[1]
RDL = ROOT / "csr/rdl/soc_dma_shim.rdl"
SOC = ROOT / "config/soc.yaml"
OFFSETS = ("head_lo", "head_hi", "command", "status")
BITS = ("submit", "irq_ack", "apb_busy", "irq_pending", "apb_error", "raw_irq")


class DmaCsrError(ValueError):
    pass


def extract(rdl=RDL):
    compiler = RDLCompiler()
    compiler.compile_file(str(rdl))
    root = compiler.elaborate(top_def_name="soc_dma_shim")
    entries = []
    occupied = set()
    for reg in root.top.registers(unroll=True):
        address = int(reg.absolute_address)
        if address % 4 or address in occupied:
            raise DmaCsrError("duplicate or unaligned DMA register address")
        occupied.add(address)
        fields = []
        for field in reg.fields():
            low, high = int(field.lsb), int(field.msb)
            mask = ((1 << (high - low + 1)) - 1) << low
            fields.append({"name": field.inst_name, "lsb": low, "msb": high,
                           "mask": f"0x{mask:08x}",
                           "access": getattr(field.get_property("sw"), "name").lower()})
        entries.append({"name": reg.inst_name, "offset": address, "size_bytes": reg.size,
                        "fields": fields, "description": reg.get_property("desc", default="") or ""})
    actual = tuple(r["name"] for r in entries)
    if actual != OFFSETS:
        raise DmaCsrError(f"DMA register ABI mismatch: {actual}")
    if tuple(r["offset"] for r in entries) != (0, 4, 8, 12):
        raise DmaCsrError("DMA offset ABI changed")
    expected = {
        "head_lo": {"value": (0, 31, "rw")},
        "head_hi": {"value": (0, 31, "rw")},
        "command": {"submit": (0, 0, "rw"),
                    "irq_ack": (1, 1, "rw")},
        "status": {"apb_busy": (0, 0, "r"),
                   "irq_pending": (1, 1, "r"),
                   "apb_error": (2, 2, "r"),
                   "raw_irq": (3, 3, "r")},
    }
    for reg in entries:
        if reg["size_bytes"] != 4:
            raise DmaCsrError("DMA CSR width changed from 32 bits")
        fields = {}
        occupied_mask = 0
        for field in reg["fields"]:
            mask = int(field["mask"], 16)
            if occupied_mask & mask:
                raise DmaCsrError("overlapping DMA CSR field masks")
            occupied_mask |= mask
            if field["name"] in fields:
                raise DmaCsrError("duplicate DMA CSR field name")
            fields[field["name"]] = (field["lsb"], field["msb"], field["access"])
        if fields != expected[reg["name"]]:
            raise DmaCsrError(
                f"DMA CSR field width/position/access ABI changed: {reg['name']} {fields}")
    return entries


def header(entries):
    lines = ["/* Generated from csr/rdl/soc_dma_shim.rdl; NEVER edit. */",
             "#ifndef SOC_DMA_SHIM_REGS_H", "#define SOC_DMA_SHIM_REGS_H",
             "#include <stdint.h>", ""]
    for reg in entries:
        name = reg["name"].upper()
        lines.append(f"#define SOC_DMA_SHIM_{name}_OFFSET UINT32_C(0x{reg['offset']:x})")
        for field in reg["fields"]:
            if field["name"] in BITS:
                lines.append(f"#define SOC_DMA_SHIM_{name}_{field['name'].upper()}_MASK UINT32_C({field['mask']})")
    lines.append("")
    # Generated ABI compatibility aliases replace duplicated manually defined
    # offsets and bit masks. Existing driver source remains untouched initially.
    for reg in entries:
        stem = reg["name"].upper()
        lines.append(f"#define SOC_DMA_REG_{stem} SOC_DMA_SHIM_{stem}_OFFSET")
    aliases = {
        "SOC_DMA_CMD_SUBMIT": "COMMAND_SUBMIT",
        "SOC_DMA_CMD_IRQ_ACK": "COMMAND_IRQ_ACK",
        "SOC_DMA_STATUS_APB_BUSY": "STATUS_APB_BUSY",
        "SOC_DMA_STATUS_IRQ": "STATUS_IRQ_PENDING",
        "SOC_DMA_STATUS_APB_ERROR": "STATUS_APB_ERROR",
        "SOC_DMA_STATUS_RAW_IRQ": "STATUS_RAW_IRQ",
    }
    lines += [f"#define {legacy} SOC_DMA_SHIM_{canonical}_MASK" for legacy, canonical in aliases.items()]
    lines += ["", "#endif /* SOC_DMA_SHIM_REGS_H */", ""]
    return "\n".join(lines)


def catalog(entries, config=SOC, rdl=RDL):
    cfg = yaml.safe_load(Path(config).read_text())
    # The existing socgen module imports sibling tools as top-level modules.
    # Make that import resolution explicit rather than relying on CLI cwd.
    import sys
    tool_root = str(ROOT / 'tools')
    if tool_root not in sys.path:
        sys.path.insert(0, tool_root)
    import socgen
    socgen.validate(cfg)
    config_apertures = {r["name"]: r for r in cfg["address_map"]["config"]}
    instances = []
    for core in cfg["subsystems"]:
        if core["type"] != "compute":
            continue
        name = core["name"] + ".dma"
        aperture = config_apertures[name]
        base = int(aperture["base"], 0)
        size = int(aperture["size"], 0)
        if size < 16 or base % 4:
            raise DmaCsrError("SoC DMA aperture too small or misaligned")
        instances.append({"name": name, "base": hex(base), "size": hex(size),
                          "status": "external_existing_rtl_not_generated",
                          "registers": [{**r, "address": hex(base + r["offset"])}
                                        for r in entries]})
    return {"schema_version": 1, "ip": "soc_dma_shim",
            "source_sha256": hashlib.sha256(Path(rdl).read_bytes()).hexdigest(),
            "config_sha256": hashlib.sha256(Path(config).read_bytes()).hexdigest(),
            "rtl_owner": "rtl/adapters/soc_dma_regs.sv",
            "registers_are_external": True, "instances": instances}


def emit(out, *, check=False):
    entries = extract()
    contents = {
        "soc_dma_shim_regs.h": header(entries),
        "soc_dma_shim_map.json": json.dumps(catalog(entries), indent=2, sort_keys=True) + "\n",
    }
    out = Path(out)
    if check:
        differing = [name for name, value in contents.items()
                     if not (out / name).is_file() or (out / name).read_text() != value]
        if differing:
            raise DmaCsrError(f"generated DMA CSR files differ: {differing}")
        return
    out.mkdir(parents=True, exist_ok=True)
    for name, value in contents.items():
        (out / name).write_text(value)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=ROOT / ".tools/csr-dma")
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    emit(args.out, check=args.check)


if __name__ == "__main__":
    main()
