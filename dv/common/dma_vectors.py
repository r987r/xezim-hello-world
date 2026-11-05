"""Fast DMA-only SRAM vectors and expected AXI readback, reusable by cocotb.

Only DMA-specific simulation scopes may preload these vectors. Cold boot must
continue to copy firmware from flash into uninitialized SRAM via real CPUs.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from tools.memory_service import Pattern
import json
from pathlib import Path
import struct
from tools.sram_layout import (build_sram_layout, DESC_START, DESC_BYTES as DESC_POOL_BYTES, PAYLOAD_START)
from tools.memory_plan import configured_regions

DESC = struct.Struct("<IIQQQ")  # length, flags, next, src, dst
DESC_BYTES = DESC.size
DESC_END = (1 << 64) - 1
FLAGS_COPY = (1 << 1) | (1 << 3)
FLAGS_IRQ = 1
DESC_OFFSET = DESC_START
PAYLOAD_OFFSET = PAYLOAD_START


@dataclass(frozen=True)
class DmaVectorCase:
    manifest: dict
    source_sram: bytes

    def write(self, output: Path) -> None:
        output.mkdir(parents=True, exist_ok=True)
        (output / "case.json").write_text(
            json.dumps(self.manifest, indent=2, sort_keys=True) + "\n")
        if len(self.source_sram) % 8:
            raise ValueError("SRAM must contain complete 64-bit words")
        (output / "source_sram.hex").write_text("".join(
            f'{int.from_bytes(self.source_sram[i:i+8], "little"):016x}\n'
            for i in range(0, len(self.source_sram), 8)))


def _region(cfg, name):
    matches = [r for r in cfg["address_map"]["data"] if r["name"] == name]
    if len(matches) != 1:
        raise ValueError(f"unknown/ambiguous data region: {name}")
    return int(matches[0]["base"], 0), int(matches[0]["size"], 0)


def build_dma_vector(cfg, *, subsystem="compute0", destination="memory0.ddr0",
                     count=4, length=64, irq_last=True, profile='boot_live'):
    """Create a disjoint chain of DMA copies, SRAM preload and golden manifest."""
    if type(count) is not int or type(length) is not int or count <= 0 or length <= 0:
        raise ValueError("count and length must be positive integers")
    if length > 0xffffffff or count > DESC_POOL_BYTES // DESC_BYTES:
        raise ValueError("transfer length/count exceeds descriptor pool")
    computes = [s["name"] for s in cfg["subsystems"] if s["type"] == "compute"]
    if subsystem not in computes:
        raise ValueError("unknown compute subsystem")
    layout = build_sram_layout(cfg, subsystem, profile=profile)
    sram_base, sram_bytes = layout.sram_base, layout.sram_size
    if count*length > layout.payload.size:
        raise ValueError("payload exceeds source SRAM")
    dst_base, window_size = _region(cfg, destination)
    if destination in [f"{name}.sram" for name in computes]:
        limit = sram_bytes
        dst_offset = 0x3000 if destination == f"{subsystem}.sram" else PAYLOAD_OFFSET
    elif destination in [t["name"] for t in cfg["memory_targets"]]:
        # Share the exact Python/C modeled DDR/HBM allocation contract.
        # The first 0x100 bytes are reserved for unrelated memory tests.
        target_region = configured_regions(cfg, profile=profile)[destination]
        dst_offset = target_region.base - dst_base
        limit = dst_offset + target_region.capacity
    else:
        raise ValueError("destination is not a modeled target")
    if dst_offset + count*length > min(window_size, limit):
        raise ValueError("destination exceeds modeled capacity")
    image = bytearray(sram_bytes)
    head = layout.descriptors.start
    source = layout.payload.start
    desc_offset = head - sram_base
    payload_offset = source - sram_base
    copies = []
    for i in range(count):
        src = source + i*length
        dst = dst_base + dst_offset + i*length
        nxt = head + (i+1)*DESC_BYTES if i < count-1 else DESC_END
        flags = FLAGS_COPY | (FLAGS_IRQ if irq_last and i == count-1 else 0)
        image[desc_offset+i*DESC_BYTES:desc_offset+(i+1)*DESC_BYTES] = DESC.pack(
            length, flags, nxt, src, dst)
        payload = Pattern("address_xor", seed=0x35 + 29 * i).chunk(
            source + i * length, length)
        image[payload_offset+i*length:payload_offset+(i+1)*length] = payload
        copies.append({
            "descriptor": head + i*DESC_BYTES, "src": src, "dst": dst,
            "length": length, "flags": flags, "next": nxt,
            "expected_hex": payload.hex(),
            "expected_sha256": hashlib.sha256(payload).hexdigest()
        })
    return DmaVectorCase({
        "schema_version": 1, "kind": "dma_only_not_cold_boot",
        "subsystem": subsystem, "destination": destination,
        "source_sram_base": sram_base, "source_sram_bytes": sram_bytes,
        "descriptor_head": head, "descriptor_count": count,
        "descriptor_size": DESC_BYTES, "descriptor_pool_start": head,
        "descriptor_pool_bytes": DESC_POOL_BYTES,
        "source_pool_start": source,
        "source_pool_bytes": layout.payload.size,
        "sram_layout": layout.as_dict(),
        "allocation_profile": profile,
        "destination_base": dst_base+dst_offset,
        "destination_modeled_bytes": limit,
        "irq_last": irq_last, "copies": copies,
        "note": "Shared scenario for isolated RTL / full-NoC BFM DMA. CPU cold boot does not preload SRAM."
    }, bytes(image))


async def verify_dma_readback(master, manifest):
    """Read actual destinations using upstream cocotbext-axi AxiMaster."""
    for copy in manifest["copies"]:
        result = await master.read(copy["dst"], copy["length"])
        if result.resp != 0:
            raise AssertionError(f'DMA AXI error {result.resp} at {copy["dst"]:#x}')
        if bytes(result.data) != bytes.fromhex(copy["expected_hex"]):
            raise AssertionError(f'DMA mismatch descriptor {copy["descriptor"]:#x}')
