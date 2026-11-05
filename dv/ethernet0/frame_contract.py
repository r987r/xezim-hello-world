"""Pure Ethernet/IPv4/UDP golden reference for the real MAC/PHY-VIP agent.

Wire FCS is Ethernet CRC32 little-endian. This module is NOT a MAC, PHY,
streaming DMA or RTL packet classifier and is never an active bus driver.
"""
from dataclasses import dataclass
from ipaddress import IPv4Address
from struct import pack, unpack
from zlib import crc32


@dataclass(frozen=True)
class Packet:
    src_mac: bytes
    dst_mac: bytes
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    payload: bytes

    def __post_init__(self):
        if len(self.src_mac) != 6 or len(self.dst_mac) != 6:
            raise ValueError("MAC address must have six bytes")
        if any(not 0 <= p <= 65535 for p in (self.src_port, self.dst_port)):
            raise ValueError("invalid UDP port")
        if not 0 <= len(self.payload) <= 65507:
            raise ValueError("UDP payload too large")


def checksum(buf: bytes) -> int:
    if len(buf) & 1:
        buf += b"\x00"
    words = unpack("!" + "H" * (len(buf) // 2), buf)
    acc = sum(words)
    while acc >> 16:
        acc = (acc & 0xffff) + (acc >> 16)
    return (~acc) & 0xffff


def encode(packet: Packet) -> bytes:
    src, dst = IPv4Address(packet.src_ip).packed, IPv4Address(packet.dst_ip).packed
    udp_size = len(packet.payload) + 8
    udp = pack("!HHHH", packet.src_port, packet.dst_port, udp_size, 0) + packet.payload
    total = 20 + len(udp)
    ipv4 = pack("!BBHHHBBH4s4s", 0x45, 0, total, 0, 0, 64, 17, 0, src, dst)
    ipv4 = ipv4[:10] + pack("!H", checksum(ipv4)) + ipv4[12:]
    ethernet = packet.dst_mac + packet.src_mac + b"\x08\x00" + ipv4 + udp
    return ethernet + pack("<I", crc32(ethernet) & 0xffffffff)


def decode(frame: bytes) -> tuple[int, bytes]:
    if len(frame) < 14 + 20 + 8 + 4:
        raise ValueError("truncated Ethernet/UDP frame")
    data, fcs = frame[:-4], frame[-4:]
    if pack("<I", crc32(data) & 0xffffffff) != fcs:
        raise ValueError("Ethernet FCS mismatch")
    if data[12:14] != b"\x08\x00":
        raise ValueError("not IPv4")
    ip = data[14:]
    if (ip[0] >> 4) != 4 or (ip[0] & 15) != 5 or ip[9] != 17:
        raise ValueError("unsupported IPv4 header / protocol")
    ip_size = int.from_bytes(ip[2:4], "big")
    if ip_size != len(ip) or checksum(ip[:20]) != 0:
        raise ValueError("bad IPv4 length/checksum")
    udp = ip[20:]
    if len(udp) < 8 or int.from_bytes(udp[4:6], "big") != len(udp):
        raise ValueError("bad UDP length")
    return int.from_bytes(udp[2:4], "big"), udp[8:]


def destination_class(dst_port: int, fast_ports: frozenset[int]) -> str:
    if not 0 <= dst_port <= 65535:
        raise ValueError("invalid UDP port")
    return "pcie_fast_candidate" if dst_port in fast_ports else "global_memory"
