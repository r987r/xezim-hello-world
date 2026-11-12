#!/usr/bin/env python3
"""Generate PCIe endpoint CPU-owned CSR bank from the ONE SystemRDL source.

This is a sibling of tools/csrgen.py. It uses the repository's exact pinned
SystemRDL/PeakRDL versions and AXI4-Lite flattened interface, and NEVER
replaces the host-visible Type-0 PCIe configuration register bank.

The 0x1000 management subwindow of pcie0.ctrl is a nonoverlapping sibling of
the already-qualified outbound requester at 0x0..0x3f. Generating RTL is NOT
evidence that a CPU/Config-NoC frontdoor has been connected.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import shutil
import sys
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
RDL = ROOT / "csr/rdl/pcie_endpoint_prelink_ctrl.rdl"
SOC = ROOT / "config/soc.yaml"
OUTPUT = ROOT / "gen/pcie/csr"
MARKER = ".pcie-csr-generated"
VERSIONS = {
    "systemrdl-compiler": "1.33.0",
    "peakrdl-regblock": "1.3.1",
    "peakrdl-cheader": "1.1.0",
}
EXPECTED = (
    ("bar0_aperture", 0x1000, {"size_bytes": (0, 31, "rw")}),
    ("bar0_target", 0x1004, {"local_base": (0, 31, "rw")}),
    ("control", 0x1008, {"commit": (0, 0, "w"), "start": (1, 1, "w")}),
    ("status", 0x100c, {"committed": (0, 0, "r"), "ltssm_allowed": (1, 1, "r"),
                        "mem_ready": (2, 2, "r"), "violation": (3, 3, "r")}),
    ("host_bar0", 0x1010, {"pci_bus_base": (4, 31, "r")}),
    ("host_command", 0x1014, {"memory_space_enable": (1, 1, "r")}),
    ("link_status", 0x1018, {"ltssm_l0": (0, 0, "r"),
                             "phy_ready": (1, 1, "r"),
                             "noc_ready": (2, 2, "r"),
                             "host_config_error": (3, 3, "r")}),
)


class PcieCsrError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def as_int(value) -> int:
    if type(value) is int:
        return value
    if isinstance(value, str):
        return int(value, 0)
    raise PcieCsrError(f"invalid SoC address value: {value!r}")


def config_aperture(config: Path = SOC) -> dict:
    cfg = yaml.safe_load(config.read_text())
    rows = [r for r in cfg["address_map"]["config"] if r["name"] == "pcie0.ctrl"]
    if len(rows) != 1:
        raise PcieCsrError("expected exactly one configured pcie0.ctrl aperture")
    item = rows[0]
    base, size = as_int(item["base"]), as_int(item["size"])
    if base & 3 or size < 0x101c or base + size > 0x100000000:
        raise PcieCsrError("pcie0.ctrl must be aligned, >=0x101c bytes and 32-bit")
    return {"name": "pcie0.ctrl", "base": base, "size": size}


def compile_rdl(path: Path = RDL):
    from systemrdl import RDLCompiler
    from peakrdl_regblock.udps import ALL_UDPS
    compiler = RDLCompiler()
    for udp in ALL_UDPS:
        compiler.register_udp(udp)
    compiler.compile_file(str(path))
    return compiler.elaborate(top_def_name="pcie_endpoint_prelink_ctrl")


def registers(root, aperture: dict) -> list[dict]:
    output = []
    reserved_start, reserved_end = 0, 0x40
    for reg in root.top.registers(unroll=True):
        address = int(reg.absolute_address)
        width = int(reg.get_property("regwidth"))
        if width != 32 or reg.size != 4 or address % 4:
            raise PcieCsrError(f"{reg.inst_name}: require aligned 32-bit register")
        if not (address >= reserved_end and address + 4 <= aperture["size"]):
            raise PcieCsrError(f"{reg.inst_name}: overlaps requester or outside pcie0.ctrl")
        fields = {}
        used_mask = 0
        for field in reg.fields():
            lo, hi = int(field.lsb), int(field.msb)
            mask = ((1 << (hi-lo+1))-1) << lo
            if mask & used_mask:
                raise PcieCsrError(f"{reg.inst_name}: overlapping bit fields")
            used_mask |= mask
            access = field.get_property("sw")
            access = getattr(access, "name", str(access)).lower()
            fields[field.inst_name] = (lo, hi, access)
            if field.get_property("csr_backdoor_policy", default="frontdoor_only") != "frontdoor_only":
                raise PcieCsrError(f"{reg.inst_name}.{field.inst_name}: unsafe CSR backdoor")
            if int(field.get_property("reset", default=0)) != 0:
                raise PcieCsrError(f"{reg.inst_name}.{field.inst_name}: unexpected reset value")
            if reg.inst_name=="control" and not field.get_property("singlepulse"):
                raise PcieCsrError(f"{field.inst_name}: commit/start must be one-cycle pulses")
            # A DBI alias must read the live ORIGINAL host-owned value, not
            # introduce a second CPU-writable BAR0 or COMMAND register.
            if reg.inst_name in ("status","host_bar0","host_command","link_status"):
                hw=field.get_property("hw")
                hw=getattr(hw,"name",str(hw)).lower()
                if access!="r" or hw!="w":
                    raise PcieCsrError(
                        f"{reg.inst_name}.{field.inst_name}: DBI aliases/status must be CPU read-only, hardware-driven")
            if reg.inst_name in ("bar0_aperture","bar0_target"):
                if not field.get_property("swwe"):
                    raise PcieCsrError(
                        f"{reg.inst_name}.{field.inst_name}: missing hardware pre-link commit write-freeze gate")
        output.append({
            "name": reg.inst_name, "offset": address,
            "address": aperture["base"] + address,
            "width_bits": width,
            "access": "mixed" if len({f[2] for f in fields.values()}) > 1
                else next(iter(fields.values()))[2],
            "fields": [
                {"name": name, "lsb": values[0], "msb": values[1],
                 "access": values[2],
                 "mask": f"0x{(((1 << (values[1]-values[0]+1))-1) << values[0]):08x}",
                 "reset": "0x0",
                 "backdoor_policy": "frontdoor_only"}
                for name, values in fields.items()
            ],
        })
    actual = [(r["name"],r["offset"],
               {f["name"]:(f["lsb"],f["msb"],f["access"]) for f in r["fields"]})
              for r in output]
    if actual != list(EXPECTED):
        raise PcieCsrError(f"PCIe management ABI/field access mismatch: {actual}")
    if len(set(r["offset"] for r in output)) != len(output):
        raise PcieCsrError("duplicate PCIe management register addresses")
    return output


def header(rows: list[dict], base: int, size: int) -> str:
    lines = [
        "/* GENERATED from csr/rdl/pcie_endpoint_prelink_ctrl.rdl; do not edit. */",
        "#ifndef SOC_PCIE_EP_PRELINK_REGS_H",
        "#define SOC_PCIE_EP_PRELINK_REGS_H",
        "#include <stdint.h>",
        "",
        f"#define SOC_PCIE_EP_CTRL_BASE UINT32_C(0x{base:08x})",
        f"#define SOC_PCIE_EP_CTRL_APERTURE_BYTES UINT32_C(0x{size:x})",
        "",
    ]
    for reg in rows:
        stem = "SOC_PCIE_EP_" + reg["name"].upper()
        lines.append(f"#define {stem}_OFFSET UINT32_C(0x{reg['offset']:x})")
        for field in reg["fields"]:
            key = stem + "_" + field["name"].upper()
            lines += [
                f"#define {key}_SHIFT {field['lsb']}u",
                f"#define {key}_MASK UINT32_C({field['mask']})",
            ]
    lines.extend(["", "#endif /* SOC_PCIE_EP_PRELINK_REGS_H */", ""])
    return "\n".join(lines)


def generate(config: Path, rdl: Path, out: Path) -> None:
    for package, expected in VERSIONS.items():
        if version(package) != expected:
            raise PcieCsrError(f"{package}: version drift (expected {expected})")
    aperture = config_aperture(config)
    root = compile_rdl(rdl)
    rows = registers(root, aperture)
    from peakrdl_regblock import RegblockExporter
    from peakrdl_regblock.cpuif.axi4lite import AXI4Lite_Cpuif_flattened
    out.mkdir(parents=True, exist_ok=True)
    (out / MARKER).write_text("pcie-csrgen-v1\n")
    (out / "soc_pcie_ep_prelink_regs.h").write_text(
        header(rows, aperture["base"], aperture["size"]))
    (out / "rtl").mkdir(parents=True, exist_ok=True)
    RegblockExporter().export(
        root, str(out / "rtl"), cpuif_cls=AXI4Lite_Cpuif_flattened,
        module_name="soc_pcie_ep_prelink_regblock",
        package_name="soc_pcie_ep_prelink_regblock_pkg",
        default_reset_activelow=True, address_width=16,
        err_if_bad_addr=True, err_if_bad_rw=True,
    )
    (out / "csr-map.json").write_text(json.dumps({
        "schema_version":1,
        "ip":"pcie_endpoint_prelink_ctrl",
        "instance":"pcie0.endpoint_prelink",
        "configuration_domain":"soc_cpu_config_noc",
        "host_pcie_configuration_space":"distinct_vendor_type0_rdl",
        "shared_host_state_aliases":{
            "host_type0_bar0":{"pcie_config_offset":"0x10",
                               "cpu_dbi_offset":"0x1010",
                               "cpu_access":"read_only",
                               "owner":"original_host_config_tlp"},
            "host_type0_command_mse":{"pcie_config_offset":"0x04",
                                      "cpu_dbi_offset":"0x1014",
                                      "cpu_access":"read_only",
                                      "owner":"original_host_config_tlp"},
            "storage_policy":"one_writer_original_host_config_no_independent_dbi_bar_state"
        },
        "base":f"0x{aperture['base']:08x}",
        "window_size_bytes":aperture["size"],
        "requester_reserved_offsets":"0x0000..0x003f",
        "rdl_sha256":digest(rdl.read_bytes()),
        "soc_config_sha256":digest(config.read_bytes()),
        "generator":VERSIONS,
        "registers":rows,
        "generated_rtl_attached_to_full_chip":False,
        "cpu0_frontdoor_verified":False,
        "note":"Generated register storage only; policy glue and real NoC acceptance not yet qualified."
    }, indent=2, sort_keys=True)+"\n")


def files(directory: Path) -> dict[str,bytes]:
    return {p.relative_to(directory).as_posix():p.read_bytes()
            for p in directory.rglob("*") if p.is_file()} if directory.exists() else {}


def execute(config: Path, rdl: Path, out: Path, check: bool) -> int:
    if out.is_symlink() or out.exists() and not (out / MARKER).is_file():
        raise PcieCsrError("refusing to overwrite path without PCIe CSR marker")
    with tempfile.TemporaryDirectory(prefix="pcie-csrgen-") as tmp:
        candidate = Path(tmp) / "csr"
        generate(config, rdl, candidate)
        produced = files(candidate)
        if check:
            existing = files(out)
            changed = sorted(produced.keys() ^ existing.keys())
            changed += sorted(name for name in produced.keys() & existing.keys()
                              if produced[name] != existing[name])
            if changed:
                print("PCIe generated CSR drift: "+str(changed),file=sys.stderr)
                return 1
            print(f"PASS: {len(produced)} exact generated PCIe CSR files")
            return 0
        if out.exists():
            shutil.rmtree(out)
        out.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(candidate,out)
        print(f"Generated {len(produced)} PCIe CSR artifacts: {out}")
        return 0


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config",type=Path,default=SOC)
    p.add_argument("--rdl",type=Path,default=RDL)
    p.add_argument("--out",type=Path,default=OUTPUT)
    p.add_argument("--check",action="store_true")
    a=p.parse_args()
    try:
        return execute(a.config,a.rdl,a.out,a.check)
    except (OSError,ValueError,KeyError,ImportError,PcieCsrError) as err:
        print(f"PCIe CSR generation failed: {err}",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
