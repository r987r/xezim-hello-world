#!/usr/bin/env python3
"""Compile genuine OpenPCIe RC/EP + selected verilog-pcie + FlooGen + SRAM.

Source assembly only. Existing SCN-C host, original endpoint, existing TLP
bridge and generated NoC own the behavior, simulator and PASS/FAIL. Never
substitute a behavioral AXI transaction or simulator success stub here.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'dv/pcie0'))
from prepare_rtl import prepare_bridge_source
from run_rtl_smoke import source_contract
import regress
from run_workspace import reserve_run, verify_run
from test_identity import selected


def sources() -> tuple[list[str], list[str], list[str]]:
    pin=source_contract()  # exact independent RTL/bridge commit
    resolver=regress.Resolver(regress.load_config(ROOT/'config/regression.yaml'))
    noc_files,noc_include,noc_defines=resolver.sources({'sources':'noc'})
    manifest=json.loads((ROOT/'gen/noc/floonoc/manifest.json').read_text())
    actual=manifest['networks']['pcie0_local_data']
    if actual['status']!='real_upstream_structural_RTL':
        raise RuntimeError('missing real generated PCIe0 local FlooNoC')
    generated=[str(ROOT/'gen/noc/floonoc'/actual[key]) for key in ('package','top')]
    vendor=ROOT/'.tools/verilog_pcie'
    files=list(dict.fromkeys(noc_files+generated+[
        str(ROOT/'rtl/adapters/axi_sram_target.sv'),
        str(ROOT/'dv/pcie_link/bar0_noc_translate.sv'),
        str(prepare_bridge_source()),
    ]+[str(vendor/x) for x in pin['rtl_modules'] if x!='rtl/pcie_axi_master.v']+[
        str(ROOT/'dv/pcie0/pcie_noc_tb.sv'),
        str(ROOT/'dv/pcie_link/openpcie_axis_req_to_tlp.sv'),
        str(ROOT/'dv/pcie_link/openpcie_cpl_to_axis.sv'),
    ]))
    return files,noc_include,noc_defines


def selection(sim: Path) -> tuple[list[str], list[str], list[str], int, int]:
    root = ROOT
    vc=sim/'fusesoc_pcie_phy_core_1.0.0.vc'
    if not vc.is_file():
        raise RuntimeError('first prepare the original pinned FuseSoC RTL')
    ep_files=[line for line in vc.read_text().splitlines()
              if line.startswith('src/') and not line.endswith('example/pcie_top.v')]
    if len(ep_files)<35:
        raise RuntimeError('incomplete pinned original endpoint source graph')
    noc,noc_include,noc_defines=sources()
    host=root/'.tools/pcie_host_pcievhost/verilog'
    vproc=root/'.tools/pcie_host_vproc'
    files=ep_files + [str(host/x) for x in ('lib/Serialiser.v','lib/clkmux.v',
              'pcieVHost/pcieVHostPipex1.v','pcieVHost/pcieVHost.v')]
    files.append(str(vproc/'f_VProc.v'))
    files += noc
    files += [str(root/x) for x in (
        'dv/pcie_link/pipe_x1_adapter.sv',
        'dv/pcie_link/phy_status_responder.sv',
        'dv/pcie_link/endpoint_prelink_ctrl.sv',
        'dv/pcie_link/pcie_bar0_host_cfg.sv',
    )]
    files += [str(root/'.tools/pcie_endpoint_openpcie'/x) for x in (
        'src/pcie_cfg/pcie_config_decode.sv',
        'src/pcie_cfg/pcie_config_handler.sv',
        'src/pcie_cfg/pcie_config_mux.sv',
        'src/pcie_cfg/pcie_config_reg.sv',
        'src/pcie_cfg/pcie_cfg_wrapper.sv',
    )]
    files.append(str(root/'dv/pcie_link/tb_pcie_cross_link.sv'))
    includes = ['-I'+str(p) for p in [*noc_include,host/'headers',host/'testcross_x1',vproc]]
    return files, includes, ['-D'+d for d in noc_defines], len(ep_files), len(noc)


def checkout():
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    revision = git('rev-parse', 'HEAD')
    dirty = bool(git('status', '--porcelain'))
    if os.environ.get('GITHUB_RUN_ID') and (
            dirty or revision != os.environ.get('GITHUB_SHA')
            or not os.environ.get('GITHUB_RUN_ATTEMPT')):
        raise ValueError('connected PCIe CI requires a clean exact checkout and run attempt')
    return revision, dirty


def sim_directory(path: Path):
    provided = ROOT / path
    expected = ROOT/'.tools/pcie-connected-fusesoc/fusesoc_pcie_phy_core_1.0.0/sim'
    if provided.resolve() != expected or not expected.is_dir():
        raise ValueError('expected the private connected FuseSoC simulation directory')
    return expected


def reserve(sim, raw):
    revision, dirty = checkout()
    plan = {'target': 'pcie-connected-memory', 'logical_test': 'host-to-sram-roundtrip',
            'engine': 'verilator', 'sources': 'pcie-connected-memory', 'top': 'test',
            'source_revision': revision, 'dirty': dirty,
            'evidence_scope': 'isolated_connected_memory_roundtrip',
            'compile_cwd': sim.relative_to(ROOT).as_posix()}
    identity = selected(plan['target'], plan, root=ROOT, filelist_bytes=raw)
    out = reserve_run(ROOT/'.tools/runs', identity, plan=plan)
    (out/'sources.f').write_bytes(raw)
    (out/'plan.json').write_text(json.dumps({**plan, 'identity': identity}, indent=2)+'\n')
    return out


def compile_connected(sim, out, inputs):
    files, includes, defines, endpoint_count, noc_count = inputs
    root = ROOT
    plan = json.loads((out/'plan.json').read_text())
    identity = json.loads((out/'identity.json').read_text())
    verify_run(out, identity, plan=plan)
    if (out.resolve() != out or not out.is_relative_to(root/'.tools/runs')
            or plan['identity'] != identity or plan['compile_cwd'] != sim.relative_to(ROOT).as_posix()
            or (plan['source_revision'], plan['dirty']) != checkout()):
        raise ValueError('connected PCIe compiler selection does not match run workspace')
    raw = (out/'sources.f').read_bytes()
    if (raw.decode().splitlines() != files
            or hashlib.sha256(raw).hexdigest() != identity['selection']['filelist_sha256']):
        raise ValueError('connected PCIe source list differs from the selected inputs')
    host=root/'.tools/pcie_host_pcievhost/verilog'
    obj=root/'.tools/pcie-connected-obj'/identity['run_id']
    obj.mkdir(parents=True, exist_ok=False)
    args=['verilator','--binary','--timing','-j','4','-Wno-fatal',
          '-DVPROC_SV','-DPCIE_CONNECTED_MEM','-GSIM_FORCE_FAST_LTSSM=1',
          '-GVERIFY_REAL_MEM_WRITE=1','--top-module','test',
          '--Mdir',str(obj),'--prefix','Vtop']
    args += includes + defines + raw.decode().splitlines()
    args += ['-CFLAGS','-std=c++17 -Wno-attributes','-LDFLAGS',
             f'-Wl,-E -lrt -rdynamic -Wl,-whole-archive '
             f'-L{host}/testcross_x1 -lvproc '
             f'-L{root}/.tools/pcie_host_pcievhost/lib -lpcievhost '
             '-Wl,-no-whole-archive -ldl']
    with (out/'compiler-argv.json').open('x') as receipt:
        json.dump({'argv': args, 'cwd': str(sim), 'source_sha256': identity['selection']['filelist_sha256']},
                  receipt, indent=2)
        receipt.write('\n')
    print(f'PCIE_CONNECTED_SOURCES: original_endpoint={endpoint_count} noc_bridge={noc_count}',flush=True)
    subprocess.run(args,cwd=sim,check=True)
    binary=obj/'Vtop'
    if not binary.is_file():
        raise RuntimeError('connected real RTL binary not generated')
    print(f'PCIE_CONNECTED_COMPILE_OK: {binary}',flush=True)


def main()->int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sim-dir', required=True, type=Path)
    parser.add_argument('--workspace', type=Path,
                        help='compile a previously reserved workspace; otherwise reserve it')
    options = parser.parse_args()
    sim = sim_directory(options.sim_dir)
    inputs = selection(sim)
    if options.workspace is None:
        raw = ('\n'.join(inputs[0])+'\n').encode()
        out = reserve(sim, raw)
        value = out.relative_to(ROOT).as_posix()
        if destination := os.environ.get('GITHUB_OUTPUT'):
            with Path(destination).open('a') as stream:
                stream.write(f'workspace={value}\n')
        print(value)
    else:
        compile_connected(sim, ROOT/options.workspace, inputs)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
