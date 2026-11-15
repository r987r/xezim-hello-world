#!/usr/bin/env python3
"""Compile genuine OpenPCIe RC/EP + selected verilog-pcie + FlooGen + SRAM.

Source assembly only. Existing SCN-C host, original endpoint, existing TLP
bridge and generated NoC own the behavior, simulator and PASS/FAIL. Never
substitute a behavioral AXI transaction or simulator success stub here.
"""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'dv/pcie0'))
from prepare_rtl import prepare_bridge_source
from run_rtl_smoke import source_contract
import regress


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


def main()->int:
    root=ROOT;sim=root/'build/fusesoc_pcie_phy_core_1.0.0/sim'
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
    args=['verilator','--binary','--timing','-j','4','-Wno-fatal',
          '-DVPROC_SV','-DPCIE_CONNECTED_MEM','-GSIM_FORCE_FAST_LTSSM=1',
          '-GVERIFY_REAL_MEM_WRITE=1','--top-module','test',
          '--Mdir',str(root/'.tools/pcie-connected-obj'),
          '--prefix','Vtop']
    for inc in [*noc_include,host/'headers',host/'testcross_x1',vproc]:
        args.append('-I'+str(inc))
    for define in noc_defines:
        args.append('-D'+define)
    args+=ep_files
    args += [str(host/x) for x in ('lib/Serialiser.v','lib/clkmux.v',
              'pcieVHost/pcieVHostPipex1.v','pcieVHost/pcieVHost.v')]
    args.append(str(vproc/'f_VProc.v'))
    args += noc
    args += [str(root/x) for x in (
        'dv/pcie_link/pipe_x1_adapter.sv',
        'dv/pcie_link/phy_status_responder.sv',
        'dv/pcie_link/endpoint_prelink_ctrl.sv',
        'dv/pcie_link/pcie_bar0_host_cfg.sv',
    )]
    args += [str(root/'.tools/pcie_endpoint_openpcie'/x) for x in (
        'src/pcie_cfg/pcie_config_decode.sv',
        'src/pcie_cfg/pcie_config_handler.sv',
        'src/pcie_cfg/pcie_config_mux.sv',
        'src/pcie_cfg/pcie_config_reg.sv',
        'src/pcie_cfg/pcie_cfg_wrapper.sv',
    )]
    args += [str(root/'dv/pcie_link/tb_pcie_cross_link.sv'),
             '-CFLAGS','-std=c++17 -Wno-attributes',
             '-LDFLAGS',
             f'-Wl,-E -lrt -rdynamic -Wl,-whole-archive '
             f'-L{host}/testcross_x1 -lvproc '
             f'-L{root}/.tools/pcie_host_pcievhost/lib -lpcievhost '
             '-Wl,-no-whole-archive -ldl']
    print(f'PCIE_CONNECTED_SOURCES: original_endpoint={len(ep_files)} noc_bridge={len(noc)}',flush=True)
    subprocess.run(args,cwd=sim,check=True)
    binary=root/'.tools/pcie-connected-obj/Vtop'
    if not binary.is_file():
        raise RuntimeError('connected real RTL binary not generated')
    print(f'PCIE_CONNECTED_COMPILE_OK: {binary}',flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
