#!/usr/bin/env python3
"""Test-independent hardware build view derived from the existing regression YAML.

Compiler-input hashing proves *selected source* identity, never elaboration or
accepted AXI/TLP/GMII/DFI activity. This is NOT another authored variant list.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import yaml
from test_identity import config_target
from selected_rtl_provenance import verify_selected_archive

ROOT = Path(__file__).resolve().parents[1]
CHIP_TOPS = frozenset(("full_chip_tb", "full_chip_dma_tb"))


def catalog(root: Path, tests: dict, require_resolved: bool = False) -> dict:
    root = Path(root).resolve()
    soc = yaml.safe_load((root / "config/soc.yaml").read_text())
    if not isinstance(tests, dict) or not isinstance(soc.get("name"), str):
        raise ValueError("invalid SoC/test catalog")
    variants = {}
    for profile, test in sorted(tests.items()):
        if test.get("top") not in CHIP_TOPS:
            continue
        name = config_target(test)
        obj = variants.setdefault(name, {
            "name": name, "project": soc["name"],
            "firmware_mode": test.get("firmware_mode"),
            "source_target": test["sources"],
            "profiles": [], "verified_profiles": [],
            "selected_soc_top_sha256": None,
        })
        if (obj["firmware_mode"] != test.get("firmware_mode")
                or obj["source_target"] != test["sources"]):
            raise ValueError(name + ": incompatible selections use one hardware variant")
        obj["profiles"].append(profile)
        archive = root / ".tools/regression" / profile / "selected-rtl-manifest.json"
        if archive.is_symlink():
            raise ValueError(profile + ": selected archive symlink is forbidden")
        if not archive.is_file():
            if require_resolved:
                raise ValueError(profile + ": missing selected RTL archive")
            continue
        verified = verify_selected_archive(root, profile, test)
        path = verified.get("selected_soc_top")
        if not path or path not in verified.get("source_sha256", {}):
            raise ValueError(profile + ": selected source closure has no actual SoC top")
        digest = verified["source_sha256"][path]
        if obj["selected_soc_top_sha256"] and obj["selected_soc_top_sha256"] != digest:
            raise ValueError(name + ": tests select different RTL tops; split variants")
        obj["selected_soc_top_sha256"] = digest
        obj["verified_profiles"].append(profile)
    for record in variants.values():
        total, done = len(record["profiles"]), len(record["verified_profiles"])
        record["status"] = ("source_verified_not_elaborated" if done == total
                            else "partially_resolved" if done
                            else "declared_only_not_compiled")
    return {
        "schema_version": 1, "project": soc["name"],
        "source": "config/regression.yaml",
        "evidence": "build_selection_and_RTL_hash_only_not_protocol_acceptance",
        "variants": [variants[k] for k in sorted(variants)],
    }


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root", type=Path, default=ROOT)
    cli.add_argument("--config", type=Path, default=ROOT / "config/regression.yaml")
    cli.add_argument("--out", type=Path, required=True)
    cli.add_argument("--require-resolved", action="store_true")
    args = cli.parse_args()
    tests = yaml.safe_load(args.config.read_text())["tests"]
    result = catalog(args.root, tests, args.require_resolved)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"HARDWARE VARIANTS: {len(result['variants'])} (source only, no RTL PASS)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
