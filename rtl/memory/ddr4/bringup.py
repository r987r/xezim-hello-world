#!/usr/bin/env python3
"""DDR4-only LiteDRAM generation and interface-contract preflight.

Does not modify the shared NoC/chip generators or checked-in gen/ tree.
A successful preflight is NOT an RTL simulation or DDR PHY validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import yaml
import sim_model
from port_contract import CORE_NAME, AXI_SIGNALS, AXI_OUTPUT_SIGNALS, emitted_port_widths

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PROFILE = HERE / "litedram_sim.yml"
DEFAULT_TARGET = "memory0.ddr0"
DEFAULT_OUTPUT = ROOT / ".tools" / "ddr4" / "litedram_sim"

# LiteDRAM standalone AXI has fewer signals than the SoC NoC AXI4 interface.
# Verify actual generated signals before approving the memory-local adapter.
def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def read_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text())
    require(isinstance(value, dict), f"{path}: expected mapping")
    return value


def validate(soc: dict, lock: dict, profile: dict,
             target: str = DEFAULT_TARGET, noc_manifest: dict | None = None) -> dict:
    """Validate against SoC configuration rather than inventing a second source."""
    bus = soc["buses"]["data"]
    require(bus.get("protocol") == "axi4", "DDR target must use AXI4")
    for name, value in (("addr_bits", 64), ("data_bits", 64), ("id_bits", 4)):
        require(bus.get(name) == value, f"SoC {name} changed; review DDR adapter contract")

    entries = [t for t in soc["memory_targets"] if t["name"] == target]
    require(len(entries) == 1, f"expected one memory target named {target}")
    entry = entries[0]
    require(entry.get("kind") == "ddr" and entry.get("controller") == "litedram",
            f"{target}: expected LiteDRAM DDR target")
    require(entry.get("simulation", {}).get("backend") == "axi_ram",
            "existing SoC functional memory backend changed; review before integration")

    matches = [m for m in soc["address_map"]["data"] if m["name"] == target]
    require(len(matches) == 1, f"{target}: missing/duplicate address-map window")
    window = matches[0]
    base, size = (int(window[key], 0) if isinstance(window[key], str)
                  else int(window[key]) for key in ("base", "size"))
    require(base >= 0 and size > 0 and base % size == 0,
            f"{target}: expected aligned, nonempty DDR memory window")
    require(base + size <= 1 << bus["addr_bits"], f"{target}: address range overflows AXI")
    outputs = soc["networks"]["global_data"]["outputs"]
    require(any(p.get("target") == target for p in outputs),
            f"{target}: not reachable via configured global data network")

    require(profile.get("memtype") == "DDR4", "expected DDR4 profile")
    require(profile.get("sdram_phy") in ("USDDRPHY", "USPDDRPHY"),
            "expected upstream DDR4 geometry class; --sim substitutes SDRAMPHYModel")
    require(profile.get("cpu") is None, "standalone profile must expose Wishbone wb_ctrl")
    require(profile.get("sdram_rank_nb") == 1, "initial test covers one rank")
    require(profile.get("sdram_module_nb") == 8, "initial test covers 64-bit DDR4 DQ")
    require(profile.get("with_refresh") is True, "refresh must remain enabled")
    ports = profile.get("user_ports")
    require(isinstance(ports, dict) and list(ports) == ["axi_0"],
            "isolation test must expose exactly one AXI user port")
    axi = ports["axi_0"]
    require(axi.get("type") == "axi", "axi_0 must be an AXI port")
    require(axi.get("data_width") == bus["data_bits"], "AXI data width mismatch")
    require(axi.get("id_width") == bus["id_bits"], "AXI ID width mismatch")
    require(axi.get("block_until_ready") is True,
            "DDR requests must be blocked until controller init completes")

    geometry = sim_model.budget(profile, read_yaml(HERE / "sim_geometry.yml"))

    pin = lock["third_party"]["litedram"]
    revision = pin.get("commit", "")
    require(re.fullmatch(r"[0-9a-f]{40}", revision) is not None,
            "LiteDRAM source must have a 40-digit immutable commit")
    require(pin.get("license") == "BSD-2-Clause", "unexpected LiteDRAM license metadata")
    if noc_manifest is not None:
        attached = [p for p in noc_manifest["slaves"] if p.get("endpoint") == "target_crossbar"]
        require(len(attached) == 1, "expected one memory-local target crossbar endpoint")
        for name, key in (("addr", "addr_width"), ("data", "data_width"), ("id", "id_width")):
            require(attached[0][key] == bus[name + "_bits"],
                    f"generated memory-local AXI {name} width differs from SoC contract")
    return {"target": target, "base": base, "size": size,
            "upstream": pin["git"], "commit": revision,
            "license": pin["license"], "axi_data_bits": bus["data_bits"],
            "axi_id_bits": bus["id_bits"], "model": geometry}


def preflight(target: str = DEFAULT_TARGET) -> dict:
    manifest_path = ROOT / "gen" / "supernoc" / "manifest.json"
    noc_manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else None
    return validate(read_yaml(ROOT / "config" / "soc.yaml"),
                    read_yaml(ROOT / "config" / "ip.lock.yaml"),
                    read_yaml(PROFILE), target, noc_manifest)


def source_checkout(revision: str) -> Path:
    source = ROOT / ".tools" / "litedram"
    require((source / "litedram" / "gen.py").is_file(),
            "missing pinned LiteDRAM: run 'python3 tools/ip_fetch.py litedram'")
    result = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=True)
    require(result.stdout.strip() == revision,
            "LiteDRAM checkout differs from pinned commit; run 'python3 tools/ip_fetch.py litedram'")
    return source


def generator_argv(output: Path) -> list[str]:
    return [sys.executable, str(HERE / "sim_model.py"), "--sim", "--name", CORE_NAME,
            "--output-dir", str(output), str(PROFILE)]


def checked_output_dir(output: Path) -> Path:
    """Keep isolated generation inside ignored .tools/ddr4 only."""
    directory = output.resolve()
    sandbox = (ROOT / ".tools" / "ddr4").resolve()
    require(sandbox in directory.parents,
            "DDR4 outputs must stay under ignored .tools/ddr4/ (not shared files)")
    return directory


def generate(contract: dict, output: Path) -> Path:
    source = source_checkout(contract["commit"])
    output = checked_output_dir(output)
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(source) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run(generator_argv(output), cwd=ROOT, env=env, check=True)
    core = output / "gateware" / f"{CORE_NAME}.v"
    require(core.is_file(), f"LiteDRAM generator did not produce {core}")
    # A mismatch in local AXI address bits risks silently aliasing DDR memory.
    expected_bits = contract["model"]["isolated_simulation_bytes"].bit_length() - 1
    ports = emitted_port_widths(core.read_text(), expected_address_bits=expected_bits)
    artifacts = {}
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "ddr4_manifest.json":
            artifacts[str(path.relative_to(output))] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = {"status": "generated-not-simulated", "source": contract,
              "generator": "sim_model.py --sim (pinned LiteDRAM, bounded simulation geometry)", "config": str(PROFILE.relative_to(ROOT)),
              "top": CORE_NAME, "ports": ports, "files_sha256": artifacts,
              "warning": "No AXI transactions, DDR4 initialization, or timing have yet been verified"}
    manifest = output / "ddr4_manifest.json"
    manifest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "generate"))
    parser.add_argument("--target", default=DEFAULT_TARGET,
                        help="configured DDR target in config/soc.yaml")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    contract = preflight(args.target)
    print(json.dumps(contract, indent=2, sort_keys=True))
    if args.action == "generate":
        print(f"Generated manifest: {generate(contract, args.output_dir)}")
    else:
        print("PASS DDR4 static contract preflight (not a DDR RTL test)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError) as error:
        print(f"DDR4 bring-up failed: {error}", file=sys.stderr)
        sys.exit(1)
