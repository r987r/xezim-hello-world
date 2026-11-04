#!/usr/bin/env python3
"""Run the exact resolved SoC variant through upstream slang-hier.

Usage:
  python3 tools/regress.py supernoc --stage files
  python3 tools/design_elaborate.py --profile supernoc

Requires the external slang-hier binary. This script fails closed: a missing
binary or parse error never creates a pretend successful elaboration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
FORMAT = "{inst}\\t{module}\\t{file}"


def analyze(root: Path, profile: str, binary: str = "slang-hier") -> dict:
    root = root.resolve()
    config = yaml.safe_load((root / "config/regression.yaml").read_text())
    if profile not in config["tests"]:
        raise ValueError(f"unknown regression profile {profile!r}")
    top = config["tests"][profile].get("top")
    if not isinstance(top, str) or not top:
        raise ValueError(f"{profile}: this profile has no unique top")
    files = root / ".tools/regression" / profile / "sources.f"
    if not files.is_file():
        raise ValueError(f"{profile}: no resolved filelist; run tools/regress.py {profile} --stage files")
    exe = shutil.which(binary)
    if not exe:
        raise ValueError(f"slang-hier executable not found: {binary}")
    argv = [exe, "--top", top, "-f", str(files), "--custom-format", FORMAT]
    run = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=300,
                         check=False)
    if run.returncode:
        raise ValueError(f"slang-hier failed for {profile} (exit {run.returncode}):\n"
                         + (run.stderr + "\n" + run.stdout)[-6000:])
    instances = []
    for line in run.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) == 3 and fields[0].strip():
            instances.append({"path": fields[0].strip(), "module": fields[1].strip(),
                              "source": fields[2].strip()})
    if not instances:
        raise ValueError(f"{profile}: slang-hier returned no recognizable hierarchy")
    fingerprint = hashlib.sha256(files.read_bytes()).hexdigest()
    return {"schema_version": 1, "profile": profile, "top": top,
            "evidence": "elaborated_slang_hier",
            "filelist_sha256": fingerprint, "command": argv,
            "instances": instances, "diagnostics": run.stderr.splitlines()}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--profile", required=True)
    cli.add_argument("--root", type=Path, default=ROOT)
    cli.add_argument("--slang-hier", default="slang-hier")
    cli.add_argument("--output", type=Path)
    args = cli.parse_args()
    data = analyze(args.root, args.profile, args.slang_hier)
    result = json.dumps(data, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result)
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
