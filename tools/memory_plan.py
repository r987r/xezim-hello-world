"""Virtual test-time allocation plans, using the same *physical ranges* as C.

Python reserves EXPECTED locations and lifetimes; C owns actual allocations.
This layer never writes, seeds or backdoor-preloads a memory model. Independent
AXI monitors and CPU-visible status must prove actual traffic and completion.

All target capacities are the *modeled* backing extents, not huge SoC
architectural apertures. Valid ranges are driven from config/soc.yaml.
"""
from dataclasses import dataclass, field
from tools.sram_layout import build_sram_layout

U64 = (1 << 64) - 1


def number(value):
    return int(value, 0) if isinstance(value, str) else value


@dataclass(frozen=True)
class VirtualAllocation:
    region: str
    phys: int
    size: int
    token: int
    previous_used: int
    previous_token: int
    generation: int
    owner: str
    phase: str

    def as_dict(self):
        return vars(self).copy()


@dataclass
class VirtualRegion:
    name: str
    kind: str
    base: int
    capacity: int
    cpu_visible: bool
    used: int = 0
    generation: int = 1
    next_token: int = 1
    top_token: int = 0
    allocations: list = field(default_factory=list)

    def __post_init__(self):
        if self.kind not in ("sram", "ddr", "hbm"):
            raise ValueError("unsupported physical memory kind")
        if self.base < 0 or self.capacity <= 0 or self.base + self.capacity > U64:
            raise ValueError("invalid physical model range")
        if self.kind != "sram" and self.cpu_visible:
            raise ValueError("32-bit CPUs cannot dereference DDR/HBM")

    def allocate(self, size: int, alignment: int, *, owner: str, phase: str):
        if not owner or phase not in ("init", "run", "check", "dma_only"):
            raise ValueError("memory ownership and phase required")
        if type(size) is not int or size <= 0 or type(alignment) is not int or alignment <= 0 or alignment & (alignment - 1):
            raise ValueError("invalid allocation size/alignment")
        current = self.base + self.used
        phys = (current + alignment - 1) & -alignment
        if phys > U64 or phys < self.base or phys + size > self.base + self.capacity:
            raise MemoryError(f"{self.name}: modeled capacity exceeded")
        item = VirtualAllocation(self.name, phys, size, self.next_token,
                                 self.used, self.top_token, self.generation,
                                 owner, phase)
        self.allocations.append(item)
        self.used = phys + size - self.base
        self.top_token = self.next_token
        self.next_token += 1
        return item

    def release(self, item: VirtualAllocation, *, consumers_quiesced: bool):
        if not consumers_quiesced:
            raise RuntimeError("cannot release before CPU/DMA quiescence")
        if not self.allocations or self.allocations[-1] != item or item.token != self.top_token:
            raise RuntimeError("stale, wrong-region or non-LIFO allocation")
        self.allocations.pop()
        self.used = item.previous_used
        self.top_token = item.previous_token

    def reset(self, *, consumers_quiesced: bool):
        if not consumers_quiesced:
            raise RuntimeError("cannot reset while CPU/DMA active")
        self.allocations.clear()
        self.used = 0
        self.generation += 1
        self.top_token = 0

    def as_dict(self):
        return dict(name=self.name, kind=self.kind, base=self.base,
                    modeled_bytes=self.capacity, cpu_visible=self.cpu_visible,
                    outstanding=[a.as_dict() for a in self.allocations])


def configured_regions(cfg, *, profile="boot_live"):
    """Produce nonoverlapping allocatable regions from actual SoC model limits."""
    layout_by_name = {}
    for compute in (s["name"] for s in cfg["subsystems"] if s["type"] == "compute"):
        layout = build_sram_layout(cfg, compute, profile=profile)
        for attr in ("descriptors", "payload"):
            region = getattr(layout, attr)
            layout_by_name[f"{compute}.sram.{attr}"] = VirtualRegion(
                f"{compute}.sram.{attr}", "sram", region.start, region.size, True)
        if layout.boot_scratch is not None and layout.boot_scratch.size:
            region = layout.boot_scratch
            layout_by_name[f"{compute}.sram.boot_scratch"] = VirtualRegion(
                f"{compute}.sram.boot_scratch", "sram", region.start, region.size, True)
    mapping = {r["name"]: r for r in cfg["address_map"]["data"]}
    modeled = 1 << number(cfg["verification"]["memory"]["model_address_bits"])
    for target in cfg["memory_targets"]:
        name = target["name"]
        r = mapping[name]
        base = number(r["base"])
        capacity = min(number(r["size"]), modeled)
        # Reserved space is explicit and cannot accidentally overlap the
        # model's low addresses used in independent BFM coverage.
        reserve = 0x100
        if capacity <= reserve:
            raise ValueError(f"{name}: backing model too small")
        layout_by_name[name] = VirtualRegion(
            name, target["kind"], base + reserve, capacity - reserve, False)
    return layout_by_name


def validate_cpu_allocation(actual_phys: int, expected: VirtualAllocation):
    """Cross-check a CPU-produced address against the Python virtual plan."""
    if type(actual_phys) is not int or actual_phys != expected.phys:
        raise AssertionError(
            f"{expected.region}: CPU allocated {actual_phys!r}, expected {expected.phys:#x}")
