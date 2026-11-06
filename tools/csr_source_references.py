#!/usr/bin/env python3
"""Configuration-discovered, source-only CSR register references.

These definitions are NOT claimed to be live in the selected chip variant.
Only the existing exact-variant, evidence-qualified register list can make
that assertion. Register offsets come from the existing C ABI and are checked
against source RTL, rather than duplicated in a second hand-maintained map.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]


class SourceCatalogError(ValueError):
    pass


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _path(root, rel):
    if not isinstance(rel, str) or not rel or rel.startswith("/") or "\\" in rel:
        raise SourceCatalogError("invalid CSR source path")
    if ".." in Path(rel).parts:
        raise SourceCatalogError("CSR source escapes repository")
    p = (root / rel).resolve()
    if not p.is_relative_to(root.resolve()) or not p.is_file():
        raise SourceCatalogError("missing CSR source file: " + rel)
    return p


def _registers(header, prefix):
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*_", prefix):
        raise SourceCatalogError("invalid CSR macro prefix")
    pattern = r"^[ \t]*#define[ \t]+" + re.escape(prefix) + (
        r"([A-Z][A-Z0-9_]*)[ \t]+(0x[0-9a-fA-F]+)[uUlL]*(?=\s|$)")
    pairs = [(m.group(1), int(m.group(2), 16))
             for m in re.finditer(pattern, header, re.M)]
    if not pairs or len(set(pairs)) != len(pairs):
        raise SourceCatalogError("missing or duplicate CSR macro definitions")
    if len({n for n, _ in pairs}) != len(pairs) or len({v for _, v in pairs}) != len(pairs):
        raise SourceCatalogError("duplicate CSR names or addresses")
    if any(off < 0 or off % 4 for _, off in pairs):
        raise SourceCatalogError("misaligned CSR source definition")
    return pairs


def _rtl_access(rtl, mode, pairs):
    if mode == "comment_table":
        found = re.findall(
            r"^\s*//\s*0x([0-9a-fA-F]+)\s+([A-Z][A-Z0-9_]*)\s+(RW|RO)\b",
            rtl, re.M)
        mapping = {(name, int(off, 16)): access.lower()
                   for off, name, access in found}
        if len(found) != len(pairs) or set(mapping) != set(pairs):
            raise SourceCatalogError("DMA RTL register comment disagrees with ABI header")
        if "AxiReadOnly(16'hf000)" not in rtl:
            raise SourceCatalogError("DMA RTL read-only status mask changed")
        return mapping
    if mode == "sv_cfg_case":
        read = re.search(r"\bcase\s*\(\s*cfg_addr\s*\)(.*?)\bendcase\b", rtl, re.S)
        write = re.search(r"\belse\s+case\s*\(\s*cfg_addr\s*\)(.*?)\bendcase\b", rtl, re.S)
        if not read or not write:
            raise SourceCatalogError("Ethernet RTL CSR read/write cases missing")
        def offsets(s):
            return [int(x, 16) for x in
                    re.findall(r"\b8'h([0-9a-fA-F]{2})\s*:", s)]
        reads, writes = offsets(read.group(1)), offsets(write.group(1))
        if (len(reads) != len(set(reads)) or len(writes) != len(set(writes))
                or set(reads) != {off for _, off in pairs}
                or not set(writes).issubset(set(reads))):
            raise SourceCatalogError("Ethernet RTL register cases mismatch C header")
        return {(n, off): "rw" if off in writes else "ro" for n, off in pairs}
    raise SourceCatalogError("unrecognized CSR source verification mode")


def _one_bit_macro(header, symbol):
    matches = re.findall(
        r"^\s*#define\s+" + re.escape(symbol) +
        r"\s+(0x[0-9a-fA-F]+[uUlL]*|\(\s*1[uUlL]*\s*<<\s*\d+\s*\))(?=\s|$)",
        header, re.M)
    if len(matches) != 1:
        raise SourceCatalogError("missing/ambiguous CSR field macro " + symbol)
    value = matches[0]
    if value.startswith("("):
        bit = int(re.search(r"<<\s*(\d+)", value).group(1))
        mask = 1 << bit
    else:
        mask = int(re.match(r"0x[0-9a-fA-F]+", value).group(0), 16)
    if mask <= 0 or mask >= (1 << 32) or (mask & (mask - 1)):
        raise SourceCatalogError("unsupported non-single-bit CSR field " + symbol)
    return mask


def _fields(header, declaration, access):
    if isinstance(declaration, str):
        symbols = re.findall(
            r"^\s*#define\s+(" + re.escape(declaration) +
            r"[A-Z][A-Z0-9_]*)\s+", header, re.M)
    elif isinstance(declaration, list) and all(isinstance(v, str) for v in declaration):
        symbols = declaration
    else:
        raise SourceCatalogError("invalid CSR field macro declaration")
    if not symbols or len(symbols) != len(set(symbols)):
        raise SourceCatalogError("missing/duplicate CSR field macro group")
    occupied = 0
    result = []
    for symbol in symbols:
        mask = _one_bit_macro(header, symbol)
        if mask & occupied:
            raise SourceCatalogError("overlapping source CSR field masks")
        occupied |= mask
        bit = mask.bit_length() - 1
        name = (symbol[len(declaration):].lower() if isinstance(declaration, str)
                else symbol.lower())
        result.append({
            "name": name, "lsb": bit, "msb": bit,
            "mask": f"0x{mask:08x}", "access": access,
            "source_symbol": symbol,
            "description": "C ABI bit flag; unknown fields and reset values not inferred",
        })
    return result


def _load(path, root):
    spec = yaml.safe_load(path.read_text())
    if not isinstance(spec, dict) or spec.get("schema_version") != 1:
        raise SourceCatalogError("invalid CSR source plugin " + path.name)
    needed = ("subsystem_type", "aperture_suffix", "header", "rtl",
              "register_macro_prefix", "rtl_register_source")
    if any(not isinstance(spec.get(k), str) or not spec[k] for k in needed):
        raise SourceCatalogError("missing mandatory CSR source plugin attributes")
    header_p, rtl_p = _path(root, spec["header"]), _path(root, spec["rtl"])
    header, rtl = header_p.read_text(), rtl_p.read_text()
    pairs = _registers(header, spec["register_macro_prefix"])
    access = _rtl_access(rtl, spec["rtl_register_source"], pairs)
    groups = spec.get("field_macro_groups", {})
    if not isinstance(groups, dict) or not set(groups).issubset({n for n, _ in pairs}):
        raise SourceCatalogError("field macro group not mapped to a CSR")
    w1c = spec.get("w1c_registers", [])
    one_shot = spec.get("one_shot_registers", [])
    if not isinstance(w1c, list) or not isinstance(one_shot, list):
        raise SourceCatalogError("invalid CSR write semantics")
    if not set(w1c + one_shot).issubset({n for n, _ in pairs}):
        raise SourceCatalogError("write semantics for unknown CSR")
    regs = []
    for name, off in pairs:
        semantics = ("write_one_to_clear" if name in w1c else
                     "one_shot_command" if name in one_shot else None)
        regs.append({
            "name": name.lower(), "offset": f"0x{off:x}",
            "size_bytes": 4, "width_bits": 32, "access": access[(name, off)],
            "reset": None, "fields": _fields(header, groups[name], access[(name, off)])
                if name in groups else [],
            "source_symbol": spec["register_macro_prefix"] + name,
            "description": "Register offset extracted from project C ABI, cross-checked against RTL",
            "write_semantics": semantics,
            "definition_status": "C_ABI_RTL_crosschecked_source_reference_not_build_qualified",
        })
    provenance = {
        "plugin": str(path.relative_to(root)), "plugin_sha256": _digest(path),
        "header": spec["header"], "header_sha256": _digest(header_p),
        "rtl": spec["rtl"], "rtl_sha256": _digest(rtl_p),
    }
    return spec, regs, provenance


def attach_sources(catalog, *, root=ROOT, config_path=None, source_dir=None,
                   gaps_path=None):
    """Attach source-only reference maps and return gap/provenance report.

    This operates on an *exact baseline* catalog, never modifies measured AXI
    traffic or marks source-only registers as active. Validated old-run DDR
    catalogs retain their original SHA and data without any present-day overlay.
    """
    root = Path(root)
    config_path = Path(config_path) if config_path else root / "config/soc.yaml"
    source_dir = Path(source_dir) if source_dir else root / "csr/source-registers"
    gaps_path = Path(gaps_path) if gaps_path else source_dir / "known-gaps.json"
    if _digest(config_path) != catalog.get("config_sha256"):
        raise SourceCatalogError("CSR reference config SHA differs from selected catalog")
    cfg = yaml.safe_load(config_path.read_text())
    subsystems = {s["name"]: s for s in cfg.get("subsystems", [])}
    regions = [r for r in catalog["regions"] if r["plane"] == "config"]
    for r in regions:
        r["source_registers"] = []
        r["source_status"] = "not_available"
        r["source_provenance"] = None
    paths = sorted(source_dir.glob("*.yaml"))
    if not paths:
        raise SourceCatalogError("no CSR source plugins installed")
    plugins = [_load(p, root) for p in paths]
    for spec, registers, provenance in plugins:
        # An existing compatible IP type must expose the expected declared
        # Config-NoC CSR aperture. Silently hiding a new instance is a bug.
        present = {r["name"] for r in regions}
        for subsystem in subsystems.values():
            if subsystem.get("type") != spec["subsystem_type"]:
                continue
            if spec.get("subsystem_ip") and subsystem.get("ip") != spec["subsystem_ip"]:
                continue
            expected = subsystem["name"] + "." + spec["aperture_suffix"]
            if expected not in present:
                raise SourceCatalogError(
                    "configured CSR-capable subsystem lacks aperture: " + expected)
        for r in regions:
            owner, sep, suffix = r["name"].partition(".")
            if not sep or suffix != spec["aperture_suffix"]:
                continue
            s = subsystems.get(owner, {})
            if s.get("type") != spec["subsystem_type"]:
                continue
            if spec.get("subsystem_ip") and s.get("ip") != spec["subsystem_ip"]:
                continue
            if r["source_provenance"] is not None:
                raise SourceCatalogError("ambiguous CSR source plugin for " + r["name"])
            base, length = int(r["base"], 0), int(r["size"], 0)
            if any(int(v["offset"], 0) + v["size_bytes"] > length for v in registers):
                raise SourceCatalogError("CSR source registers exceed " + r["name"])
            r["source_registers"] = [
                {**v, "address": f"0x{base + int(v['offset'], 0):x}"}
                for v in registers]
            r["source_status"] = "source_only_attachment_not_qualified"
            r["source_provenance"] = provenance
    gaps = [r["name"] for r in regions
            if not r.get("registers") and not r["source_registers"]]
    known = json.loads(gaps_path.read_text())
    if known.get("schema_version") != 1 or not isinstance(known.get("known_gaps"), dict):
        raise SourceCatalogError("invalid CSR known-gap registry")
    for r in regions:
        r["source_gap_reason"] = known["known_gaps"].get(r["name"]) if r["name"] in gaps else None
    unacknowledged = sorted(set(gaps) - set(known["known_gaps"]))
    if unacknowledged:
        raise SourceCatalogError(
            "new CSR subsystem(s) without source metadata or documented exception: " +
            ", ".join(unacknowledged))
    return {
        "schema_version": 1, "variant": catalog["variant"],
        "sources": [p for _, _, p in plugins],
        "instances": [{
            "instance": r["name"], "selected_variant_registers": len(r.get("registers", [])),
            "source_only_registers": len(r["source_registers"]),
            "status": ("selected_variant_definition" if r.get("registers")
                       else r["source_status"]),
            "provenance": r["source_provenance"],
        } for r in regions],
        "gaps": [{"instance": name, "reason": known["known_gaps"][name]}
                 for name in gaps],
        "missing_count": len(gaps),
        "unacknowledged": unacknowledged,
    }
