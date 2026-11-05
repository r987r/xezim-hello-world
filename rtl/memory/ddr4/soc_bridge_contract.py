"""Fail-closed DDR-B full-chip LiteDRAM AXI interface and aperture contract.

This is an isolated *integration prerequisite*, not a memory responder.
It refuses to pass a 64-bit SoC physical address directly into the 32-bit
standalone controller, to truncate AXI IDs, or to wrap the 32 MiB model.
A future generated RTL adapter must enforce the same checks *on pins* and
return explicit DECERR for unsupported accesses; unit tests of this module
alone do not establish integrated RTL behavior.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json

import yaml

from port_contract import AXI_SIGNALS, CORE_NAME, emitted_port_widths
from sim_model import budget

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TARGET = "memory0.ddr0"


@dataclass(frozen=True)
class MemoryWindow:
    target: str
    physical_base: int
    architectural_size: int
    modeled_size: int
    fabric_addr_bits: int
    fabric_data_bits: int
    fabric_id_bits: int
    controller_addr_bits: int
    controller_data_bits: int
    controller_id_bits: int
    requires_explicit_init: bool
    controller_top: str
    backend: str

    def as_dict(self):
        return asdict(self)


def number(value):
    if isinstance(value, bool):
        raise ValueError("bool cannot be an AXI address or size")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 0)
    raise ValueError("invalid AXI address or size")


def contract(soc: dict, profile: dict, geometry: dict,
             *, generated_verilog: str | None = None) -> MemoryWindow:
    bus = soc.get("buses", {}).get("data", {})
    if bus != {"protocol": "axi4", "addr_bits": 64, "data_bits": 64, "id_bits": 4}:
        raise ValueError("unsupported SoC AXI interface; explicit adapter revision required")
    targets = [v for v in soc.get("memory_targets", []) if v.get("name") == TARGET]
    if len(targets) != 1:
        raise ValueError("DDR target missing or duplicated")
    target = targets[0]
    if target.get("controller") != "litedram" or target.get("kind") != "ddr":
        raise ValueError("target does not select LiteDRAM")
    # The baseline remains axi_ram, and integration must be *opt-in*.
    if target.get("simulation", {}).get("backend") not in ("axi_ram", "litedram_sim"):
        raise ValueError("unknown DDR SoC simulation backend")
    routes = soc.get("networks", {}).get("global_data", {}).get("outputs", [])
    if sum(route.get("target") == TARGET for route in routes) != 1:
        raise ValueError("DDR must have exactly one global DATA NoC ingress")
    regions = [v for v in soc.get("address_map", {}).get("data", [])
               if v.get("name") == TARGET]
    if len(regions) != 1:
        raise ValueError("DDR address window must exist exactly once")
    addr = number(regions[0]["base"])
    size = number(regions[0]["size"])
    if addr < 0 or size <= 0 or addr % size or size & (size - 1):
        raise ValueError("DDR physical window must be aligned power of two")
    if addr + size > 1 << 64:
        raise ValueError("DDR physical aperture overflows 64 bits")
    if profile.get("memtype") != "DDR4":
        raise ValueError("not a DDR4 controller")
    users = profile.get("user_ports", {})
    axi = users.get("axi_0", {})
    if (axi.get("type") != "axi" or axi.get("data_width") != 64
            or axi.get("id_width") != 4):
        raise ValueError("LiteDRAM AXI data/ID contract mismatch")
    if not axi.get("block_until_ready"):
        raise ValueError("DDR AXI port must remain blocked until DFII initialization")
    if not profile.get("with_refresh"):
        raise ValueError("DDR refresh must be enabled")
    sizing = budget(profile, geometry)
    capacity = sizing["isolated_simulation_bytes"]
    if capacity > size:
        raise ValueError("modeled DDR exceeds physical aperture")
    if capacity & (capacity - 1):
        raise ValueError("non-power-of-two modeled DDR size unsupported")
    # LiteDRAM generated address bits reflect its *local* interface, which
    # is not the same as the full-chip 64-bit physical address.
    address_bits = capacity.bit_length() - 1
    if generated_verilog is not None:
        widths = emitted_port_widths(generated_verilog)
        address_bits = widths["user_port_axi_0_awaddr"]
        if widths["user_port_axi_0_araddr"] != address_bits:
            raise ValueError("read/write controller address widths differ")
        if (widths["user_port_axi_0_awid"] != bus["id_bits"]
                or widths["user_port_axi_0_arid"] != bus["id_bits"]):
            raise ValueError("controller AXI ID would be truncated")
    if not 1 <= address_bits <= 32:
        raise ValueError("unsupported local DDR controller address width")
    if capacity > (1 << address_bits):
        raise ValueError("LiteDRAM local AXI address cannot reach modeled DDR capacity")
    return MemoryWindow(
        target=TARGET, physical_base=addr, architectural_size=size,
        modeled_size=capacity, fabric_addr_bits=64, fabric_data_bits=64,
        fabric_id_bits=4, controller_addr_bits=address_bits,
        controller_data_bits=64, controller_id_bits=4,
        requires_explicit_init=True, controller_top=CORE_NAME,
        backend="litedram_sim")


def translate_access(window: MemoryWindow, *, physical: int, length: int,
                     axi_id: int, beat_bytes: int = 8, burst: str = "INCR",
                     atop: int = 0) -> dict:
    """Preflight a requested AXI transaction; NEVER mask the high bits.

    A future RTL slave must DECERR invalid requests while consuming their
    AXI beats and issuing a legal response. This pure function does not.
    """
    if (not isinstance(physical, int) or isinstance(physical, bool)
            or not isinstance(length, int) or isinstance(length, bool)
            or not isinstance(axi_id, int) or isinstance(axi_id, bool)):
        raise ValueError("AXI address/length/id must be integers")
    if not 0 <= axi_id < 1 << window.fabric_id_bits:
        raise ValueError("AXI ID out of range")
    if not 1 <= length <= 256:
        raise ValueError("invalid AXI burst length")
    if beat_bytes not in (1, 2, 4, 8):
        raise ValueError("unsupported AXI transfer size")
    if burst != "INCR":
        raise ValueError("only validated AXI INCR bursts supported")
    if atop != 0:
        raise ValueError("LiteDRAM does not support AXI ATOP atomic accesses")
    if physical < 0 or physical > (1 << window.fabric_addr_bits) - 1:
        raise ValueError("AXI address out of fabric range")
    # Conservative bound for unaligned beats; never accept an access that
    # could cross the modeled aperture or AXI 4 KiB transaction boundary.
    nbytes = length * beat_bytes
    end = physical + nbytes
    lo = window.physical_base
    if physical < lo or end > lo + window.architectural_size:
        raise ValueError("DDR request outside architectural aperture")
    if end > lo + window.modeled_size:
        raise ValueError("DDR request exceeds 32 MiB modeled storage; no aliasing")
    if (physical >> 12) != ((end - 1) >> 12):
        raise ValueError("AXI burst crosses 4 KiB boundary")
    local = physical - lo
    if local + nbytes > 1 << window.controller_addr_bits:
        raise ValueError("local LiteDRAM AXI address would truncate")
    if axi_id >= 1 << window.controller_id_bits:
        raise ValueError("LiteDRAM AXI response ID cannot be represented")
    return {"physical": physical, "local": local, "length": length,
            "beat_bytes": beat_bytes, "id": axi_id,
            "evidence": "contract_preflight_only_no_generated_rtl_claim"}


def from_repo(root: Path = ROOT, *, generated_verilog: Path | None = None):
    root = Path(root)
    soc = yaml.safe_load((root / "config/soc.yaml").read_text())
    profile = yaml.safe_load((root / "rtl/memory/ddr4/litedram_sim.yml").read_text())
    geometry = yaml.safe_load((root / "rtl/memory/ddr4/sim_geometry.yml").read_text())
    rtl = generated_verilog.read_text() if generated_verilog else None
    return contract(soc, profile, geometry, generated_verilog=rtl)


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--generated-verilog", type=Path,
                   help="optional real .tools/ddr4/.../soc_ddr4_sim.v pin check")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    result = from_repo(generated_verilog=a.generated_verilog)
    info = {"schema_version": 1, "integration_state": "contract_only",
            "implementation": result.as_dict(),
            "outstanding": [
                "real NoC-to-LiteDRAM AXI bridge with explicit error responses",
                "DDR Wishbone DFII initialization service on CONFIG NoC",
                "generated SoC/backend selection and Bender source closure",
                "controller ready/reset, CPU/iDMA readback and DFI capture",
            ]}
    txt = json.dumps(info, indent=2) + "\n"
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(txt)
    else:
        print(txt, end="")


if __name__ == "__main__":
    main()
