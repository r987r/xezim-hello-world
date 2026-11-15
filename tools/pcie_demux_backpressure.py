#!/usr/bin/env python3
"""Source-pinned original OpenPCIe demux and real axis_register backpressure test.

Reuse the selected IP overlay, never replace the DUT or scoreboard with mocks.
Record independent seeded PASS and original-pinned negative failure evidence.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import secrets
import subprocess

from pcie_link import ROOT, selection

PKG = 'src/packages/pcie_datalink_pkg.sv'
AXIS = 'src/verilog-axis/rtl/axis_register.v'
DEMUX = 'src/dllp/axis_user_demux.sv'
TB = ROOT / 'dv/pcie_link/axis_demux_backpressure_tb.sv'
PINNED_BLOB = 'b2a79a9bd71f00100fae5d8087f357cf708097b4'
ORIGINAL_WITNESS_SEED = 428173


def command(args: list[str], *, log: Path, timeout_s: int = 150) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(args, cwd=ROOT, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, timeout=timeout_s,
                                check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f'timed out: {args[0]}') from exc
    log.write_text(result.stdout)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--checkout', type=Path,
                    default=ROOT/'.tools/pcie_endpoint_openpcie')
    ap.add_argument('--out', type=Path,
                    default=ROOT/'.tools/pcie-link/demux-backpressure')
    ap.add_argument('--seed', type=int, action='append', default=[],
                    help='repeatable seed override; default uses fresh random seeds')
    opts = ap.parse_args()
    sel = selection(ROOT)
    expected_sha = sel['providers']['endpoint']['commit']
    checkout = opts.checkout.resolve()
    out = opts.out.resolve()
    if not checkout.is_dir() or not TB.is_file():
        ap.error('source checkout / checked-in testbench missing')
    if command(['git','-C',str(checkout),'rev-parse','HEAD'],
               log=out.parent...[truncated]