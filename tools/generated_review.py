#!/usr/bin/env python3
"""Review tracked generator outputs with source-aware, human-readable Git diffs.

This is a read-only review helper. It does not generate RTL, select a
hardware variant, run simulation, or claim elaboration/protocol evidence.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEX_REF = re.compile(r"^[A-Za-z0-9_./^-]+$")
STRUCTURED = {".json", ".yaml", ".yml"}


def git(*args: str, root: Path = ROOT, allow_missing: bool = False) -> str | None:
    process = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if process.returncode:
        if allow_missing:
            return None
        raise ValueError(process.stderr.strip() or f"git {' '.join(args)} failed")
    return process.stdout


def classify(path: str) -> str:
    if path.startswith("gen/projects/"):
        return "Selected/review RTL variants"
    if path.startswith("gen/noc/floonoc/"):
        return "Generated FlooNoC RTL and configurations"
    if path.startswith("gen/chip/"):
        return "Generated chip RTL / firmware / manifests"
    if path.startswith("gen/supernoc/"):
        return "Generated connected fabric / testbench / monitors"
    if path.startswith("gen/diagrams/"):
        return "Generated diagrams and connectivity"
    if path.startswith("gen/verification/"):
        return "Generated verification metadata"
    if path.startswith("gen/memory/"):
        return "Generated memory fabric"
    if path.startswith("gen/boot/"):
        return "Generated boot images"
    return "Generator root metadata"


def flatten(obj, prefix: str = "") -> dict[str, object]:
    if isinstance(obj, dict):
        result = {}
        for k, v in sorted(obj.items()):
            result.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
        return result
    if isinstance(obj, list):
        # Keep list structure and ordering visible; lists are not necessarily
        # keyed sets and may contain meaningful ordered RTL connectivity.
        return {prefix: obj}
    return {prefix: obj}


def semantic_keys(before: str, after: str, limit: int = 16) -> list[str]:
    try:
        a, b = flatten(json.loads(before)), flatten(json.loads(after))
    except (ValueError, TypeError):
        return []
    keys = [key for key in sorted(a.keys() | b.keys()) if a.get(key) != b.get(key)
            or (key in a) != (key in b)]
    return keys[:limit] + ([f"... {len(keys)-limit} more changed fields"] if len(keys) > limit else [])


def review(base: str, *, root: Path = ROOT) -> dict:
    if not HEX_REF.fullmatch(base) or base.startswith("-"):
        raise ValueError("invalid comparison ref")
    # Resolve to an actual commit before using it in git diff or show.
    sha = git("rev-parse", "--verify", f"{base}^{{commit}}", root=root).strip()
    diff = git("diff", "--name-status", "--no-renames", sha, "--", "gen/", root=root)
    files = []
    for line in diff.splitlines():
        if not line.strip():
            continue
        status, path = line.split("\t", 1)
        if not path.startswith("gen/"):
            continue
        old = git("show", f"{sha}:{path}", root=root, allow_missing=True)
        p = root / path
        if p.is_symlink():
            raise ValueError(f"refusing symlink in generated files: {path}")
        new = p.read_text() if p.is_file() and p.suffix == ".json" else None
        keys = semantic_keys(old, new) if old is not None and new is not None else []
        files.append({"path": path, "change": status, "group": classify(path),
                      "changed_fields": keys})
    # Include working-tree changes, even before they are staged.
    changed = set(x["path"] for x in files)
    for status, path in [line.split("\t", 1) for line in
                         git("status", "--porcelain=v1", "--untracked-files=all", "--", "gen/", root=root).splitlines()
                         if "\t" in line]:
        if path not in changed:
            files.append({"path": path, "change": status.strip() or "M",
                          "group": classify(path), "changed_fields": []})
    files.sort(key=lambda item: (item["group"], item["path"]))
    return {"base_commit": sha, "files": files, "count": len(files)}


def markdown(data: dict) -> str:
    lines = [f"# Generated artifacts review (base {data['base_commit'][:12]})", "",
             f"{data['count']} generated paths differ from the comparison base.", ""]
    groups = sorted({item["group"] for item in data["files"]})
    if not groups:
        lines.append("No tracked generated changes.")
    for group in groups:
        lines.append(f"## {group}")
        for f in (x for x in data["files"] if x["group"] == group):
            lines.append(f"- \`{f['change']}\` \`{f['path']}\`")
            if f["changed_fields"]:
                lines.append("  - Changed JSON fields: " +
                             ", ".join(f"\`{key}\`" for key in f["changed_fields"]))
        lines.append("")
    lines += ["**Review limits:** SHA/path changes are generated-source evidence only; "
              "they do not establish an elaborated chip or a passing RTL test. "
              "Run \`make check-generated\` separately for exact byte reproducibility. "
              "Opt-in compiler-selected RTL under ignored \`.tools/\` is not in this report; "
              "issue #184 tracks promotion of such RTL into tracked \`gen/projects/\`.", ""]
    return "\n".join(lines)


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--base", default="HEAD", help="Comparison commit/branch, e.g. origin/main")
    cli.add_argument("--format", choices=("markdown", "json"), default="markdown")
    cli.add_argument("--output", type=Path, help="Optional report path; defaults to stdout")
    args = cli.parse_args()
    result = review(args.base)
    output = markdown(result) if args.format == "markdown" else json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
