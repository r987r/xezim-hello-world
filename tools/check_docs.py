#!/usr/bin/env python3
"""Validate local Markdown links and keep entrypoint guides free of dated handoffs."""
from __future__ import annotations
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]+\]\(([^)]+)\)")
FENCED = ("~~~", chr(96) * 3)
WATCHED = {
    "README.md", "AGENTS.md", "docs/README.md",
    "docs/implementation-status.md", "docs/multiprotocol-integration-readiness.md",
}
STALE = re.compile(
    r"(?im)^#{1,4}[^\n]*(?:current (?:progress|status)|"
    r"merge status|milestone|handoff history)[^\n]*\b20[0-9]{2}\b"
    r"|\bdraft PR #\d+\b"
)

# Detect assertions about an open/draft PR in source-truth guides. This is
# intentionally a syntactic guard, not a live status/CI check.
STALE_PR_CLAIM = re.compile(
    r"(?im)\\bPR\\s*#\\d+\\s+is\\s+(?:still\\s+)?(?:draft|pending|open)\\b"
    r"|\\bPR\\s*#\\d+[^\\n]{0,64}\\b(?:CI pending|not yet verified)\\b"
)

def documents(root: Path) -> list[Path]:
    items = [root / "README.md", root / "AGENTS.md"]
    for d in ("docs", "dv", "rtl", "gen", "config"):
        sub = root / d
        if sub.is_dir():
            items.extend(sub.rglob("*.md"))
    return sorted({p.resolve() for p in items if p.is_file()})

def issues(root: Path) -> list[str]:
    root = root.resolve()
    problems = []
    for path in documents(root):
        data = path.read_text(encoding="utf-8")
        name = path.relative_to(root).as_posix()
        if name in WATCHED and (STALE.search(data) or STALE_PR_CLAIM.search(data)):
            problems.append(f"{name}: dated progress/draft claim in guide")
        fenced = None
        for line_no, line in enumerate(data.splitlines(), 1):
            token = line.lstrip()
            if token.startswith(FENCED):
                char = token[0]
                if fenced is None:
                    fenced = char
                elif fenced == char:
                    fenced = None
                continue
            if fenced is not None:
                continue
            for match in LINK.finditer(line):
                dest = match.group(1).strip().split(maxsplit=1)[0].strip("<>")
                if not dest or dest.startswith("#"):
                    continue
                uri = urlsplit(dest)
                if uri.scheme or uri.netloc or dest.startswith("/"):
                    continue
                loc = unquote(uri.path)
                if not loc:
                    continue
                target = (path.parent / loc).resolve()
                if not target.is_relative_to(root) or not target.exists():
                    problems.append(f"{name}:{line_no}: broken local link {dest}")
    readme = root / "README.md"
    if readme.exists():
        content = readme.read_text(encoding="utf-8")
        for marker in ("<!-- BEGIN GENERATED SOC -->", "<!-- END GENERATED SOC -->"):
            if content.count(marker) != 1:
                problems.append(f"README.md: expected one {marker}")
    return problems

def main() -> int:
    problems = issues(ROOT)
    if problems:
        for error in problems:
            print("DOC ERROR:", error, file=sys.stderr)
        return 1
    print(f"PASS: {len(documents(ROOT))} Markdown documents, local links and entrypoints")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
