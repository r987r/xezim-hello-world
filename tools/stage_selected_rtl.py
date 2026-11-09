#!/usr/bin/env python3
"""Stage selected generated RTL for code review without claiming it is in gen/.

This is a fail-closed intermediate step for #184. Sources must originate in
the existing exact selected regression archive. No second variant generator,
source inventory, or authority is created. The staged copy is NOT promoted to
generator-owned gen/ until deterministic regeneration is independently proven.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

import yaml

from selected_rtl_provenance import verify_selected_archive
from test_identity import config_target

ROOT = Path(__file__).resolve().parents[1]
PROFILE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
HEXDIGEST = re.compile(r"[a-f0-9]{64}\Z")
TOPS = {"full_chip_tb", "full_chip_dma_tb"}


class PromotionError(ValueError):
    pass


def _hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _manifest_hash(value: dict) -> str:
    """Canonical self-integrity field, not an external signer or hardware proof."""
    canonical = {k: v for k, v in value.items() if k != "manifest_sha256"}
    return _hash(json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8"))


def _path_in(root: Path, raw: str) -> Path:
    if not isinstance(raw, str) or not raw or Path(raw).is_absolute():
        raise PromotionError("promotion path must be a nonempty checkout-relative path")
    source = root / raw
    if source.is_symlink():
        raise PromotionError("symlink source is not allowed")
    resolved = source.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise PromotionError("missing/foreign source in selected closure: " + raw)
    return resolved


def stage(root: Path, profile: str, definition: dict,
          out_root: Path, *, replace: bool = False) -> dict:
    """Stage a byte-exact copy under .tools, never under generator-owned gen/.

    A source digest plus selected source inventory identify the build, not the
    test's stimulus/seed. Multiple tests claiming one named hardware variant
    may only share it if the selected top and source closure hashes match.
    """
    root = root.resolve()
    if not PROFILE.fullmatch(profile) or definition.get("top") not in TOPS:
        raise PromotionError("requires a selected full-chip test profile")
    source_manifest = verify_selected_archive(root, profile, definition)
    source_root = root / source_manifest["archive"]
    selected = source_manifest.get("selected_soc_top")
    if (not isinstance(selected, str)
            or selected not in source_manifest["generated_sha256"]
            or selected not in source_manifest["source_sha256"]):
        raise PromotionError("selected generated SoC top not present in attested closure")
    top = _path_in(root, selected)
    top_sha = _hash(top.read_bytes())
    if top_sha != source_manifest["generated_sha256"][selected]:
        raise PromotionError("selected generated top changed since attestation")
    if not HEXDIGEST.fullmatch(top_sha):
        raise PromotionError("invalid top digest")
    project_path = _path_in(root, "config/soc.yaml")
    project = yaml.safe_load(project_path.read_text())["name"]
    if not isinstance(project, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", project):
        raise PromotionError("unsupported project identifier")
    variant = config_target(definition)
    out_root = out_root.resolve()
    if not out_root.is_relative_to(root) or out_root == root / "gen":
        raise PromotionError("review stage must be inside checkout, outside generator gen/")
    if out_root.is_relative_to(root / "gen"):
        raise PromotionError("review stage cannot change generator-owned gen/")
    stage_path = out_root / project / variant
    if stage_path.is_symlink():
        raise PromotionError("unsafe review stage symlink")
    if stage_path.exists() and not replace:
        raise PromotionError("review stage already exists (explicit --replace needed)")

    files: dict[str, tuple[str, bytes]] = {}
    for source, digest in sorted(source_manifest["generated_sha256"].items()):
        original = _path_in(root, source)
        archived = _path_in(root, str(source_root.relative_to(root) / source))
        raw = original.read_bytes()
        if (not isinstance(digest, str) or not HEXDIGEST.fullmatch(digest)
                or _hash(raw) != digest or archived.read_bytes() != raw):
            raise PromotionError("selected/archived generated file differs: " + source)
        # Keep exact original selected paths under snapshot/ to make source
        # diffs unambiguous; don't flatten two similarly named generated RTL.
        files["snapshot/" + source] = (source, raw)
    filelist = (root / ".tools/regression" / profile / "sources.f").read_bytes()
    files["compiler/sources.f"] = (
        ".tools/regression/" + profile + "/sources.f", filelist)
    missing = [p for p in ("snapshot/" + selected, "compiler/sources.f")
               if p not in files]
    if missing:
        raise PromotionError("missing selected RTL top/filelist in staged archive")
    source_digest = source_manifest["compiler_input_sha256"]
    if not isinstance(source_digest, str) or not HEXDIGEST.fullmatch(source_digest):
        raise PromotionError("invalid selected source fingerprint")
    content = {
        "schema_version": 1,
        "project": project,
        "hardware_variant": variant,
        "selected_top": selected,
        "selected_top_sha256": top_sha,
        "compiler_input_sha256": source_digest,
        "compiled_top": source_manifest["compiled_top"],
        "source_profile": profile,
        "source_manifest_sha256": source_manifest["manifest_sha256"],
        "sources_sha256": source_manifest["source_sha256"],
        "include_headers_sha256": source_manifest["include_headers_sha256"],
        "filelist_sha256": source_manifest["filelist_sha256"],
        "files": {key: {"original": original, "sha256": _hash(data)}
                  for key, (original, data) in sorted(files.items())},
        "evidence": "review_staging_only_not_generator_owned_or_elaborated",
        "generator_reproducible": False,
        "bit_connectivity_proven": False,
        "protocol_traffic_observed": False,
    }
    content["manifest_sha256"] = _manifest_hash(content)
    if stage_path.exists() and replace:
        # Explicit replace cannot mask a previously corrupted or foreign stage.
        existing = verify_stage(stage_path)
        if (existing.get("hardware_variant") != variant
                or existing.get("project") != project):
            raise PromotionError("cannot replace foreign stage")
    out_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".stage-", dir=out_root))
    try:
        for relative, (_, data) in files.items():
            dest = temporary / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        (temporary / "manifest.json").write_text(
            json.dumps(content, indent=2, sort_keys=True) + "\n")
        if stage_path.exists():
            shutil.rmtree(stage_path)
        stage_path.parent.mkdir(parents=True, exist_ok=True)
        temporary.rename(stage_path)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return content


def verify_stage(folder: Path) -> dict:
    folder = folder.resolve()
    manifest_path = folder / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise PromotionError("staged manifest unavailable")
    obj = json.loads(manifest_path.read_text())
    if obj.get("schema_version") != 1 or obj.get("generator_reproducible") is not False:
        raise PromotionError("review stage illegally promoted to generated")
    signature = obj.get("manifest_sha256")
    if (not isinstance(signature, str) or not HEXDIGEST.fullmatch(signature)
            or _manifest_hash(obj) != signature):
        raise PromotionError("staged manifest metadata SHA mismatch")
    files = obj.get("files")
    if not isinstance(files, dict) or not files:
        raise PromotionError("empty staged file inventory")
    for rel, entry in files.items():
        if (not isinstance(rel, str) or not rel.startswith(("snapshot/", "compiler/"))
                or ".." in Path(rel).parts or not isinstance(entry, dict)):
            raise PromotionError("unsafe staged file inventory")
        source = folder / rel
        if source.is_symlink() or not source.is_file():
            raise PromotionError("missing/unsafe staged file: " + rel)
        if _hash(source.read_bytes()) != entry.get("sha256"):
            raise PromotionError("staged artifact changed: " + rel)
    top = obj.get("selected_top")
    if ("snapshot/" + str(top) not in files
            or files["snapshot/" + str(top)]["sha256"] != obj.get("selected_top_sha256")):
        raise PromotionError("selected top is not an inventoried original")
    compiler = files.get("compiler/sources.f")
    if (not isinstance(compiler, dict)
            or compiler.get("sha256") != obj.get("filelist_sha256")):
        raise PromotionError("staged compiler source list digest mismatch")
    if (not isinstance(obj.get("sources_sha256"), dict)
            or obj["sources_sha256"].get(top) != obj.get("selected_top_sha256")):
        raise PromotionError("staged top does not match original source selection")
    return obj


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root", type=Path, default=ROOT)
    cli.add_argument("--profile", required=True)
    cli.add_argument("--out", type=Path, default=ROOT / ".tools/rtl-review-staging")
    cli.add_argument("--replace", action="store_true")
    args = cli.parse_args()
    root = args.root.resolve()
    data = yaml.safe_load((root / "config/regression.yaml").read_text())
    test = data["tests"][args.profile]
    review = stage(root, args.profile, test, args.out, replace=args.replace)
    folder = args.out.resolve() / review["project"] / review["hardware_variant"]
    verify_stage(folder)
    print(json.dumps({"stage": str(folder), "top": review["selected_top"],
                      "sha256": review["selected_top_sha256"],
                      "generator_reproducible": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
