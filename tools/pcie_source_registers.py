#!/usr/bin/env python3
"""Fail-closed PCIe CSR source references for the address-map catalog.

The outbound requester comes from its C ABI plus the actual RTL read/write
case statements. The endpoint DBI definitions come from the authored SystemRDL
and its independently pinned generator contract. Neither source proves that the
corresponding block was elaborated, connected or exercised in the selected SoC.
Host-originated Type-0 config TLP offsets are NOT CPU Config-NoC MMIO.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

from pcie_csrgen import EXPECTED

ROOT = Path(__file__).resolve().parents[1]
HEADER = "sw/pcie/pcie_requester.h"
RTL = "rtl/adapters/pcie_requester_axi_regs.sv"
RDL = "csr/rdl/pcie_endpoint_prelink_ctrl.rdl"


class PcieSourceError(ValueError):
    pass


def _read(root, path):
    file = root / path
    if not file.is_file():
        raise PcieSourceError(f"missing PCIe CSR source: {path}")
    return file.read_text(), hashlib.sha256(file.read_bytes()).hexdigest()


def source_registers(root=ROOT):
    """Parse source-owned register offsets/fields and reject ABI/RTL drift."""
    root = Path(root)
    header, header_sha = _read(root, HEADER)
    rtl, rtl_sha = _read(root, RTL)
    rdl, rdl_sha = _read(root, RDL)
    match = re.search(r"\benum\s*\{(.*?)\}\s*;", header, re.S)
    if not match:
        raise PcieSourceError("missing PCIe requester C ABI enum")
    pairs = re.findall(r"\bSOC_PCIE_([A-Z][A-Z0-9_]*)\s*=\s*(0x[0-9a-fA-F]+)\b",
                       match.group(1))
    offsets = [(name, int(offset, 16)) for name, offset in pairs]
    if (len(offsets) != 15 or len(set(name for name, _ in offsets)) != len(offsets)
            or len(set(off for _, off in offsets)) != len(offsets)
            or any(off >= 0x40 or off % 4 for _, off in offsets)):
        raise PcieSourceError("unexpected PCIe requester register ABI")
    read_cases = re.findall(r"\bcase\s*\(\s*rd_offset\s*\)(.*?)\bendcase\b",
                            rtl, re.S)
    write_cases = re.findall(r"\bcase\s*\(\s*wr_offset\s*\)(.*?)\bendcase\b",
                             rtl, re.S)
    if len(read_cases) != 1 or not write_cases:
        raise PcieSourceError("PCIe requester RTL read/write decode missing")
    def case_offsets(text):
        return {int(v, 16) for v in
                re.findall(r"\b32'h([0-9a-fA-F]+)\s*:", text)}
    reads = case_offsets(read_cases[0])
    # The last wr_offset case is the accepted AXI-Lite write decoder;
    # earlier uses are policy validation only.
    writes = case_offsets(write_cases[-1])
    expected_reads = {off for _, off in offsets}
    expected_writes = {off for name, off in offsets
                       if not (name.endswith("_STATUS") or name == "VERSION")}
    if reads != expected_reads or writes != expected_writes:
        raise PcieSourceError("PCIe requester RTL decode disagrees with C ABI")
    status_flags = re.findall(
        r"#define\s+SOC_PCIE_STATUS_([A-Z]+)\s+([124])u\b", header)
    if {n: int(v) for n, v in status_flags} != {
            "DONE": 1, "BUSY": 2, "ERROR": 4}:
        raise PcieSourceError("PCIe status bit ABI changed")
    requester = []
    for name, offset in offsets:
        writable = offset in writes
        fields = []
        if name.endswith("_STATUS"):
            fields = [{
                "name": field.lower(), "lsb": mask.bit_length()-1,
                "msb": mask.bit_length()-1, "mask": f"0x{mask:08x}",
                "access": "r", "reset": None,
                "description": "Status bit defined in PCIe requester C ABI",
                "source_symbol": "SOC_PCIE_STATUS_" + field,
            } for field, mask in (("DONE", 1), ("BUSY", 2), ("ERROR", 4))]
        requester.append({
            "name": name.lower(), "offset": hex(offset), "size_bytes": 4,
            "width_bits": 32, "access": "rw" if writable else "r",
            "reset": None, "fields": fields,
            "source_symbol": "SOC_PCIE_" + name,
            "description": "Outbound PCIe requester: C enum and RTL AXI-Lite decode agree. "
                           "Selected SoC connectivity is not certified by this source map.",
            "definition_status": "PCIe_source_reference_not_build_qualified",
        })
    # Exact SystemRDL field ranges, masks and access modes. All source-defined
    # registers must match the separately checked PeakRDL ABI contract.
    register_matches = re.findall(
        r"\breg\s*\{(.*?)\}\s*([a-z][a-z0-9_]*)\s*@\s*(0x[0-9a-fA-F]+)\s*;",
        rdl, re.S)
    parsed = []
    for body, name, raw_offset in register_matches:
        fields = []
        for declaration, field_name, msb, lsb in re.findall(
                r"\bfield\s*\{(.*?)\}\s*([a-z][a-z0-9_]*)\s*\[(\d+):(\d+)\]\s*;",
                body, re.S):
            access = re.findall(r"\bsw\s*=\s*(rw|r|w)\s*;", declaration)
            reset = re.findall(r"\breset\s*=\s*(\d+)\s*;", declaration)
            hi, lo = int(msb), int(lsb)
            if len(access) != 1 or len(reset) != 1 or reset[0] != "0" or lo > hi or hi > 31:
                raise PcieSourceError(f"invalid PCIe DBI RDL field: {name}.{field_name}")
            fields.append({
                "name": field_name, "lsb": lo, "msb": hi,
                "mask": f"0x{((1 << (hi-lo+1))-1) << lo:08x}",
                "access": access[0], "reset": "0x0",
                "description": "Authoritative PCIe endpoint SystemRDL field",
                "backdoor_policy": "frontdoor_only",
            })
        parsed.append((name, int(raw_offset, 16),
                       {f["name"]: (f["lsb"], f["msb"], f["access"]) for f in fields},
                       fields))
    if [(name, offset, specs) for name, offset, specs, _ in parsed] != list(EXPECTED):
        raise PcieSourceError("PCIe endpoint RDL differs from pinned generated ABI")
    if max(offset for _, offset, _, _ in parsed) + 4 > 0x10000:
        raise PcieSourceError("PCIe DBI registers exceed configuration aperture")
    endpoint = []
    for name, offset, _specs, fields in parsed:
        accesses = {field["access"] for field in fields}
        endpoint.append({
            "name": name, "offset": hex(offset), "size_bytes": 4,
            "width_bits": 32, "access": accesses.pop() if len(accesses) == 1 else "mixed",
            "reset": None, "fields": fields,
            "description": "CPU0 device-side endpoint DBI source, NOT host Type-0 config. "
                           "Generated RTL is not proven attached to CPU0 Config NoC.",
            "definition_status": "PCIe_source_reference_not_build_qualified",
        })
    if {int(r["offset"], 16) for r in requester} & {
            int(r["offset"], 16) for r in endpoint}:
        raise PcieSourceError("PCIe requester and endpoint DBI register collision")
    provenance = {
        "plugin": "tools/pcie_source_registers.py",
        "header": HEADER, "header_sha256": header_sha,
        "rtl": RTL, "rtl_sha256": rtl_sha,
        "rdl": RDL, "rdl_sha256": rdl_sha,
        "host_configuration_space": "Type-0 BAR0 offset 0x10; COMMAND offset 0x04",
        "active_variant_qualified": False,
    }
    return requester + endpoint, provenance
