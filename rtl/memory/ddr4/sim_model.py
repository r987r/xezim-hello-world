#!/usr/bin/env python3
"""Run pinned LiteDRAM's --sim generator with bounded DRAM geometry.

LiteDRAM's DFI model generates a dense memory per bank. The ordinary
MT40A512M8 x64 DDR4 model would allocate ~4 GiB of modeled storage. Only
this ISOLATED simulation swaps nrows/ncols; timing and controller RTL still
come from the pinned upstream source. Never use this generated model as a
production DDR4 PHY/geometry or a full 1-GiB SoC memory backing store.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


def power_of_two(value: int) -> bool:
    return type(value) is int and value > 0 and value & (value - 1) == 0


def estimated_storage_bytes(banks: int, rows: int, cols: int,
                            data_bits: int, ranks: int = 1) -> int:
    for label, num in (("banks", banks), ("rows", rows), ("cols", cols),
                       ("data_bits", data_bits), ("ranks", ranks)):
        if not power_of_two(num):
            raise ValueError(f"{label} must be a positive power of two, got {num}")
    if data_bits % 8:
        raise ValueError("memory data bits must be byte-addressable")
    return banks * rows * cols * (data_bits // 8) * ranks


def budget(profile: dict, geometry: dict) -> dict:
    """Validate pinned-device assumptions and report both memory capacities."""
    if profile.get("memtype") != "DDR4":
        raise ValueError("geometry scaling is restricted to DDR4 simulation")
    if profile.get("sdram_module") != geometry.get("module"):
        raise ValueError("DDR4 simulation module disagrees with profile")
    if profile.get("sdram_rank_nb") != 1:
        raise ValueError("only one DDR4 simulation rank supported")
    byte_groups = profile.get("sdram_module_nb")
    if not power_of_two(byte_groups):
        raise ValueError("DDR4 data byte group count must be power of two")
    base = geometry["expected_upstream"]
    sim = geometry["simulation"]
    for key in ("banks", "rows", "cols"):
        if not power_of_two(base.get(key)):
            raise ValueError(f"invalid upstream DDR4 {key}")
    if not power_of_two(sim.get("rows")) or sim["rows"] < 2048:
        raise ValueError("simulation rows must retain DDR4 A10 command bit")
    if not power_of_two(sim.get("cols")) or sim["cols"] < 128:
        raise ValueError("simulation columns must support burst access")
    if sim["rows"] > base["rows"] or sim["cols"] > base["cols"]:
        raise ValueError("simulation cannot exceed pinned device geometry")
    max_bytes = geometry.get("max_model_bytes")
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("expected positive max_model_bytes")
    real = estimated_storage_bytes(base["banks"], base["rows"], base["cols"],
                                   byte_groups * 8)
    scaled = estimated_storage_bytes(base["banks"], sim["rows"], sim["cols"],
                                     byte_groups * 8)
    if scaled > max_bytes:
        raise ValueError(f"scaled DDR model {scaled} bytes exceeds budget {max_bytes}")
    return {"device": geometry["module"], "banks": base["banks"],
            "production_device_bytes": real, "isolated_simulation_bytes": scaled,
            "sim_rows": sim["rows"], "sim_cols": sim["cols"],
            "max_model_bytes": max_bytes, "simulation_only": True}


def scaled_device_class(original: type, geometry: dict) -> type:
    """Keep full DDR4 DFI command/address width while bounding stored rows.

    The isolated controller sees the reduced row/column geometry; DFI still
    exposes the original device's A[14:0] command address to encode mode
    registers. The dense model storage is calculated from reduced rowbits.
    """
    expected = geometry["expected_upstream"]
    for name, attr in (("banks", "nbanks"), ("rows", "nrows"), ("cols", "ncols")):
        if getattr(original, attr) != expected[name]:
            raise ValueError(f"pinned LiteDRAM {name} changed: revalidate geometry")
    sim = geometry["simulation"]
    original_addressbits = expected["rows"].bit_length() - 1

    class SimDevice(original):
        nrows = sim["rows"]
        ncols = sim["cols"]

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.geom_settings.addressbits = max(
                self.geom_settings.addressbits, original_addressbits)

    SimDevice.__name__ = original.__name__
    return SimDevice


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--sim", action="store_true")
    opts, _ = parser.parse_known_args()
    if not opts.sim:
        raise ValueError("refusing to scale physical DDR geometry without --sim")
    profile = yaml.safe_load((HERE / "litedram_sim.yml").read_text())
    geometry = yaml.safe_load((HERE / "sim_geometry.yml").read_text())
    info = budget(profile, geometry)

    # Import and modify a Python device-geometry class in THIS generator process
    # only. The upstream controller, frontend, PHY model and timings are reused.
    # This is not an RTL fork or a module outside the memory subsystem.
    from litedram import modules
    original = getattr(modules, info["device"])
    setattr(modules, info["device"], scaled_device_class(original, geometry))
    print(f"DDR4 isolated simulation geometry: {info['isolated_simulation_bytes']} bytes "
          f"(real device {info['production_device_bytes']} bytes)", flush=True)
    from litedram.gen import main as upstream_main
    upstream_main()


if __name__ == "__main__":
    main()
