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
               log=out.parent/'demux-pin-check.log' if out.parent.is_dir() else Path('/tmp/demux-pin-check.log')).stdout.strip() != expected_sha:
        ap.error('OpenPCIe checkout is not selected pinned provider')
    original_blob = subprocess.run(['git','-C',str(checkout),'rev-parse',f'HEAD:{DEMUX}'],
                                   capture_output=True,text=True,check=True).stdout.strip()
    if original_blob != PINNED_BLOB:
        ap.error('upstream demux blob drift; re-review test and fix')
    # Prevent an accidental test against pristine, unpatched RTL.
    source = (checkout/DEMUX).read_text()
    if ('s_axis_tready = dllp_ready;' not in source or
        's_axis_tready = tlp_ready;' not in source or
        'if (s_axis_tready && !s_axis_tlast) next_state = ST_DLLP;' not in source):
        ap.error('selected provider does not contain reviewed input-ready fix')
    out.mkdir(parents=True,exist_ok=True)
    original = subprocess.run(['git','-C',str(checkout),'show',f'HEAD:{DEMUX}'],
                              text=True,capture_output=True,check=True).stdout
    original_file = out/'axis_user_demux_original.sv'
    original_file.write_text(original)

    def compile_dut(demux:Path, label:str) -> Path:
        build = out/(label+'-build')
        c = ['verilator','--binary','--timing','-Wno-fatal',
             '--top-module','axis_demux_backpressure_tb','--Mdir',str(build),
             str(checkout/PKG),str(checkout/AXIS),str(demux),str(TB)]
        p = command(c,log=out/(label+'-compile.log'))
        if p.returncode:
            raise RuntimeError(f'{label} original-RTL compile failed: {p.returncode}')
        return build/'Vaxis_demux_backpressure_tb'

    # A known failure witness proves that the checker detects the inherited
    # upstream loss. This negative is distinct from randomized positive seeds.
    broken = compile_dut(original_file,'upstream-negative')
    negative = command([str(broken),f'+SEED={ORIGINAL_WITNESS_SEED}'],
                       log=out/'upstream-negative.log',timeout_s=40)
    if negative.returncode==0 or not any(x in negative.stdout for x in ('DLLP mismatch','TLP mismatch')):
        raise RuntimeError('negative original upstream demux did not fail expected scoreboard')
    print(f'EXPECTED_FAIL: original pinned upstream demux seed={ORIGINAL_WITNESS_SEED}')
    fixed = compile_dut(checkout/DEMUX,'selected-positive')
    seeds = opts.seed or [secrets.randbits(31) for _ in range(3)]
    if any(not 1<=seed<=0x7fffffff for seed in seeds):
        ap.error('seeds must be positive 31-bit integers')
    for index,seed in enumerate(seeds):
        p=command([str(fixed),f'+SEED={seed}'],
                  log=out/f'selected-seed-{index}.log',timeout_s=40)
        if p.returncode or f'PASS: AXIS_DEMUX_RANDOM_BACKPRESSURE seed={seed} ' not in p.stdout:
            raise RuntimeError(f'selected demux scoreboard FAIL seed={seed}: exit {p.returncode}')
        print(next(line for line in p.stdout.splitlines()
                   if 'PASS: AXIS_DEMUX_RANDOM_BACKPRESSURE' in line))
    print('PASS: selected OpenPCIe real RTL skid-buffer backpressure regression')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
