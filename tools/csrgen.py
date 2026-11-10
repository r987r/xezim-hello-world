#!/usr/bin/env python3
"""Reproducible SystemRDL/PeakRDL CSR artifacts for project-owned register banks.

Does NOT replace any active PULP register RTL or update gen/chip. Source-of-truth:
config/soc.yaml for absolute apertures and csr/rdl for relative register fields.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
RDL = ROOT / "csr/rdl/boot_reset_ctrl.rdl"
CONFIG = ROOT / "config/soc.yaml"
OUTPUT = ROOT / "csr/generated"
MARKER = ".csr-generated"
VERSIONS = {
    "systemrdl-compiler": "1.33.0",
    "peakrdl-regblock": "1.3.1",
    "peakrdl-cheader": "1.1.0",
}


class CsrError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def as_int(value) -> int:
    if type(value) is int:
        return value
    if isinstance(value, str):
        return int(value, 0)
    raise CsrError(f"invalid integer: {value!r}")


def identifier(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name):
        raise CsrError(f"unsupported register identifier: {name}")
    return name.upper()


def validate_config(cfg: dict) -> tuple[list[dict], list[str]]:
    # Reuse existing SoC contract checks rather than a second address decoder.
    import socgen
    socgen.validate(cfg)
    cores = [s["name"] for s in cfg["subsystems"] if s["type"] == "compute"]
    if not 2 <= len(cores) <= 16:
        raise CsrError("reset register supports 2..16 configured compute cores")
    apertures = cfg["address_map"]["config"]
    names = [r["name"] for r in apertures]
    if names.count("boot.reset_ctrl") != 1:
        raise CsrError("exactly one boot.reset_ctrl aperture required")
    return apertures, cores


def compile_rdl(path: Path, n_secondary: int):
    from systemrdl import RDLCompiler
    from peakrdl_regblock.udps import ALL_UDPS
    compiler = RDLCompiler()
    # The regblock scanner requires its registered RDL extension properties
    # even for registers that do not exercise write/read buffering.
    for udp in ALL_UDPS:
        compiler.register_udp(udp)
    compiler.compile_file(str(path))
    root = compiler.elaborate(top_def_name="boot_reset_ctrl", parameters={"SECONDARY_COUNT": n_secondary})
    return root


def register_layout(root, aperture_size: int) -> list[dict]:
    regs: list[dict] = []
    occupied: list[tuple[int, int]] = []
    for reg in root.top.registers(unroll=True):
        offset = reg.absolute_address
        size = reg.size
        width = int(reg.get_property("regwidth"))
        if width != 32 or size != 4 or offset % 4:
            raise CsrError(f"{reg.inst_name}: expected aligned 32-bit register")
        if offset < 0 or offset + size > aperture_size:
            raise CsrError(f"{reg.inst_name}: exceeds SoC CSR aperture")
        if any(offset < end and start < offset + size for start, end in occupied):
            raise CsrError(f"{reg.inst_name}: overlapping register address")
        occupied.append((offset, offset + size))
        fields = []
        used_bits = 0
        for field in reg.fields():
            lsb, msb = int(field.lsb), int(field.msb)
            if not (0 <= lsb <= msb < width):
                raise CsrError(f"{reg.inst_name}.{field.inst_name}: invalid field bits")
            mask = ((1 << (msb - lsb + 1)) - 1) << lsb
            if used_bits & mask:
                raise CsrError(f"{reg.inst_name}: overlapping field bits")
            used_bits |= mask
            sw = field.get_property("sw")
            sw = getattr(sw, "name", str(sw)).lower()
            fields.append({
                "name": field.inst_name,
                "lsb": lsb,
                "msb": msb,
                "mask": f"0x{mask:08x}",
                "access": sw,
                "backdoor_policy": field.get_property("csr_backdoor_policy", default="frontdoor_only"),
                "reset": f"0x{int(field.get_property('reset', default=0)):x}",
                "description": field.get_property("desc", default="") or "",
            })
        regs.append({
            "name": reg.get_path_segment(),
            "offset": f"0x{offset:x}",
            "width_bits": width,
            "size_bytes": size,
            "access": "mixed" if len({f["access"] for f in fields}) > 1 else fields[0]["access"],
            "reset": "0x0",
            "description": reg.get_property("desc", default="") or "",
            "fields": fields,
        })
    expected = ["cpu_release", *[f"secondary_ack[{i}]" for i in range(root.top.parameters["SECONDARY_COUNT"])]]
    if ([r["name"] for r in regs] != expected
            or [as_int(r["offset"]) for r in regs] != [4*i for i in range(len(expected))]):
        raise CsrError("reset register ABI drift: expected release plus one peer acknowledgement per secondary")
    # A source-compatible offset is not a compatible firmware ABI if the
    # access policy, reset value or field width changes underneath software.
    # These rules are for the existing boot/reset bank only; do not invent
    # policies for reserved or upstream vendor CSR windows.
    n_secondary = root.top.parameters["SECONDARY_COUNT"]
    for index, reg in enumerate(regs):
        fields = reg["fields"]
        expected_name = "secondary_release" if index == 0 else "ack"
        expected_mask = (1 << n_secondary)-1 if index == 0 else 0xffffffff
        if (len(fields) != 1 or fields[0]["name"] != expected_name
                or fields[0]["lsb"] != 0
                or fields[0]["msb"] != (n_secondary-1 if index == 0 else 31)
                or int(fields[0]["mask"], 0) != expected_mask
                or fields[0]["access"] != "rw"
                or int(fields[0]["reset"], 0) != 0
                or fields[0]["backdoor_policy"] != "frontdoor_only"):
            raise CsrError(f"{reg['name']}: reset CSR software field ABI drift")
    return regs


def header(regs: list[dict]) -> str:
    lines = [
        "/* Generated from SystemRDL; do not edit. */",
        "#ifndef SOC_BOOT_RESET_CTRL_REGS_H",
        "#define SOC_BOOT_RESET_CTRL_REGS_H",
        "#include <stdint.h>",
        "",
    ]
    for reg in regs:
        name = identifier(reg["name"].replace("[", "_").replace("]", ""))
        lines.append(f"#define SOC_BOOT_RESET_CTRL_{name}_OFFSET UINT32_C({reg['offset']})")
        for field in reg["fields"]:
            stem = f"SOC_BOOT_RESET_CTRL_{name}_{identifier(field['name'])}"
            lines += [
                f"#define {stem}_SHIFT {field['lsb']}u",
                f"#define {stem}_MASK UINT32_C({field['mask']})",
            ]
    lines += ["", "#endif /* SOC_BOOT_RESET_CTRL_REGS_H */", ""]
    return "\n".join(lines)


def bases_header(apertures: list[dict]) -> str:
    lines = [
        "/* Generated SoC CSR physical bases; these macros emit no executable code. */",
        "#ifndef SOC_CSR_BASES_H",
        "#define SOC_CSR_BASES_H",
        "#include <stdint.h>",
        "",
    ]
    for region in sorted(apertures, key=lambda r: r["name"]):
        stem = identifier(region["name"].replace(".", "_"))
        lines.append(f"#define SOC_CSR_{stem}_BASE UINT32_C(0x{as_int(region['base']):08x})")
        lines.append(f"#define SOC_CSR_{stem}_SIZE UINT32_C(0x{as_int(region['size']):x})")
    lines += ["", "#endif /* SOC_CSR_BASES_H */", ""]
    return "\n".join(lines)


def generate(config: Path, rdl: Path, out: Path, variant: str) -> None:
    if variant != "cold_boot":
        raise CsrError("only the cold_boot RTL attachment is qualified in CSR-1")
    for package, expected in VERSIONS.items():
        found = version(package)
        if found != expected:
            raise CsrError(f"{package} version {found} != pinned {expected}")
    cfg = yaml.safe_load(config.read_text())
    apertures, cores = validate_config(cfg)
    reset_window = next(r for r in apertures if r["name"] == "boot.reset_ctrl")
    root = compile_rdl(rdl, len(cores) - 1)
    regs = register_layout(root, as_int(reset_window["size"]))

    from peakrdl_cheader.exporter import CHeaderExporter
    from peakrdl_regblock import RegblockExporter
    from peakrdl_regblock.cpuif.axi4lite import AXI4Lite_Cpuif_flattened

    out.mkdir(parents=True, exist_ok=True)
    (out / MARKER).write_text("csrgen-v1\n")
    (out / "soc_boot_reset_ctrl_regs.h").write_text(header(regs))
    (out / "soc_csr_bases.h").write_text(bases_header(apertures))
    CHeaderExporter().export(node=root, path=str(out / "boot_reset_ctrl_types.h"))
    (out / "rtl").mkdir(parents=True, exist_ok=True)
    RegblockExporter().export(
        root, str(out / "rtl"), cpuif_cls=AXI4Lite_Cpuif_flattened,
        module_name="soc_boot_reset_ctrl_regblock",
        package_name="soc_boot_reset_ctrl_regblock_pkg",
        default_reset_activelow=True,
        address_width=12,
        err_if_bad_addr=True,
        err_if_bad_rw=True,
    )
    catalog = {
        "schema_version": 1,
        "variant": variant,
        "config_sha256": digest(config.read_bytes()),
        "rdl_sha256": digest(rdl.read_bytes()),
        "generator": {**VERSIONS},
        "register_count": len(regs),
        "instances": [],
    }
    for region in apertures:
        name = region["name"]
        implemented = name == "boot.reset_ctrl"
        # Other apertures cannot be described as live registers in cold boot.
        catalog["instances"].append({
            "name": name,
            "base": f"0x{as_int(region['base']):x}",
            "size": f"0x{as_int(region['size']):x}",
            "status": "implemented" if implemented else "unmapped_or_disabled",
            "source": "SystemRDL" if implemented else "SoC aperture only",
            "registers": regs if implemented else [],
        })
    (out / "csr-map.json").write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n")


def contents(path: Path) -> dict[str, bytes]:
    return {p.relative_to(path).as_posix(): p.read_bytes()
            for p in path.rglob("*") if p.is_file()} if path.exists() else {}


def execute(config: Path, rdl: Path, output: Path, variant: str, check: bool) -> int:
    if output.is_symlink():
        raise CsrError("refusing symlink CSR output")
    if output.exists() and not (output / MARKER).is_file():
        raise CsrError("refusing to replace directory without CSR ownership marker")
    with tempfile.TemporaryDirectory(prefix="csrgen-") as scratch:
        candidate = Path(scratch) / "csr"
        generate(config, rdl, candidate, variant)
        new = contents(candidate)
        if check:
            old = contents(output)
            differences = [f"missing {p}" for p in sorted(new.keys() - old.keys())]
            differences += [f"stale {p}" for p in sorted(old.keys() - new.keys())]
            differences += [f"changed {p}" for p in sorted(new.keys() & old.keys()) if new[p] != old[p]]
            if differences:
                print("\n".join(differences), file=sys.stderr)
                return 1
            print(f"PASS: {len(new)} deterministic CSR outputs")
            return 0
        if output.exists():
            shutil.rmtree(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(candidate, output)
        print(f"Generated {len(new)} CSR files into {output}")
        return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=CONFIG)
    p.add_argument("--rdl", type=Path, default=RDL)
    p.add_argument("--out", type=Path, default=OUTPUT)
    p.add_argument("--variant", default="cold_boot")
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    try:
        return execute(args.config, args.rdl, args.out, args.variant, args.check)
    except (CsrError, ValueError, OSError, KeyError, ImportError) as exc:
        print(f"CSR generation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
