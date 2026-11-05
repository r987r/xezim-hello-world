"""Fail-closed interface contract for future config-driven SoC subsystem emitters.

This deliberately does not alter soc.yaml or generated RTL until one owner
integrates actual PCIe/Ethernet adapters and their pinned source closure.
"""
from dataclasses import dataclass
import re

IDENT = re.compile(r"^[a-z][a-z0-9_]*$")
PROTOCOLS = frozenset(("axi4", "axi4_lite", "axis", "gmii", "pcie_tlp", "dfi", "clock", "reset"))
DIRECTIONS = frozenset(("input", "output"))
ROLES = frozenset(("initiator", "target", "signal"))


@dataclass(frozen=True)
class Port:
    name: str
    protocol: str
    direction: str
    role: str
    width: int
    clock: str

    def __post_init__(self):
        if not IDENT.fullmatch(self.name):
            raise ValueError("bad subsystem port name")
        if self.protocol not in PROTOCOLS or self.direction not in DIRECTIONS or self.role not in ROLES:
            raise ValueError("bad protocol/direction/role")
        if type(self.width) is not int or self.width < 1 or self.width > 1024:
            raise ValueError("bad port width")
        if not IDENT.fullmatch(self.clock):
            raise ValueError("bad clock reference")
        if self.protocol in ("clock", "reset") and (self.width != 1 or self.role != "signal"):
            raise ValueError("clock/reset must be a one-bit signal")


@dataclass(frozen=True)
class SubsystemContract:
    kind: str
    clock_domains: tuple[str, ...]
    ports: tuple[Port, ...]
    emitter: str

    def __post_init__(self):
        if not IDENT.fullmatch(self.kind) or not IDENT.fullmatch(self.emitter):
            raise ValueError("bad kind/emitter")
        if not self.clock_domains or len(set(self.clock_domains)) != len(self.clock_domains):
            raise ValueError("invalid clocks")
        if any(not IDENT.fullmatch(x) for x in self.clock_domains):
            raise ValueError("bad clock domain")
        if not self.ports or len({p.name for p in self.ports}) != len(self.ports):
            raise ValueError("missing/duplicate ports")
        if any(p.clock not in self.clock_domains for p in self.ports):
            raise ValueError("port clock not declared")


class Registry:
    def __init__(self):
        self._kinds = {}

    def register(self, contract: SubsystemContract):
        if contract.kind in self._kinds:
            raise ValueError("duplicate subsystem type registration")
        self._kinds[contract.kind] = contract

    def resolve(self, kind: str) -> SubsystemContract:
        try:
            return self._kinds[kind]
        except KeyError as exc:
            raise ValueError(f"subsystem type {kind!r} has no emitter") from exc

    def check_link(self, source_kind: str, source_port: str,
                   dest_kind: str, dest_port: str, *, cdc: bool = False):
        src = next((p for p in self.resolve(source_kind).ports if p.name == source_port), None)
        dst = next((p for p in self.resolve(dest_kind).ports if p.name == dest_port), None)
        if src is None or dst is None:
            raise ValueError("unknown required port")
        if src.direction != "output" or dst.direction != "input" or src.protocol != dst.protocol:
            raise ValueError("protocol or direction mismatch")
        if src.width != dst.width:
            raise ValueError("bus width mismatch")
        if src.clock != dst.clock and not cdc:
            raise ValueError("unresolved clock-domain crossing")
        if src.protocol in ("axi4", "axi4_lite") and src.role != "initiator":
            raise ValueError("AXI source must be initiator")
        if src.protocol in ("axi4", "axi4_lite") and dst.role != "target":
            raise ValueError("AXI sink must be target")
        return {"protocol": src.protocol, "bits": src.width,
                "cdc_required": src.clock != dst.clock, "evidence": "declarative_only"}
