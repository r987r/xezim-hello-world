#!/usr/bin/env python3
"""Prepare a copy of pinned SERV RTL compatible with Xezim 0.11.3.

Xezim 0.11.3 incorrectly lowers a non-zero-lower-bound packed part-select
when it is passed *directly* to a like-indexed module input port.
See dv/simulator/port_slice_repro.sv for an isolated differential test.

Avoid modifying .tools/serv (the exact pinned upstream checkout). The two
wiring changes are valid IEEE SystemVerilog and pass both Xezim and Icarus.
"""
from __future__ import annotations

from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]


class ServPatchError(ValueError):
    pass


def patch_serv_top(source: str) -> str:
    """Replace two port part-select expressions with explicitly indexed nets.

    This is not a substitute for validating the upstream revision: fail closed
    if its source changes, so we never silently apply a patch to the wrong RTL.
    """
    edits = (
        (".i_wb_rdt           (i_wb_rdt[31:2])",
         ".i_wb_rdt           (decode_instr_indexed)",
         "   serv_decode",
         "   // Simulator compatibility: preserve [31:2] indexing at port boundary.\n"
         "   wire [31:2] decode_instr_indexed = i_wb_rdt[31:2];\n\n"),
        (".i_wb_rdt     (i_wb_rdt[31:7])",
         ".i_wb_rdt     (imm_instr_indexed)",
         "   serv_immdec",
         "   // Simulator compatibility: preserve [31:7] indexing at port boundary.\n"
         "   wire [31:7] imm_instr_indexed = i_wb_rdt[31:7];\n\n"),
    )
    for old, new, marker, declaration in edits:
        if source.count(old) != 1 or source.count(marker) != 1:
            raise ServPatchError(f"unexpected pinned SERV source; failed to match {old!r}")
        source = source.replace(old, new, 1).replace(marker, declaration + marker, 1)
    return source


def sources(root: Path = ROOT) -> list[str]:
    lock = yaml.safe_load((root / "config" / "ip.lock.yaml").read_text())
    modules = lock["third_party"]["serv"]["modules"]
    if modules.count("rtl/serv_top.v") != 1:
        raise ServPatchError("expected exactly one serv_top.v in locked source list")
    original = root / ".tools" / "serv" / "rtl" / "serv_top.v"
    if not original.is_file():
        raise ServPatchError("pinned SERV sources missing; run tools/ip_fetch.py serv first")
    patched = patch_serv_top(original.read_text())
    target = root / ".tools" / "compat" / "serv_top.v"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or target.read_text() != patched:
        target.write_text(patched)
    return [str(target if mod == "rtl/serv_top.v" else root / ".tools" / "serv" / mod)
            for mod in modules]


def main():
    try:
        print("\n".join(sources()))
    except (OSError, ServPatchError) as exc:
        print(f"SERV compatibility preparation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
