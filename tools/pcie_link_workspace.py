#!/usr/bin/env python3
"""Reserve the existing isolated PCIe capture's source-selected workspace."""
import argparse
import json
from pathlib import Path
import os
import subprocess
import sys

if __package__:
    from .run_workspace import reserve_run
    from .test_identity import selected
else:
    from run_workspace import reserve_run
    from test_identity import selected

ROOT = Path(__file__).resolve().parents[1]
MODES = {
    "l0": ("pcie-link-isolated", "link-training"),
    "bar0": ("pcie-bar0-isolated", "bar-enumeration"),
    "mem_ingress": ("pcie-mem-ingress-isolated", "memory-ingress"),
}


def reserve(root, mode, compiler_list):
    root = Path(root).resolve()
    provided = Path(compiler_list)
    provided = (root / provided) if not provided.is_absolute() else provided
    private = root/".tools/pcie-cross-fusesoc"
    if (not provided.resolve().is_relative_to(private)
            or provided.is_symlink() or not provided.is_file()):
        raise ValueError("expected the private FuseSoC compiler list")
    raw = provided.read_bytes()
    if not raw.strip():
        raise ValueError("empty selected FuseSoC compiler inputs")
    target, logical = MODES[mode]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True)
    if "GITHUB_RUN_ID" in os.environ and (
            dirty or os.environ.get("GITHUB_SHA") != revision
            or not os.environ.get("GITHUB_RUN_ATTEMPT")):
        raise ValueError("isolated PCIe CI requires a clean exact checkout and run attempt")
    plan = {"target": target, "logical_test": logical, "top": "test",
            "engine": "verilator", "sources": "pcie-link",
            "source_revision": revision,
            "evidence_scope": "isolated_observation_only"}
    identity = selected(target, plan, root=root, filelist_bytes=raw)
    out = reserve_run(root/".tools/runs", identity, plan=plan)
    with (out/"sources.f").open("xb") as stream:
        stream.write(raw)
    with (out/"plan.json").open("x") as stream:
        stream.write(json.dumps({**plan, "identity": identity}, indent=2)+"\n")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("compiler_list", type=Path)
    args = parser.parse_args()
    try:
        print(reserve(ROOT, args.mode, args.compiler_list).relative_to(ROOT))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
