#!/usr/bin/env python3
"""Use the existing pinned Bender resolver to compile one project-selected SoC."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import yaml
import project_catalog
from regress import Resolver, append_pinned_dma_and_bender_sources, filelist_text, load_config

ROOT = Path(__file__).resolve().parents[1]


def selected(project):
    projects = {p["id"]: p for p in project_catalog.projects(ROOT)}
    if project not in projects:
        raise ValueError("unknown SoC project")
    out = ROOT / ".tools/projects" / project
    manifest_path = out / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("generate selected full-chip RTL before compiling")
    built = json.loads(manifest_path.read_text())
    if (built["project_id"] != project or not built["generated_full_chip"]
            or built["source_config_sha256"] != projects[project]["config_sha256"]):
        raise ValueError("selected build does not match project source")
    resolver = Resolver(load_config(ROOT / "config/regression.yaml"))
    spec = {"sources": "noc", "ip": ["picorv32", "serv", "wb2axip",
            "verilog_axi", "pulp_idma"], "bender_targets": ["chip_boot", "dma"]}
    sources, includes, defines = resolver.sources(spec)
    networks = json.loads((out / "noc/floonoc/manifest.json").read_text())["networks"]
    sources += [str(out / "noc/floonoc" / v["package"])
                for _, v in sorted(networks.items())]
    sources += [str(out / "noc/floonoc" / v["top"])
                for _, v in sorted(networks.items())]
    append_pinned_dma_and_bender_sources(spec, resolver, sources, includes, defines)
    replace = {
        str(ROOT / "gen/chip/soc_top.sv"): str(out / "chip/soc_top.sv"),
        str(ROOT / "gen/chip/full_chip_tb.sv"): str(out / "chip/full_chip_tb.sv"),
        str(ROOT / "gen/supernoc/soc_noc.sv"): str(out / "supernoc/soc_noc.sv"),
    }
    sources = list(dict.fromkeys(replace.get(p, p) for p in sources))
    if not set(replace.values()).issubset(sources):
        raise ValueError("project-selected Bender top/wrapper missing")
    if any(p.startswith(str(ROOT / "gen/chip/"))
           or p.startswith(str(ROOT / "gen/supernoc/"))
           or p.startswith(str(ROOT / "gen/noc/floonoc/"))
           for p in sources):
        raise ValueError("default project RTL leaked into selected filelist")
    for p in sources:
        if not Path(p).is_file():
            raise ValueError("missing selected compiler input: " + p)
    data = filelist_text(sources, list(dict.fromkeys(includes)),
                         list(dict.fromkeys(defines)))
    filelist = out / "chip/sources.f"
    filelist.write_text(data)
    return out / "chip", {
        "schema_version": 1, "project_id": project, "top": "full_chip_tb",
        "filelist": filelist.relative_to(ROOT).as_posix(),
        "filelist_sha256": hashlib.sha256(data.encode()).hexdigest(),
        "selected_noc_count": len(networks), "source_count": len(sources),
        "compile_status": "not_run"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", required=True)
    p.add_argument("--verilator", default="verilator")
    p.add_argument("--files-only", action="store_true")
    args = p.parse_args()
    out, data = selected(args.project)
    if args.files_only:
        data["compile_status"] = "source_selected_only"
    else:
        command = [args.verilator, "--lint-only", "--timing", "-Wno-fatal",
                   "--top-module", data["top"], "-f", str(ROOT / data["filelist"])]
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        (out / "compile.log").write_text(
            " ".join(command) + "\n" + completed.stdout + completed.stderr)
        data["compile_status"] = ("passed" if completed.returncode == 0 else "failed")
    (out / "compile-result.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    if data["compile_status"] == "failed":
        print((out / "compile.log").read_text()[-16000:])
        raise SystemExit(1)
    print(data["project_id"], data["compile_status"],
          data["selected_noc_count"], "FlooNoCs",
          data["source_count"], "compiler sources")


if __name__ == "__main__":
    main()
