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
    r"(?im)\bPR\s*#\d+\s+is\s+(?:still\s+)?(?:draft|pending|open)\b"
    r"|\bPR\s*#\d+[^\n]{0,64}\b(?:CI pending|not yet verified)\b"
)

def documents(root: Path) -> list[Path]:
    items = [root / "README.md", root / "AGENTS.md"]
    for d in ("docs", "dv", "rtl", "gen", "config"):
        sub = root / d
        if sub.is_dir():
            items.extend(sub.rglob("*.md"))
    return sorted({p.resolve() for p in items if p.is_file()})

def heading_anchors(content: str) -> set[str]:
    """Approximate GitHub Markdown heading slugs, including duplicates."""
    from html import unescape
    used: dict[str, int] = {}
    slugs = set()
    fence = None
    for line in content.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(FENCED):
            marker = stripped[0]
            fence = None if fence == marker else marker
            continue
        if fence is not None:
            continue
        match = re.match(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        heading = unescape(match.group(1))
        heading = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", heading)
        heading = re.sub(r"<[^>]+>", "", heading)
        heading = re.sub(r"[^\w\- ]", "", heading.lower()).strip()
        base = re.sub(r"\s+", "-", heading)
        if not base:
            continue
        count = used.get(base, 0)
        used[base] = count + 1
        slugs.add(base if count == 0 else f"{base}-{count}")
    return slugs


def regression_targets(root: Path) -> set[str]:
    """Read the literal test/suite keys without executing YAML or importing IP."""
    path = root / "config/regression.yaml"
    if not path.exists():
        return set()
    names = set()
    section = None
    for line in path.read_text(encoding="utf-8").splitlines():
        top = re.match(r"^(tests|suites):\s*$", line)
        if top:
            section = top.group(1)
        elif line and not line.startswith((" ", "#")):
            section = None
        elif section:
            item = re.match(r"^  ([A-Za-z][\w-]*):(?:\s|$)", line)
            if item:
                names.add(item.group(1))
    return names


def make_targets(root: Path) -> set[str]:
    path = root / "Makefile"
    if not path.exists():
        return set()
    return set(re.findall(r"^([A-Za-z][\w.-]*):", path.read_text(encoding="utf-8"), re.M))


def issues(root: Path) -> list[str]:
    root = root.resolve()
    problems = []
    targets = regression_targets(root)
    make_names = make_targets(root)
    cache: dict[Path, set[str]] = {}
    for path in documents(root):
        data = path.read_text(encoding="utf-8")
        name = path.relative_to(root).as_posix()
        if name in WATCHED and (STALE.search(data) or STALE_PR_CLAIM.search(data)):
            problems.append(f"{name}: dated progress/draft claim in guide")
        fenced = None
        shell = False
        for line_no, line in enumerate(data.splitlines(), 1):
            token = line.lstrip()
            if token.startswith(FENCED):
                char = token[0]
                if fenced is None:
                    fenced = char
                    shell = bool(re.match(r"^(?:\x60{3,}|~{3,})\s*(?:sh|bash|shell|console)\s*$", token))
                elif fenced == char:
                    fenced = None
                    shell = False
                continue
            if fenced is not None:
                if shell and not token.startswith("#") and "# doc-check: skip" not in line:
                    for match in re.finditer(r"\b(?:python3|python)\s+((?:tools|dv|tests)/[\w./-]+\.py)\b", line):
                        script = match.group(1)
                        if not (root / script).is_file():
                            problems.append(f"{name}:{line_no}: missing documented script {script}")
                    for match in re.finditer(r"\b(?:python3|python)\s+tools/regress\.py\s+([^\s;#&|]+)", line):
                        target = match.group(1)
                        if re.fullmatch(r"[A-Za-z][\w-]*", target) and targets and target not in targets:
                            problems.append(f"{name}:{line_no}: unknown regression target {target}")
                    make_match = re.search(r"(?:^|[;&|])\s*(?:[\w_]+=\S+\s+)*make\s+([^#;&|]+)", line)
                    if make_match and make_names:
                        for word in make_match.group(1).split():
                            if word.startswith("-") or "=" in word or "$" in word or not re.fullmatch(r"[\w.-]+", word):
                                continue
                            if word not in make_names:
                                problems.append(f"{name}:{line_no}: unknown make target {word}")
                continue
            for match in LINK.finditer(line):
                dest = match.group(1).strip().split(maxsplit=1)[0].strip("<>")
                if not dest:
                    continue
                uri = urlsplit(dest)
                if uri.scheme or uri.netloc or dest.startswith("/"):
                    # Validate only this repository's own workflow links, not
                    # arbitrary external GitHub/other-project URLs.
                    workflow = re.search(
                        r"https://github\.com/r987r/xezim-hello-world/actions/workflows/([\w.-]+\.ya?ml)",
                        dest,
                    )
                    if workflow and not (root / ".github/workflows" / workflow.group(1)).is_file():
                        problems.append(f"{name}:{line_no}: missing workflow {workflow.group(1)}")
                    continue
                loc = unquote(uri.path)
                target = (path.parent / loc).resolve() if loc else path
                if not target.is_relative_to(root) or not target.exists():
                    problems.append(f"{name}:{line_no}: broken local link {dest}")
                elif uri.fragment and target.suffix.lower() == ".md":
                    if target not in cache:
                        cache[target] = heading_anchors(target.read_text(encoding="utf-8"))
                    anchor = unquote(uri.fragment)
                    if anchor not in cache[target]:
                        problems.append(f"{name}:{line_no}: broken heading anchor {dest}")
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
