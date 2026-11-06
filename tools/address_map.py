#!/usr/bin/env python3
"""One SoC address-space catalog: RAM/ROM/DDR/HBM windows and CSR submaps.

Physical apertures always come from config/soc.yaml. SystemRDL adds relative
register definitions only. An address map is NOT proof that backing RTL or a
hardware transaction exists. This module does not generate/interpose RTL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/soc.yaml"


class AddressMapError(ValueError):
    pass


def number(value):
    if type(value) is int:
        return value
    if isinstance(value, str):
        return int(value, 0)
    raise AddressMapError(f"invalid address/size: {value!r}")


def hx(value):
    return f"0x{value:x}"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def classify(plane, name, cfg):
    if plane == "config":
        return "csr_aperture"
    suffix = name.rsplit(".", 1)[-1]
    if suffix in ("rom", "flash", "sram"):
        return suffix
    return next((target["kind"] for target in cfg.get("memory_targets", [])
                 if target["name"] == name), "memory_aperture")


def model_capacity(cfg, name, kind, arch_size):
    """Advertise a configured modeled capacity, not an actual RTL proof."""
    if kind == "sram":
        value = number(cfg["boot"]["simulation_sram_bytes"])
    elif kind == "ddr" and any(
            target["name"] == name and target.get("simulation", {}).get("backend") == "litedram_sim"
            for target in cfg.get("memory_targets", [])):
        # DDR-B's pinned real LiteDRAM DFI/BankModel preflight validates the
        # low 32 MiB, not the default fast-AXI-RAM model's 64 KiB.
        value = 32 * 1024 * 1024
    elif kind in ("ddr", "hbm"):
        value = 1 << number(cfg["verification"]["memory"]["model_address_bits"])
    else:
        return None
    if value <= 0 or value > arch_size:
        raise AddressMapError(f"{name}: modeled capacity exceeds physical window")
    return value


def build(config_path=CONFIG, *, csr_path=None, variant="architecture"):
    """Compose independent data and config planes without unifying their buses."""
    config_path = Path(config_path)
    cfg = yaml.safe_load(config_path.read_text())
    # Default SoC uses the normal strict validator. The opt-in DDR-B variant
    # is allowed only if it is EXACTLY the deterministic transform of the
    # checked-in baseline, not an arbitrary alternative/relaxed SoC YAML.
    import socgen
    if variant == "ddr_real":
        from ddr_chip import variant_configuration
        baseline = yaml.safe_load(CONFIG.read_text())
        if cfg != variant_configuration(baseline):
            raise AddressMapError("DDR CSR variant differs from the pinned real-LiteDRAM SoC composition")
        for plane in ("data", "config"):
            socgen.check_region_map(cfg["address_map"][plane],
                                    number(cfg["buses"][plane]["addr_bits"]), plane)
    else:
        socgen.validate(cfg)

    if not isinstance(variant, str) or not re.fullmatch(r"[a-zA-Z_][\w.-]*", variant):
        raise AddressMapError("invalid exact-build variant identifier")
    config_sha = sha(config_path)
    catalog = None
    if csr_path is not None:
        catalog = json.loads(Path(csr_path).read_text())
        if (catalog.get("schema_version") != 1
                or catalog.get("config_sha256") != config_sha
                or catalog.get("variant") != variant):
            raise AddressMapError("stale/foreign SystemRDL catalog or SoC variant")

    regions = []
    for plane in ("data", "config"):
        width = number(cfg["buses"][plane]["addr_bits"])
        for item in cfg["address_map"][plane]:
            name, base, size = item["name"], number(item["base"]), number(item["size"])
            if base < 0 or size <= 0 or base + size > 1 << width:
                raise AddressMapError(f"{name}: invalid {plane} address window")
            kind = classify(plane, name, cfg)
            modeled = model_capacity(cfg, name, kind, size)
            target = next((t for t in cfg.get("memory_targets", [])
                           if t["name"] == name), None)
            row = {
                "plane": plane, "name": name,
                "base": hx(base), "size": hx(size),
                "end_exclusive": hx(base + size),
                "kind": kind, "owner": name.split(".")[0],
                "architecture_status": "declared_aperture",
                "implementation_status": "not_qualified_for_this_variant",
                "registers": [],
                "modeled_capacity_bytes": modeled,
                "modeled_backing_declared": (
                    target.get("simulation", {}).get("backend") if target else None),
                "physical_controller_declared": target.get("controller") if target else None,
                "cpu32_direct_data_addressable": plane == "data" and base + size <= 1 << 32,
            }
            regions.append(row)

    if catalog is not None:
        config_by_name = {r["name"]: r for r in regions if r["plane"] == "config"}
        encountered = set()
        for entry in catalog.get("instances", []):
            name = entry["name"]
            if name in encountered or name not in config_by_name:
                raise AddressMapError(f"unexpected or duplicate CSR instance: {name}")
            encountered.add(name)
            mapped = config_by_name[name]
            base, size = number(entry["base"]), number(entry["size"])
            if (base != number(mapped["base"]) or size != number(mapped["size"])):
                raise AddressMapError(f"{name}: CSR base/aperture disagrees with SoC")
            registers = entry.get("registers", [])
            if registers and entry.get("status") != "implemented":
                raise AddressMapError(f"{name}: registers defined in an unavailable window")
            if not isinstance(registers, list):
                raise AddressMapError(f"{name}: invalid register list")
            occupied = []
            for register in registers:
                offset = number(register["offset"])
                bytes_ = number(register.get("size_bytes", 4))
                bits = number(register["width_bits"])
                if (offset < 0 or bytes_ <= 0 or offset % bytes_
                        or bytes_ * 8 != bits or offset + bytes_ > size):
                    raise AddressMapError(f"{name}.{register['name']}: invalid register bounds")
                if any(offset < hi and lo < offset + bytes_ for lo, hi in occupied):
                    raise AddressMapError(f"{name}: overlapping SystemRDL registers")
                occupied.append((offset, offset + bytes_))
                masks = 0
                for field in register.get("fields", []):
                    lsb, msb = number(field["lsb"]), number(field["msb"])
                    if lsb < 0 or msb < lsb or msb >= bits:
                        raise AddressMapError(f"{name}: invalid SystemRDL field slice")
                    mask = ((1 << (msb - lsb + 1)) - 1) << lsb
                    if mask & masks:
                        raise AddressMapError(f"{name}: overlapping SystemRDL fields")
                    masks |= mask
                mapped["registers"].append({
                    **register, "address": hx(base + offset),
                    "definition_status": (
                        "native_LiteDRAM_generated_CSR_not_bus_coverage"
                        if entry.get("source") == "LiteDRAM native csr.json"
                        else "SystemRDL_defined_not_RTL_proof"),
                })
            if registers:
                mapped["implementation_status"] = "register_map_defined_RTL_unverified"
        # A catalog may mention only owned CSRs, but never arbitrary unmapped IP.
    return {
        "schema_version": 1, "soc_name": cfg["name"], "variant": variant,
        "config_sha256": config_sha,
        "csr_source_sha256": sha(csr_path) if csr_path is not None else None,
        "planes": [
            {"name": p, "addr_bits": number(cfg["buses"][p]["addr_bits"]),
             "protocol": cfg["buses"][p]["protocol"]}
            for p in ("data", "config")
        ],
        "regions": regions,
        "note": "Architectural windows and generated CSR definitions are not RTL access/coverage evidence. Data and configuration travel over separate networks.",
    }


def observe(catalog, axi_rows, *, complete_capture):
    """Annotate source-true initiator transactions; never synthesize AXI data."""
    result = json.loads(json.dumps(catalog))
    if result.get("schema_version") != 1:
        raise AddressMapError("unsupported address-map catalog schema")
    for region in result["regions"]:
        base, end = number(region["base"]), number(region["end_exclusive"])
        associated = []
        for tx in axi_rows:
            if tx.get("role") != "initiator" or tx.get("plane") != region["plane"]:
                continue
            address = number(tx["address"])
            # AXI request may be a burst; boundaries may repeat the transfer.
            request = tx.get("request") or {}
            bytes_per_beat = 1 << number(request.get("size", 0))
            beats = number(tx.get("expected_beats", 1))
            if bytes_per_beat < 1 or beats < 1 or address >= end or address + bytes_per_beat * beats <= base:
                continue
            associated.append(tx)
        complete = [r for r in associated if r.get("status") == "complete"]
        good = [r for r in complete if r.get("response") is not None
                and number(r["response"]) in (0, 1)]
        bad = [r for r in complete if r not in good]
        incomplete = len(associated) - len(complete)
        stats = {
            "capture": "measured" if complete_capture else "unmeasured",
            "reads_ok": sum(r["operation"] == "read" for r in good),
            "writes_ok": sum(r["operation"] == "write" for r in good),
            "errors": len(bad), "incomplete": incomplete,
            "observation_status": (
                "unmeasured" if not complete_capture else
                "incomplete_or_error" if bad or incomplete else
                "observed_complete" if good else "not_accessed"
            ),
        }
        region["observations"] = stats
        for reg in region["registers"]:
            addr, end_reg = number(reg["address"]), number(reg["address"]) + number(reg.get("size_bytes", 4))
            hits = [tx for tx in associated if addr <= number(tx["address"]) < end_reg]
            reg["observations"] = {
                "capture": stats["capture"],
                "completed": sum(tx.get("status") == "complete" for tx in hits),
                "errors_or_incomplete": sum(tx.get("status") != "complete"
                    or tx.get("response") is None
                    or number(tx["response"]) > 1 for tx in hits),
                "status": ("unmeasured" if not complete_capture else
                           "not_accessed" if not hits else
                           "incomplete_or_error" if any(
                               tx.get("status") != "complete"
                               or tx.get("response") is None
                               or number(tx["response"]) > 1 for tx in hits)
                           else "observed_complete"),
            }
    return result


def memory_rdl_view(catalog):
    """Read-only RDL external-memory view, not a new SoC/NoC RTL generator.

    Config and third-party CSR apertures are kept in the JSON catalog until
    their actual native RDL definition is imported, not misrepresented as RAM.
    """
    if catalog.get("schema_version") != 1:
        raise AddressMapError("unsupported map schema")
    names = set()
    lines = [
        "// Generated architectural external memory view from config/soc.yaml.",
        "// NEVER use this to instantiate SRAM/ROM/DDR/HBM or replace FlooNoC.",
        "addrmap soc_data_memory_view {",
    ]
    for r in catalog["regions"]:
        if r["plane"] != "data":
            continue
        name = re.sub(r"[^A-Za-z0-9_]", "_", r["name"])
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) or name in names:
            raise AddressMapError(f"invalid/duplicate RDL memory identifier: {name}")
        names.add(name)
        width = 64
        size = number(r["size"])
        if size % (width // 8):
            raise AddressMapError("external memory window is not an integral number of bus words")
        access = "r" if r["kind"] in ("rom", "flash") else "rw"
        lines += [
            "    external mem {",
            f"        memwidth = {width};",
            f"        mementries = {size // (width // 8)};",
            f"        sw = {access};",
            f"    }} {name} @ {r['base']};",
        ]
    lines += ["};", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--csr-map", type=Path)
    parser.add_argument("--variant", default="architecture")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rdl-out", type=Path)
    args = parser.parse_args()
    catalog = build(args.config, csr_path=args.csr_map, variant=args.variant)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(catalog, sort_keys=True, indent=2) + "\n")
    if args.rdl_out:
        args.rdl_out.parent.mkdir(parents=True, exist_ok=True)
        args.rdl_out.write_text(memory_rdl_view(catalog))


if __name__ == "__main__":
    main()
