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

from selected_rtl_provenance import selected, public_fields

ROOT = Path(__file__).resolve().parents[1]
FORMAT = "{inst}|||{module}|||{file}"



def audit_selected_hierarchy(root: Path, top: str, rows: list[dict],
                             source_hashes: dict[str, str]) -> list[dict]:
    """Bind every slang-reported hierarchy source to the selected filelist.

    Successful *syntax/elaboration* and exact-source provenance are distinct
    from proven active netlist bit/port connections and routed traffic.
    """
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError("missing selected RTL source inventory")
    if not isinstance(rows, list) or not rows:
        raise ValueError("empty elaborated hierarchy")
    seen = set()
    verified = []
    root_seen = False
    for item in rows:
        path = item.get("path")
        module = item.get("module")
        raw = item.get("source")
        if any(not isinstance(x, str) or not x.strip()
               for x in (path, module, raw)):
            raise ValueError("slang hierarchy missing required identity/source")
        if path in seen:
            raise ValueError("duplicate elaborated instance path: " + path)
        seen.add(path)
        original = Path(raw)
        if original.is_symlink():
            raise ValueError("unsafe symlink in elaborated source: " + raw)
        source = (original if original.is_absolute() else root / original).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            raise ValueError("elaborated source absent/outside checkout: " + raw)
        relative = source.relative_to(root).as_posix()
        expected = source_hashes.get(relative)
        if not isinstance(expected, str):
            raise ValueError("elaborated instance uses unselected RTL: " + relative)
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("selected elaborated RTL changed since source attestation")
        if path == top and module == top:
            root_seen = True
        verified.append({
            "path": path, "module": module, "source": relative,
            "source_sha256": expected,
            "evidence": "selected_source_hash_and_elaborator_output_not_bit_proof",
        })
    if not root_seen:
        raise ValueError("selected elaboration omitted the required root top")
    return verified

def analyze(root: Path, profile: str, binary: str = "slang-hier") -> dict:
    root = root.resolve()
    attested = selected(root, profile)
    top = attested["top"]
    files = attested["source_list"]
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
        fields = line.split("|||")
        if len(fields) == 3 and fields[0].strip():
            instances.append({"path": fields[0].strip(), "module": fields[1].strip(),
                              "source": fields[2].strip()})
    if not instances:
        raise ValueError(f"{profile}: slang-hier returned no recognizable hierarchy")
    checked = audit_selected_hierarchy(
        root, top, instances, attested["selected_source_sha256"])
    return {**public_fields(attested), "evidence": "elaborated_slang_hier_inputs_attested",
            "command": argv, "instances": checked,
            "source_hierarchy_sha256": hashlib.sha256(json.dumps(
                checked, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "bit_level_connectivity_proven": False,
            "observed_protocol_traffic": False,
            "diagnostics": run.stderr.splitlines()}


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
