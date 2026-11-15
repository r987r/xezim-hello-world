#!/usr/bin/env python3
"""Execute an exact repository-owned debug recipe and preserve truthful evidence.

Exploratory debug only: nonzero child exit stays nonzero, and zero exit never
becomes a qualified RTL PASS. Canonical regression/CI own actual qualification.
No shell dispatch, arbitrary CLI commands, fabricated seeds or test summaries.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def load_profiles(config: Path) -> dict:
    import yaml

    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("unsupported debug recipe schema")
    profiles = data.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("missing debug profiles")
    for name, profile in profiles.items():
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", str(name)):
            raise ValueError("invalid debug profile name")
        if not isinstance(profile, dict):
            raise ValueError(f"{name}: profile must be a mapping")
        command = profile.get("command")
        if (not isinstance(command, list) or not command
                or any(not isinstance(x, str) or not x.strip() for x in command)):
            raise ValueError(f"{name}: command must be nonempty argv strings")
        if any("\x00" in x or "\n" in x for x in command):
            raise ValueError(f"{name}: command contains invalid characters")
        timeout = profile.get("timeout_s")
        if type(timeout) is not int or not 1 <= timeout <= 3600:
            raise ValueError(f"{name}: invalid timeout_s")
        if (not isinstance(profile.get("tool_versions", []), list)
                or any(x not in ("python3", "verilator", "iverilog", "xezim")
                       for x in profile.get("tool_versions", []))):
            raise ValueError(f"{name}: unsupported tool version probe")
    return profiles


def probe_version(tool: str) -> str:
    try:
        p = subprocess.run([tool, "--version"], cwd=ROOT, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=10, check=False)
        return (p.stdout or "").splitlines()[0][:300] if p.returncode == 0 else (
            f"unavailable (exit {p.returncode})")
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"


def git_output(*args: str) -> str | None:
    try:
        p = subprocess.run(["git", *args], cwd=ROOT, text=True, timeout=10,
                           capture_output=True, check=False)
        return p.stdout.strip() if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def safe_output_dir(root: Path, requested: Path) -> Path:
    path = (ROOT / requested).resolve() if not requested.is_absolute() else requested.resolve()
    if path == ROOT or not path.is_relative_to(root.resolve()):
        raise ValueError("debug evidence must be under .tools/debug-runs/")
    return path


def run_profile(name: str, profile: dict, out: Path, *, allow_dirty: bool = False) -> int:
    dirty = git_output("status", "--porcelain", "--untracked-files=no")
    if dirty is None:
        raise ValueError("git status unavailable: cannot capture source provenance")
    if dirty and not allow_dirty:
        raise ValueError("tracked source is dirty: pass --allow-dirty for exploratory A/B")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.mkdir(exist_ok=False)  # immutable per-run record
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    evidence = {
        "schema_version": 1, "qualification": "exploratory_only",
        "profile": name, "command": profile["command"], "cwd": str(ROOT),
        "git_sha": git_output("rev-parse", "HEAD"),
        "git_branch": git_output("branch", "--show-current"),
        "tracked_tree_dirty": bool(dirty),
        "started_at_utc": started,
        "tool_versions": {tool: probe_version(tool)
                          for tool in profile.get("tool_versions", [])},
        "timeout_s": profile["timeout_s"],
        "seed": os.getenv("SEED"),  # record only; never invent a seed
        "exit_code": None,
        "timed_out": False,
    }
    began = time.monotonic()
    try:
        with (out / "stdout-stderr.log").open("w", encoding="utf-8") as log:
            # Start a fresh POSIX process group: on timeout, killing only the
            # simulator launcher can leave compilers, workers or a VM running.
            child = subprocess.Popen(
                profile["command"], cwd=ROOT, stdout=log,
                stderr=subprocess.STDOUT, start_new_session=True,
            )
            try:
                evidence["exit_code"] = child.wait(timeout=profile["timeout_s"])
            except subprocess.TimeoutExpired:
                evidence["timed_out"] = True
                evidence["exit_code"] = 124
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
    except OSError as exc:
        evidence["exit_code"] = 127
        (out / "launch-error.txt").write_text(str(exc) + "\n")
    finally:
        evidence["elapsed_s"] = round(time.monotonic() - began, 3)
        evidence["finished_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        (out / "run.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    return int(evidence["exit_code"])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile")
    p.add_argument("--out", type=Path)
    p.add_argument("--allow-dirty", action="store_true")
    p.add_argument("--audit", action="store_true",
                   help="validate recipe schema without running commands")
    args = p.parse_args()
    try:
        # CLI executes only checked-in repository recipes, never an arbitrary
        # replacement YAML file supplied on the command line.
        profiles = load_profiles(ROOT / "config/debug.yaml")
        if args.audit:
            print("PASS: validated debug recipes:", ", ".join(sorted(profiles)))
            return 0
        if not args.profile or not args.out:
            p.error("--profile and --out are required unless --audit")
        if args.profile not in profiles:
            raise ValueError("unknown profile: " + args.profile)
        out = safe_output_dir(ROOT / ".tools/debug-runs", args.out)
        result = run_profile(args.profile, profiles[args.profile], out,
                             allow_dirty=args.allow_dirty)
    except (ValueError, OSError) as exc:
        p.exit(2, f"FAIL: debug evidence: {exc}\n")
    print(f"DEBUG: {args.profile} exit={result}; evidence={out}; not a qualification gate")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
