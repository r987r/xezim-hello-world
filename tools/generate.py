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
import socgen

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- BEGIN GENERATED SOC -->"
END = "<!-- END GENERATED SOC -->"
STAMP = ".generated-root"


class GenerationError(RuntimeError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def generated_section(cfg: dict, meta: dict, diagrams: dict[str, str]) -> str:
    compute = [s for s in meta["subsystems"] if s["type"] == "compute"]
    memory = [s for s in meta["subsystems"] if s["type"] == "memory"]
    results = [
        "<!-- Do not edit this section: regenerate with `make gen`. -->",
        "### Architecture overview — configured intent",
        "",
        "The diagram below shows **logical** chip connectivity. Dashed links are **planned, not integrated RTL**; solid memory-model paths are exercised in the memory testbench.",
        "",
        "[![Generated SoC architecture — PicoRV32, SERV, two global fabrics, HBM and DDR](gen/diagrams/architecture.svg)](gen/diagrams/architecture.svg)",
        "", "[Full-size image](gen/diagrams/architecture.svg) · [Mermaid source](gen/diagrams/architecture.mmd) · [Detailed view](gen/diagrams/architecture.md)", "",
        "### Executable RTL connectivity — memory testbench",
        "",
        "This is the wiring generated in `gen/memory/memory_tb.sv`: two AXI4 master BFMs, the real open-source AXI crossbar, two AXI memory models, and a passive route monitor. It is **not** a full-chip elaboration.",
        "",
        "[![Executable 2x2 AXI RTL connectivity diagram with BFMs and HBM/DDR models](gen/diagrams/rtl-connectivity.svg)](gen/diagrams/rtl-connectivity.svg)",
        "", "[Full-size image](gen/diagrams/rtl-connectivity.svg) · [Mermaid source](gen/diagrams/rtl-connectivity.mmd) · [Detailed view](gen/diagrams/rtl-connectivity.md)", "",
        "### Hierarchical verification plan",
        "",
        "Green scope boxes are **implemented testbenches**, not a claim that the entire SoC was simulated. Grey scope boxes are planned; CI separately determines whether executable scopes pass.",
        "",
        "[![Generated SoC verification hierarchy, implemented versus planned scopes](gen/diagrams/verification.svg)](gen/diagrams/verification.svg)",
        "", "[Full-size image](gen/diagrams/verification.svg) · [Mermaid source](gen/diagrams/verification.mmd) · [Detailed view](gen/diagrams/verification.md)", "",
        "### Generated architecture reference", "",
        f'- **Subsystems:** {len(compute)} compute, {len(memory)} memory; **data:** AXI4 {meta["data_bits"]}-bit, {meta["address_bits"]}-bit addressing; **config:** AXI4-Lite {cfg["buses"]["config"]["data_bits"]}-bit.',
        f'- **Global data NoC:** {cfg["fabrics"]["global_data"]["backend"]} / {cfg["fabrics"]["global_data"]["topology"]} (selected, emitter pending).',
        f'- **Global config NoC:** {cfg["fabrics"]["global_config"]["backend"]} / {cfg["fabrics"]["global_config"]["topology"]} (selected, emitter pending).',
        f'- **Local memory crossbar:** {cfg["fabrics"]["memory_data"]["backend"]}; {meta["ingress"]} ingress × {len(meta["targets"])} targets (executable RTL testbench).',
        "", "| Subsystem | CPU | CPU bus/adapter | DMA | Detailed 2D diagram |", "| --- | --- | --- | --- | --- |",
    ]
    for inst in compute:
        cpu = inst["cpu"]
        results.append(f'| `{inst["name"]}` | `{cpu["ip"]}` | `{cpu["bus"]}` / `{cpu["adapter"]}` | `{meta["common_dma"]}` (planned RTL integration) | [View](gen/diagrams/subsystems/{inst["name"]}.md) |')
    results += ["", "| Memory target | Kind | Selected controller | Simulated implementation | Global address window |", "| --- | --- | --- | --- | --- |"]
    for t in meta["targets"]:
        results.append(f'| `{t["name"]}` | {t["kind"].upper()} | `{t["controller"]}` (not integrated) | `{t["sim_backend"]}` | `0x{t["base"]:x}` / `0x{t["size"]:x}` |')
    results += ["", "| Configuration target | Base address | Size |", "| --- | --- | --- |"]
    for r in meta["config_regions"]:
        results.append(f'| `{r["name"]}` | `0x{r["base"]:x}` | `0x{r["size"]:x}` |')
    results += ["", "| Global output | Configured target | Memory ingress |", "| --- | --- | --- |"]
    for i, output in enumerate(meta["global_data_outputs"]):
        results.append(f'| `{output["name"]}` | `{output["target"]}` | `{i}` |')
    results += ["", "| Verification scope | Status | Entry point |", "| --- | --- | --- |"]
    for scope in cfg["verification"]["scopes"]:
        results.append(f'| `{scope["name"]}` | {scope["status"]} | `{scope.get("command", "not implemented")}` |')
    results += [
        "", "**Explore generated artifacts:** [NoC intermediate representation](gen/noc/fabric_ir.json) · [RTL connection metadata](gen/diagrams/graphs.json) · [verification plan](gen/verification/plan.json) · [route matrix](gen/verification/routes.json) · [memory testbench](gen/memory/memory_tb.sv) · [generated manifest](gen/manifest.json).",
        "", "**Detailed subsystem diagrams:** " + " · ".join(f'[{s["name"]}](gen/diagrams/subsystems/{s["name"]}.md)' for s in meta["subsystems"]) + ".",
    ]
    return "\n".join(results).rstrip() + "\n"


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
    diagrams = diagram_gen.render(cfg, meta, out / "diagrams")
    dump(out / "verification" / "plan.json", verification_plan(cfg, meta))
    dump(out / "verification" / "routes.json", route_matrix(meta))
    (out / "README.md").write_text(
        "# Generated SoC reference\n\nDo not edit. Run `make gen` to atomically regenerate this tree "
        "from `config/soc.yaml`. All output files are version-controlled for diffs.\n\n"
        "The `memory/` SystemVerilog is executable; the global NoC backend choices "
        "in `noc/` are not currently emitted into a full-chip top.\n"
    )
    (out / STAMP).write_text("socgen-v2\n")
    files = {p.relative_to(out).as_posix(): sha(p.read_bytes())
             for p in sorted(out.rglob("*")) if p.is_file()}
    dump(out / "manifest.json", {
        "schema_version": 2, "config_sha256": sha(cfg_path.read_bytes()),
        "files_sha256": files,
        "note": "No timestamp; regenerated files should be byte-for-byte stable.",
    })
    return embed(readme.read_text(), generated_section(cfg, meta, diagrams))


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
