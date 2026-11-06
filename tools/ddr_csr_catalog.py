#!/usr/bin/env python3
"""Import pinned LiteDRAM/LiteX generated CSR addresses for one real DDR variant.

The upstream csr.json owns the register byte addresses, sizes and RO/RW flags.
The SoC variant's memory0.ctrl aperture and the DDR transport contract own the
physical relocation. No fields, reset values, RTL or behavioral side effects
are invented; this only describes addressable controller register *words*.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


class DdrCsrError(ValueError):
    pass


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_native(native, transport, variant_config, *, csr_source, config_source):
    rows = native.get("csr_registers")
    if not isinstance(rows, dict) or not rows:
        raise DdrCsrError("missing native LiteDRAM CSR register definitions")
    if transport.get("target_csr") != "memory0.ctrl" or transport.get("controller") != "memory0.ddr0":
        raise DdrCsrError("foreign controller CSR transport contract")
    if transport.get("config_plane") != "global_config -> memory0.local_config":
        raise DdrCsrError("controller not on the independent Config NoC")
    import yaml
    cfg = yaml.safe_load(Path(variant_config).read_text())
    apertures = [r for r in cfg["address_map"]["config"] if r["name"] == "memory0.ctrl"]
    if len(apertures) != 1:
        raise DdrCsrError("DDR controller aperture not unique")
    region = apertures[0]
    base, size = int(region["base"], 0), int(region["size"], 0)
    if (base != 0x40030000 or size != 0x4000
            or transport["config_base"] != base
            or transport["window_bytes"] != size
            or transport["configured_window_bytes"] != size):
        raise DdrCsrError("DDR Config-NoC aperture does not match generated variant")
    wb_base = transport["generated_wb_base"]
    if type(wb_base) is not int or wb_base < 0 or wb_base % size:
        raise DdrCsrError("invalid generated LiteDRAM Wishbone window")
    mapped, excluded, occupied = [], [], set()
    for name, reg in sorted(rows.items()):
        if not isinstance(name, str) or not name or not isinstance(reg, dict):
            raise DdrCsrError("malformed native CSR entry")
        addr, count, access = reg.get("addr"), reg.get("size"), reg.get("type")
        if type(addr) is not int or addr < 0 or addr % 4 or type(count) is not int or count <= 0:
            raise DdrCsrError(f"{name}: invalid native CSR address/word size")
        if access not in ("ro", "rw"):
            raise DdrCsrError(f"{name}: unsupported native CSR access")
        if (addr < wb_base or addr + count * 4 > wb_base + size):
            excluded.append(name)
            continue
        for word in range(count):
            word_addr = addr + word * 4
            if word_addr in occupied:
                raise DdrCsrError(f"{name}: overlapping native LiteDRAM register word")
            occupied.add(word_addr)
            offset = word_addr - wb_base
            mapped.append({
                "name": name if count == 1 else f"{name}[{word}]",
                "native_name": name,
                "native_word_index": word,
                "offset": f"0x{offset:x}", "size_bytes": 4, "width_bits": 32,
                "access": "r" if access == "ro" else "rw",
                "reset": None, "fields": [],
                "source": "pinned LiteDRAM/LiteX generated csr.json",
                "description": "Native 32-bit LiteDRAM/LiteX CSR word; field and reset semantics not exported",
                "wishbone_byte_address": f"0x{word_addr:x}",
            })
    expected = {a["csr"] for a in transport.get("actions", []) if a.get("csr")}
    actual = {r["native_name"] for r in mapped}
    if not expected or not expected <= actual:
        raise DdrCsrError(f"required initialized DDR CSRs missing from physical window: {sorted(expected - actual)}")
    if not mapped:
        raise DdrCsrError("no addressable native DDR controller CSRs")
    return {
        "schema_version": 1, "variant": "ddr_real",
        "config_sha256": digest(variant_config),
        "native_csr_sha256": digest(csr_source),
        "transport_sha256": digest(config_source),
        "generator": {"name": "LiteDRAM/LiteX", "rtl_replaced": False},
        "register_count": len(mapped),
        "native_unmapped_registers": excluded,
        "instances": [{
            "name": "memory0.ctrl", "base": hex(base), "size": hex(size),
            "status": "implemented", "source": "LiteDRAM native csr.json",
            "registers": sorted(mapped, key=lambda r: int(r["offset"], 0)),
        }],
    }


def generate(config_path, csr_path, transport_path, output):
    import yaml
    config_path, csr_path, transport_path, output = map(
        Path, (config_path, csr_path, transport_path, output))
    native = json.loads(csr_path.read_text())
    transport = json.loads(transport_path.read_text())
    catalog = parse_native(native, transport, config_path,
                           csr_source=csr_path, config_source=transport_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n")
    return catalog


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--variant-config", type=Path, required=True)
    p.add_argument("--native-csr", type=Path, required=True)
    p.add_argument("--transport", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    generate(a.variant_config, a.native_csr, a.transport, a.out)


if __name__ == "__main__":
    main()
