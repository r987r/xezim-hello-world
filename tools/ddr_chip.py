"""Build an opt-in source-true Memory0 DDR4 variant; leave checked-in gen/ unchanged.

All controller artifacts are emitted from pinned upstream LiteDRAM, never an RTL
copy or substitute AXI RAM. This module is called by the *existing* regression
runner. Both Data and Config NoCs are regenerated from the same enlarged
memory0.ctrl 16-KiB aperture and the original SoC YAML.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
DDR = ROOT / "rtl" / "memory" / "ddr4"


def variant_configuration(source: dict) -> dict:
    cfg = copy.deepcopy(source)
    regions = [r for r in cfg["address_map"]["config"]
               if r["name"] == "memory0.ctrl"]
    if len(regions) != 1 or int(regions[0]["base"], 0) != 0x40030000:
        raise ValueError("DDR-B requires the known independent memory0.ctrl aperture")
    if int(regions[0]["size"], 0) != 0x1000:
        raise ValueError("DDR-B 16-KiB opt-in decode needs a 4-KiB baseline")
    regions[0]["size"] = "0x4000"
    targets = [x for x in cfg["memory_targets"] if x["name"] == "memory0.ddr0"]
    if len(targets) != 1 or targets[0]["controller"] != "litedram":
        raise ValueError("DDR-B target missing")
    if targets[0]["simulation"]["backend"] != "axi_ram":
        raise ValueError("baseline memory model changed")
    targets[0]["simulation"]["backend"] = "litedram_sim"
    return cfg


def prepare(cfg: dict, out: Path) -> dict:
    import floonoc_gen
    import supernoc_gen
    import socgen
    sys.path.insert(0, str(DDR))
    from port_contract import emitted_port_widths
    from config_noc_init_contract import compile_transport
    from check_rtl import generated_sources

    out.mkdir(parents=True, exist_ok=True)
    ddr_generated = ROOT / ".tools" / "ddr4" / "litedram_sim"
    core = ddr_generated / "gateware" / "soc_ddr4_sim.v"
    if not core.is_file():
        raise ValueError("generate pinned LiteDRAM first: python3 rtl/memory/ddr4/bringup.py generate")
    ports = emitted_port_widths(core.read_text(), expected_address_bits=25)
    controller_files = generated_sources(ddr_generated)
    from bringup import preflight
    upstream = preflight()
    if upstream["model"]["isolated_simulation_bytes"] != 32 * 1024 * 1024:
        raise ValueError("real LiteDRAM modeled storage must remain exactly 32MiB")

    variant = variant_configuration(cfg)
    # socgen's fast standalone memory TB intentionally rejects this backend.
    # Instead validate its physical address/routing invariants separately.
    socgen.check_region_map(variant["address_map"]["config"], 32, "config")
    knobs = yaml.safe_load((ROOT / "config" / "interface_contracts.yaml").read_text())
    root = out / "ddr_noc"
    noc_root = root / "noc" / "floonoc"
    floonoc_gen.generate_all(variant, knobs, noc_root)
    noc_manifest = supernoc_gen.emit(variant, noc_root,
                                    root / "supernoc" / "supernoc_tb.sv")
    plan = json.loads((ddr_generated / "ddr4_init_plan.json").read_text())
    csr = json.loads((ddr_generated / "csr.json").read_text())
    wb_bits = ports["wb_ctrl_adr"]
    contract = compile_transport(variant, plan, csr, generated_wb_adr_bits=wb_bits)
    if contract["configured_window_bytes"] != 0x4000:
        raise ValueError("DDR-B independent control decode remains 4KiB")
    if contract["generated_wb_base"] % 0x4000:
        raise ValueError("unaligned generated controller Wishbone base")
    if not contract["actions"] or contract["actions"][-1]["op"] != "config_read32":
        raise ValueError("DDR-B generated init commands incomplete")
    (root / "soc.yaml").write_text(yaml.safe_dump(variant, sort_keys=False))
    (root / "ddr4_init_script.json").write_text(json.dumps(contract, indent=2) + "\n")
    return {
        "variant_cfg": variant, "noc_manifest": noc_manifest, "noc_root": noc_root,
        "source_root": root, "wb_base": contract["generated_wb_base"],
        "wb_bits": wb_bits, "controller_files": controller_files,
        "contract": contract
    }


def source_closure(sources: list[str], info: dict) -> list[str]:
    """Replace ONLY opt-in generated NoC objects, never change baseline gen/."""
    root = ROOT / "gen"
    replacement = info["source_root"]
    changed = []
    for path in sources:
        p = Path(path)
        try:
            rel = p.relative_to(root)
        except ValueError:
            changed.append(path)
            continue
        if rel.parts[:2] == ("noc", "floonoc") or rel.parts[:1] == ("supernoc",):
            updated = replacement / rel
            if not updated.is_file():
                raise ValueError(f"regenerated DDR NoC source absent: {updated}")
            changed.append(str(updated))
        else:
            changed.append(path)
    changed += [str(ROOT / "rtl" / "memory" / "ddr4" / name)
                for name in ("soc_aperture_guard.sv", "soc_axi_bridge.sv",
                             "soc_axi_wishbone_bridge.sv", "soc_fullchip_target.sv")]
    changed += [str(p) for p in info["controller_files"]]
    return list(dict.fromkeys(changed))
