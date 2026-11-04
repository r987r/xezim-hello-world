#!/usr/bin/env python3
"""Reproducible SoC generation. One config -> RTL, NoC IR, DV metadata, 2D docs.

`make gen` replaces the complete generator-owned `gen/` tree, including removal
of outputs that no longer exist after a configuration change. `--check` builds
in a temporary directory and checks exact file names, contents and README
embedded diagrams without writing to the checkout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

import yaml

import diagram_gen
import bootgen
import socgen
import floonoc_gen
import supernoc_gen
import full_chip_gen

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- BEGIN GENERATED SOC -->"
END = "<!-- END GENERATED SOC -->"
STAMP = ".generated-root"


class GenerationError(RuntimeError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def generated_section(cfg: dict, meta: dict, diagrams: dict[str, str], nocs: dict) -> str:
    """Only one general SoC NoC picture. RTL/port topology stays inspectable."""
    compute = [s for s in meta["subsystems"] if s["type"] == "compute"]
    networks = nocs["networks"]
    result = [
        "<!-- Do not edit this section: regenerate with `make gen`. -->",
        "### Whole-SoC data and configuration NoCs",
        "",
        "The **single architecture diagram** below includes all local/global FlooNoCs, "
        "compute CPU/DMA/SRAM blocks and memory target crossbar. It is generated "
        "from the same SoC configuration and FlooGen endpoint topology as the real "
        "structural RTL. **Solid links show generated optional iDMA/CSR wiring (enabled in DMA mode); dashed links show pending physical controllers.** "
        "The same NoC RTL is instantiated by BFM, CPU boot, and dual-DMA configurations.",
        "",
        "[![Complete hierarchical SoC and all data/config FlooNoCs](gen/diagrams/noc-hierarchy.svg)](gen/diagrams/noc-hierarchy.svg)",
        "",
        "[Full-size diagram](gen/diagrams/noc-hierarchy.svg) · "
        "[Editable Mermaid](gen/diagrams/noc-hierarchy.mmd) · "
        "[Machine-readable router/NI/link graph](gen/diagrams/noc-topology.json) · "
        "[Real generated FlooNoC RTL](gen/noc/floonoc/manifest.json)",
        "",
        f"**Configured topology:** {len(compute)} compute subsystems, "
        f"{len(networks)} independent FlooNoC instances, "
        f"{sum(x['routers'] for x in networks.values())} total generated routers. "
        f"Data: {meta['data_bits']}-bit AXI4; control: "
        f"{cfg['buses']['config']['data_bits']}-bit AXI4 transport "
        "for AXI4-Lite endpoint bridges. CPU/reset adapters are attached in the boot configuration; the BFM scope uses AXI agents.",
        "",
        "**Verification truth:** Xezim exercises separate CPU cold-boot/SRAM and "
        "Verilog-AXI memory testbenches. Both Xezim and Verilator have compiled "
        "the eight structural FlooNoCs. The unified `make dv-supernoc` regression "
        "connects all meshes to upstream AXI agents and checks destinations, data, "
        "bursts, concurrent IDs, stalls and downstream SLVERR. Xezim NoC traffic "
        "is not verified. The `make dv-chip` boot configuration runs the real CPUs through "
        "the shared NoCs with CPU0-coordinated init/run/check and AXI memory stand-ins. "
        "See [chip boot scope](docs/full-chip-boot.md) and [DMA integration](docs/dma-bringup.md); `make dv-chip-dma` tests both real engines through data/config FlooNoCs with the CPUs held in reset and host-initialized DMA SRAM.",
        "",
        "### Generated NoC sources (no duplicate pictures)",
        "",
        "| Network | Routers | Generated top | Config |",
        "| --- | ---: | --- | --- |",
    ]
    for name, entry in sorted(networks.items()):
        base = "gen/noc/floonoc/"
        result.append(
            f'| `{name}` | {entry["routers"]} | '
            f'[SystemVerilog]({base + entry["top"]}) | '
            f'[FlooGen YAML]({base + entry["config"]}) |'
        )
    result += [
        "",
        "**Validation and generated metadata:** "
        "[NoC interface budgets](config/interface_contracts.yaml) · "
        "[routing IR](gen/noc/fabric_ir.json) · "
        "[memory testbench](gen/memory/memory_tb.sv) · "
        "[verification plan](gen/verification/plan.json) · "
        "[generated tree manifest](gen/manifest.json).",
    ]
    return "\n".join(result).rstrip() + "\n"


def embed(readme: str, body: str) -> str:
    if readme.count(START) != 1 or readme.count(END) != 1:
        raise GenerationError("README must contain exactly one BEGIN and END GENERATED SOC marker")
    start, end = readme.index(START), readme.index(END)
    if end <= start:
        raise GenerationError("README generated markers are reversed")
    return readme[:start + len(START)] + "\n\n" + body.rstrip() + "\n\n" + readme[end:]


def verification_plan(cfg: dict, meta: dict) -> dict:
    return {
        "schema_version": 1,
        "source_config": "config/soc.yaml",
        "buses": cfg["buses"],
        "scopes": cfg["verification"]["scopes"],
        "memory": {
            "dut": f'{meta["memory_subsystem"]}.memory_data',
            "testbench_source": "gen/memory/memory_tb.sv",
            "ingress_master_agents": meta["ingress"],
            "burst_beats": meta["burst_beats"],
            "target_names": [t["name"] for t in meta["targets"]],
            "note": "Behavioral AXI RAM, not integrated DRAM controller/PHY",
        },
    }


def route_matrix(meta: dict) -> dict:
    """All source/destination pairs exercised by the generated memory TB."""
    return {
        "schema_version": 1,
        "scope": "memory_fabric",
        "ingress_count": meta["ingress"],
        "target_count": len(meta["targets"]),
        "expected_routes": [
            {"source": f"master{i}", "source_port": i,
             "destination": t["name"], "destination_port": j,
             "address_base": f'0x{t["base"]:x}', "address_size": f'0x{t["size"]:x}',
             "read": True, "write": True, "bursts": meta["burst_beats"]}
            for i in range(meta["ingress"]) for j, t in enumerate(meta["targets"])
        ],
    }


def dump(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n")


def build(cfg_path: Path, out: Path, readme: Path) -> str:
    """Build every artifact into out; returns expected README text."""
    cfg = yaml.safe_load(cfg_path.read_text())
    meta = socgen.validate(cfg)
    socgen.run(cfg_path, out / "memory")
    # socgen.run populates target_count on its own validation copy.
    meta["target_count"] = len(meta["targets"])
    bootgen.emit(cfg, out / "boot")
    # FlooGen is installed from the immutable IP lock and emits actual
    # checked-in RTL alongside all diagrams and the generated NoC IR.
    knobs = yaml.safe_load((ROOT / "config/interface_contracts.yaml").read_text())
    nocs = floonoc_gen.generate_all(cfg, knobs, out / "noc" / "floonoc")
    noc_dv = supernoc_gen.emit(cfg, out / "noc" / "floonoc", out / "supernoc" / "supernoc_tb.sv")
    full_chip_gen.emit(cfg, noc_dv, out / "noc" / "floonoc", out / "chip")
    diagrams = diagram_gen.render(cfg, meta, out / "diagrams", out / "noc" / "floonoc")
    dump(out / "verification" / "plan.json", verification_plan(cfg, meta))
    dump(out / "verification" / "routes.json", route_matrix(meta))
    (out / "README.md").write_text(
        "# Generated SoC reference\n\nDo not edit. Run `make gen` to atomically regenerate this tree "
        "from `config/soc.yaml`. All output files are version-controlled for diffs.\n\n"
        "The `memory/` SystemVerilog and `boot/` firmware images are executable "
        "in separate scoped testbenches. All configured local/global FlooNoC "
        "networks have checked-in structural SystemVerilog in noc/floonoc. "
        "supernoc/supernoc_tb.sv connects them with upstream AXI BFMs; run "
        "make dv-supernoc for current-source routed-traffic verification. "
        "chip/ contains the actual CPU/NoC boot configuration, phased firmware and shared checker; "
        "run make dv-chip. Real iDMA and physical controllers remain separate integration work.\n"
    )
    (out / STAMP).write_text("socgen-v2\n")
    files = {p.relative_to(out).as_posix(): sha(p.read_bytes())
             for p in sorted(out.rglob("*")) if p.is_file()}
    dump(out / "manifest.json", {
        "schema_version": 2, "config_sha256": sha(cfg_path.read_bytes()),
        "files_sha256": files,
        "note": "No timestamp; regenerated files should be byte-for-byte stable.",
    })
    return embed(readme.read_text(), generated_section(cfg, meta, diagrams, nocs))


def tree_files(folder: Path) -> dict[str, bytes]:
    if not folder.exists():
        return {}
    return {p.relative_to(folder).as_posix(): p.read_bytes()
            for p in folder.rglob("*") if p.is_file()}


def differences(expected: Path, actual: Path, expected_readme: str, readme: Path) -> list[str]:
    a, b = tree_files(expected), tree_files(actual)
    changes = [f"MISSING gen/{path}" for path in sorted(set(a) - set(b))]
    changes += [f"STALE gen/{path}" for path in sorted(set(b) - set(a))]
    changes += [f"CHANGED gen/{path}" for path in sorted(set(a) & set(b)) if a[path] != b[path]]
    if readme.read_text() != expected_readme:
        changes.append("CHANGED README.md generated section")
    return changes


def execute(cfg: Path, out: Path, readme: Path, check: bool = False) -> int:
    # Never delete user files outside of the declared generator-owned root.
    if out.is_symlink():
        raise GenerationError(f"refusing to operate on symlink output: {out}")
    if out.exists() and not (out / STAMP).is_file():
        raise GenerationError(f"refusing to delete unmarked existing output tree: {out}")
    with tempfile.TemporaryDirectory(prefix="socgen-") as temporary:
        staging = Path(temporary) / "gen"
        staging.mkdir()
        readme_result = build(cfg, staging, readme)
        if check:
            differences_found = differences(staging, out, readme_result, readme)
            if differences_found:
                for item in differences_found:
                    print(item, file=sys.stderr)
                print("Generated files are out of date. Run `make gen`.", file=sys.stderr)
                return 1
            print(f"PASS: {len(tree_files(staging))} generated files and README match config")
            return 0
        # Preserve a backup until both tree and README have been updated.
        out.parent.mkdir(parents=True, exist_ok=True)
        backup = out.parent / (out.name + ".previous-socgen")
        if backup.exists():
            raise GenerationError(f"refusing to overwrite existing generator backup: {backup}")
        original_readme = readme.read_text()
        if out.exists():
            out.rename(backup)
        try:
            shutil.copytree(staging, out)
            readme.write_text(readme_result)
        except Exception:
            if out.exists():
                shutil.rmtree(out)
            if backup.exists():
                backup.rename(out)
            readme.write_text(original_readme)
            raise
        if backup.exists():
            shutil.rmtree(backup)
        print(f"Generated {len(tree_files(out))} files; replaced gen/ and README section (stale outputs removed)")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/soc.yaml")
    parser.add_argument("--out", type=Path, default=ROOT / "gen")
    parser.add_argument("--readme", type=Path, default=ROOT / "README.md")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        return execute(args.config, args.out, args.readme, args.check)
    except (GenerationError, socgen.ConfigError, ValueError, OSError, KeyError, yaml.YAMLError) as exc:
        print("Generation error:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
