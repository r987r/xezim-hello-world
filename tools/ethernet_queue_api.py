"""Shared host-side queue programming oracle for Ethernet0 V1.

All register offsets are read from the single C ABI header, never redefined.
This file DOES NOT emulate hardware DMA, MAC traffic, NoCs or completion writes.
"""
from dataclasses import dataclass
from pathlib import Path
import re
import struct

HEADER = Path(__file__).resolve().parents[1] / "sw" / "ethernet" / "eth_queue_abi.h"
DESC = struct.Struct("<QIIIIQ")


def register_offsets(path=HEADER):
    expressions = re.findall(r"^#define\s+(ETHQ_REG_\w+)\s+0x([0-9a-fA-F]+)u\b",
                             Path(path).read_text(), re.MULTILINE)
    result = {name.removeprefix("ETHQ_REG_"): int(value, 16)
              for name, value in expressions}
    if len(result) < 25 or len(result) != len(expressions):
        raise ValueError("malformed or duplicate queue register ABI")
    if len(set(result.values())) != len(result):
        raise ValueError("two queue registers share a CSR address")
    return result


REG = register_offsets()


@dataclass(frozen=True)
class RxDescriptor:
    dst_addr: int
    capacity: int
    cookie: int
    flags: int = 0
    region_id: int = 0

    def __post_init__(self):
        if not 0 < self.capacity < (1 << 32) or self.dst_addr < 0 or \
           self.dst_addr + self.capacity > (1 << 64) or \
           any(not 0 <= n < (1 << 32)
               for n in (self.cookie, self.flags, self.region_id)):
            raise ValueError("RX descriptor physical range or metadata invalid")

    def encode(self):
        return DESC.pack(self.dst_addr, self.capacity, self.cookie,
                         self.flags, self.region_id, 0)


@dataclass(frozen=True)
class TxDescriptor:
    src_addr: int
    length: int
    cookie: int
    flags: int = 0

    def __post_init__(self):
        if not 0 < self.length < (1 << 32) or self.src_addr < 0 or \
           self.src_addr + self.length > (1 << 64) or \
           not 0 <= self.cookie < (1 << 32) or \
           not 0 <= self.flags < (1 << 32):
            raise ValueError("TX descriptor physical range or metadata invalid")

    def encode(self):
        return DESC.pack(self.src_addr, self.length, self.cookie,
                         self.flags, 0, 0)


@dataclass(frozen=True)
class Policy:
    ethertype: int
    ethertype_mask: int
    udp_port: int
    udp_mask: int
    require_udp: bool
    queue: int
    drop: bool = False

    def __post_init__(self):
        if any(not 0 <= n < (1 << 16) for n in
               (self.ethertype, self.ethertype_mask, self.udp_port, self.udp_mask)):
            raise ValueError("invalid 16-bit policy field")
        if not 0 <= self.queue < 256:
            raise ValueError("invalid RX queue index")
        if not self.require_udp and self.udp_mask:
            raise ValueError("UDP port mask only legal with require_udp")

    def matches(self, ethertype, is_udp, udp_dst_port):
        return ((ethertype ^ self.ethertype) & self.ethertype_mask) == 0 and \
               (not self.require_udp or
                (is_udp and
                 ((udp_dst_port ^ self.udp_port) & self.udp_mask) == 0))


def possible_overlap(a: Policy, b: Policy) -> bool:
    if ((a.ethertype ^ b.ethertype) &
        a.ethertype_mask & b.ethertype_mask):
        return False
    if a.require_udp and b.require_udp:
        return ((a.udp_port ^ b.udp_port) & a.udp_mask & b.udp_mask) == 0
    return True


def select_policy(policies, *, ethertype, is_udp, udp_dst_port):
    hits = [idx for idx, rule in enumerate(policies)
            if rule is not None and
            rule.matches(ethertype, is_udp, udp_dst_port)]
    if len(hits) > 1:
        raise ValueError("POLICY_MULTI_MATCH")
    return hits[0] if hits else None


class QueueProgrammer:
    """MMIO-independent frontdoor API using read32/write32 callbacks."""

    def __init__(self, read32, write32):
        self.read32, self.write32 = read32, write32
        if read32(REG["MAGIC"]) != 0x45544851 or \
           read32(REG["VERSION"]) != 0x00010000:
            raise ValueError("Ethernet queue CSR ABI mismatch")
        caps = read32(REG["CAPS"])
        self.rx_queues, self.tx_queues = caps & 255, (caps >> 8) & 255
        self.depth = 1 << ((caps >> 16) & 255)
        self.policies = (caps >> 24) & 255
        if not self.rx_queues or not self.tx_queues or \
           not 1 <= self.depth <= 256 or not 1 <= self.policies <= 16:
            raise ValueError("invalid queue hardware capabilities")

    def config_ring(self, q, *, rx, desc_addr, cq_addr):
        if q >= (self.rx_queues if rx else self.tx_queues) or q < 0 or \
           min(desc_addr, cq_addr) <= 0 or \
           (desc_addr | cq_addr) & 31 or \
           max(desc_addr, cq_addr) >= (1 << 64):
            raise ValueError("invalid queue ring address")
        if self.read32(REG["ENABLE"]):
            raise ValueError("cannot modify ring bases while enabled")
        self.write32(REG["QUEUE_SELECT"], q)
        base = "RX" if rx else "TX"
        for addr, lo, hi in ((desc_addr, f"{base}_DESC_LO", f"{base}_DESC_HI"),
                             (cq_addr, f"{base}_CQ_LO", f"{base}_CQ_HI")):
            self.write32(REG[lo], addr & 0xffffffff)
            self.write32(REG[hi], addr >> 32)

    def config_policy(self, index, policy: Policy, existing=()):
        if index < 0 or index >= self.policies or policy.queue >= self.rx_queues:
            raise ValueError("invalid queue or policy index")
        if self.read32(REG["ENABLE"]):
            raise ValueError("disable RX/TX before policy programming")
        for j, item in enumerate(existing):
            if j != index and item is not None and possible_overlap(item, policy):
                raise ValueError("overlapping rules must not be committed")
        self.write32(REG["POLICY_SELECT"], index)
        for key, val in (
            ("MATCH_ETHERTYPE", policy.ethertype),
            ("MASK_ETHERTYPE", policy.ethertype_mask),
            ("MATCH_UDP_PORT", policy.udp_port),
            ("MASK_UDP_PORT", policy.udp_mask),
            ("POLICY_CONTROL", 1 | (2 if policy.require_udp else 0) |
             (4 if policy.drop else 0) | (policy.queue << 8)),
        ):
            self.write32(REG[key], val)

    def ring_doorbell(self, *, rx, new_producer):
        old = self.read32(REG["RX_PRODUCER" if rx else "TX_PRODUCER"])
        cons = self.read32(REG["RX_CONSUMER" if rx else "TX_CONSUMER"])
        if not 0 <= new_producer < (1 << 32) or \
           ((new_producer - old) & 0xffffffff) > self.depth or \
           ((new_producer - cons) & 0xffffffff) > self.depth:
            raise ValueError("descriptor ring overflow/stale producer")
        # memory barrier and cache maintenance must be supplied by the
        # BFM/CPU backend before calling this. This class is not an allocator.
        self.write32(REG["RX_PRODUCER" if rx else "TX_PRODUCER"], new_producer)
