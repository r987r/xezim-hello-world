"""Deterministic DDR4 AXI stress vectors for the *existing* standalone LiteDRAM DUT.

Pure stimulus planning; never claims to simulate the controller. Agents drive
these cases through functional_tb and the existing passive AXI/DFI monitors.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Burst:
    address: int
    beats: int
    id: int
    strobe: int
    pattern: int
    kind: str


def pattern_byte(address: int, seed: int) -> int:
    """Same value for a byte regardless of burst fragmentation."""
    return ((address * 131) ^ (address >> 11) ^ seed) & 0xff


def lanes_per_beat(data_bits: int) -> int:
    if data_bits not in (32, 64, 128, 256, 512) or data_bits % 8:
        raise ValueError("unsupported integral AXI beat width")
    return data_bits // 8


def build_matrix(*, aperture_bytes: int, data_bits: int = 64,
                 id_bits: int = 4, seed: int = 1) -> tuple[Burst, ...]:
    """Cover legal low/high addresses, byte lanes, IDs, and read/write reuse.

    Address ranges are bounded by the *modeled* capacity, not a 1GiB
    architectural map. No wrap/alias is hidden in this generator.
    """
    lanes = lanes_per_beat(data_bits)
    if not 1 <= id_bits <= 16:
        raise ValueError("invalid AXI ID width")
    if aperture_bytes < lanes * 64 or aperture_bytes % lanes:
        raise ValueError("aperture must contain at least 64 aligned beats")
    ids = (0, (1 << id_bits) - 1)
    sites = (0, lanes * 2, (aperture_bytes // 2 // lanes) * lanes,
             aperture_bytes - lanes * 16)
    lengths = (1, 4, 8, 16)
    result = []
    for idx, (address, beats) in enumerate(zip(sites, lengths)):
        if address + lanes * beats > aperture_bytes:
            raise ValueError("burst exceeds physical model aperture")
        strobes = (1, (1 << lanes) - 1, 1 << (lanes - 1),
                   sum(1 << i for i in range(0, lanes, 2)))
        for kind in ("write", "read"):
            result.append(Burst(address, beats, ids[idx % len(ids)],
                                strobes[idx], seed ^ (idx * 0x9e37), kind))
    # Explicit adjacent bank/row-boundary candidates are deliberately NOT
    # guessed: map these through generated sim_geometry.yml before exercising.
    return tuple(result)


def expected_write(previous: bytes, burst: Burst, beat_bytes: int) -> bytes:
    if burst.kind != "write" or burst.beats * beat_bytes != len(previous):
        raise ValueError("invalid write image")
    if burst.strobe >= (1 << beat_bytes) or burst.strobe < 0:
        raise ValueError("invalid strobe")
    out = bytearray(previous)
    for i in range(burst.beats):
        for lane in range(beat_bytes):
            if (burst.strobe >> lane) & 1:
                off = i * beat_bytes + lane
                out[off] = pattern_byte(burst.address + off, burst.pattern)
    return bytes(out)
