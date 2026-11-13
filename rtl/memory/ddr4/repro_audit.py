#!/usr/bin/env python3
"""Compare two independently generated pinned LiteDRAM RTL outputs.

Report changed bytes/files faithfully; this is diagnostic only by default.
It is never evidence of equivalent compiled DDR RTL or real PHY behavior.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path


class RepeatabilityError(ValueError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot(folder: Path) -> dict:
    if not folder.is_dir() or folder.is_symlink():
        raise RepeatabilityError("missing or symlink DDR source folder")
    manifest = folder / "ddr4_manifest.json"
    if not manifest.is_file() or manifest.is_symlink():
        raise RepeatabilityError("missing original generator manifest")
    record = json.loads(manifest.read_text())
    if (not isinstance(record, dict) or record.get("top") != "soc_ddr4_sim"
            or record.get("status") != "generated-not-simulated"):
        raise RepeatabilityError("unexpected generated LiteDRAM manifest identity")
    expected = record.get("files_sha256")
    if not isinstance(expected, dict) or "gateware/soc_ddr4_sim.v" not in expected:
        raise RepeatabilityError("missing required Verilog source inventory")
    inventory = {}
    for relative, digest in expected.items():
        name = Path(relative)
        if (name.is_absolute() or ".." in name.parts or not relative
                or not isinstance(digest, str) or len(digest) != 64):
            raise RepeatabilityError("invalid generator source path/hash")
        path = folder / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
            raise RepeatabilityError("generated source missing or external: " + relative)
        actual = sha(path.read_bytes())
        if digest != actual:
            raise RepeatabilityError("tampered generator source: " + relative)
        inventory[relative] = actual
    actual_names = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    if actual_names - (set(inventory) | {"ddr4_manifest.json"}):
        raise RepeatabilityError("untracked generated files")
    return {"manifest": record, "files": inventory}


def compare(left: Path, right: Path, *, max_lines: int = 16) -> dict:
    if left.resolve() == right.resolve():
        raise RepeatabilityError("two independent DDR builds required")
    a, b = snapshot(left), snapshot(right)
    core = "gateware/soc_ddr4_sim.v"
    changed = sorted(p for p in a["files"].keys() | b["files"].keys()
                     if a["files"].get(p) != b["files"].get(p))
    if (a["manifest"].get("config") != b["manifest"].get("config")
            or a["manifest"].get("source") != b["manifest"].get("source")
            or a["manifest"].get("ports") != b["manifest"].get("ports")):
        raise RepeatabilityError("source, pinned configuration or port contract changed")
    first = (left / core).read_text(errors="replace").splitlines()
    second = (right / core).read_text(errors="replace").splitlines()
    # Only short bounded source lines; hashing full file is authoritative.
    diff = list(difflib.unified_diff(first, second, fromfile="first", tofile="second", n=1))
    return {
        "schema_version": 1, "generator": "pinned_litedram_behavioral_model",
        "first_core_sha256": a["files"][core],
        "second_core_sha256": b["files"][core],
        "repeatable": not changed,
        "rtl_byte_repeatable": a["files"][core] == b["files"][core],
        "changed_generated_paths": changed,
        "changed_count": len(changed),
        "diff_sample": diff[:max_lines],
        "diff_sample_truncated": len(diff) > max_lines,
        "qualification": "source_repeatability_diagnostic_not_equivalence_or_ddr_traffic",
    }


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--first", type=Path, required=True)
    cli.add_argument("--second", type=Path, required=True)
    cli.add_argument("--out", type=Path, required=True)
    cli.add_argument("--require-equal", action="store_true",
                     help="fail until all generator outputs are byte-identical")
    cli.add_argument("--require-rtl-equal", action="store_true",
                     help="fail when the generated Verilog differs, even if collateral is noisy")
    args = cli.parse_args()
    result = compare(args.first, args.second)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if args.require_rtl_equal and not result["rtl_byte_repeatable"]:
        raise RepeatabilityError("generated DDR compiled Verilog still differs between independent builds")
    if not result["repeatable"]:
        print("DDR OUTPUT DRIFT (NOT QUALIFIED): " + ", ".join(result["changed_generated_paths"]))
        if args.require_equal:
            raise RepeatabilityError("generated DDR source is not byte-reproducible")
    else:
        print("PASS DDR generator byte-identical repeatability (not functional simulation)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
