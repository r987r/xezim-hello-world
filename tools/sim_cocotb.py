#!/usr/bin/env python3
"""Small cocotb adapter for the resolved regression plan (not a test list)."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from xml.etree import ElementTree


def build_fingerprint(plan):
    # Include headers and simulator/options, not just the top file or mtime.
    digest = hashlib.sha256()
    digest.update(json.dumps([plan['sources'], plan['includes'], plan['defines'],
                              plan['top'], ['--timing', '--assert', '-Wno-fatal']]).encode())
    sim = shutil.which('verilator')
    if not sim:
        raise ValueError('verilator missing from PATH')
    digest.update(subprocess.check_output([sim, '--version']))
    headers = {p for directory in plan['includes'] for p in Path(directory).rglob('*')
               if p.is_file() and p.suffix in {'.svh', '.vh'}}
    for path in [*map(Path, plan['sources']), *sorted(headers)]:
        digest.update(str(path).encode())
        digest.update(path.read_bytes())
    import cocotb
    digest.update(cocotb.__version__.encode())
    return digest.hexdigest()


def main(plan_file):
    from cocotb.runner import get_runner
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    plan = json.loads(Path(plan_file).read_text())
    result_dir = Path(plan['results_xml']).parent
    runner = get_runner('verilator')
    build = root/plan['build']
    stamp = build/'regression-build.json'
    signature = build_fingerprint(plan)
    if plan.get('reuse_build') or plan['stage'] == 'run':
        state = json.loads(stamp.read_text()) if stamp.is_file() else {}
        if state.get('signature') != signature or not (build/plan['top']).is_file():
            raise ValueError('missing/stale build; run the positive build target first')
        if hashlib.sha256((build/plan['top']).read_bytes()).hexdigest() != state.get('binary_sha256'):
            raise ValueError('built executable changed; rebuild the positive target')
        runner.build_dir = build
    else:
        stamp.unlink(missing_ok=True)
        defines = dict(d.split('=', 1) if '=' in d else (d, '1') for d in plan['defines'])
        runner.build(sources=plan['sources'], includes=plan['includes'], defines=defines,
                     build_args=['--timing', '--assert', '-Wno-fatal'],
                     hdl_toplevel=plan['top'], build_dir=build, always=True, waves=False,
                     log_file=result_dir/'build.log')
        stamp.write_text(json.dumps({'signature': signature, 'binary_sha256':
                                     hashlib.sha256((build/plan['top']).read_bytes()).hexdigest()}) + '\n')
    if plan['stage'] == 'build':
        return
    results = Path(plan['results_xml'])
    results.unlink(missing_ok=True)
    returned = runner.test(hdl_toplevel=plan['top'], hdl_toplevel_lang='verilog',
                          test_module=plan['module'], test_dir=root/plan['test_dir'],
                          results_xml=str(results), test_args=plan['args'],
                          seed=plan.get('seed', 1),
                          log_file=result_dir/'simulation.log')
    tests = ElementTree.parse(returned).findall('.//testcase')
    if not tests or any(any(t.find(tag) is not None for tag in ('failure', 'error', 'skipped')) for t in tests):
        raise SystemExit('cocotb regression failed; see results XML')


if __name__ == '__main__':
    main(sys.argv[1])
