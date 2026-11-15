#!/usr/bin/env python3
"""Check original RC readback against actual endpoint/FlooNoC/SRAM signals.

Parser of source-qualified passive logs, NOT a decoder, bus driver, or
replacement scoreboard. Original RTL/SCN-C checks must pass independently.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys

if __package__:
    from .pcie_bar0_evidence import check as bar_check
else:
    from pcie_bar0_evidence import check as bar_check

PATTERNS={
 'host_mwr':r'PCIE_RC_BAR_MWR_TX: action=write_bar0 addr=([0-9a-f]{8}) data=([0-9a-f]{8}) plan=([0-9a-f]{64})',
 'mem_bytes':r'PCIE_CONNECTED_SRAM_DATA_OK: addr=([0-9a-f]{16}) data=([0-9a-f]{16}) strb=([0-9a-f]{2})',
 'mem_write':r'PCIE_CONNECTED_SRAM_WRITE: actual_host_mwr=1 real_bridge=1 generated_noc=1 real_sram_write=1 addr=([0-9a-f]{16}) beats=([0-9]+)',
 'host_mrd':r'PCIE_RC_BAR_MRD_TX: action=write_bar0 addr=([0-9a-f]{8}) tag=([0-9]+)',
 'mem_read':r'PCIE_CONNECTED_SRAM_READ: real_sram_read=1 addr=([0-9a-f]{16})',
 'ep_cpl':r'PCIE_CONNECTED_EP_TX_CPLD: returned_completion=1 from_actual_sram=1',
 'host_cpl':r'PCIE_RC_BAR_MRD_RX: tag=([0-9]+) status=([0-9]+) bytes=([0-9]+) data=([0-9a-f]{8})',
 'host_pass':r'PCIE_RC_BAR_MRD_CPLD_PASS: addr=([0-9a-f]{8}) data=([0-9a-f]{8}) same_real_host=1',
 'driver_done':r'PCIE_SCN_DRIVER: plan=([0-9a-f]{64}) action=write_bar0 stage=driver_done',
}
PATTERNS={name:re.compile(pattern) for name,pattern in PATTERNS.items()}
ORDER=tuple(PATTERNS)


def check(transcript:str)->dict:
    lines=[line.strip() for line in transcript.splitlines()]
    bar=bar_check(transcript)
    marks={name:[(i,m.groups()) for i,line in enumerate(lines)
                 if (m:=regex.fullmatch(line))]
           for name,regex in PATTERNS.items()}
    errors=[]
    if not bar['qualified_over_link_bar0']:
        errors.append('original independent host BAR0 config/completions invalid')
    for name,occurrences in marks.items():
        if len(occurrences)!=1:
            errors.append(f'{name}: require exactly one original observed event, got {len(occurrences)}')
    if all(len(x)==1 for x in marks.values()):
        order=[marks[name][0][0] for name in ORDER]
        if order!=sorted(order) or len(set(order))!=len(order):
            errors.append('original host/endpoint/SRAM readback event ordering invalid')
        host,ram_data,ram_write,read,ram_read,ep_cpl,received,passed,done=[marks[x][0][1] for x in ORDER]
        bus_addr,word,plan=host
        expected_local='0000000012000100'
        if bus_addr!='80001100' or word!='a5c36e91':
            errors.append('host memory write not the selected BAR0 plan data')
        if ram_data!=(expected_local,'00000000a5c36e91','0f'):
            errors.append('actual SRAM primitive data/address/strobe mismatch')
        if ram_write!=(expected_local,'4'):
            errors.append('missing real bridge/NoC SRAM write with four accepted endpoint beats')
        if read[0]!=bus_addr:
            errors.append('host read address differs from prior BAR write')
        if ram_read[0]!=expected_local:
            errors.append('real NoC SRAM read missing/wrong address')
        if received!=(read[1],'0','4',word):
            errors.append('host original PCIe CplD tag/status/bytes/data mismatch')
        if passed!=(bus_addr,word):
            errors.append('original host comparison did not pass selected bytes')
        if done[0]!=plan:
            errors.append('canonical SCN plan SHA differs from original host write')
    return {
      'schema_version':1,'kind':'pcie_isolated_connected_memory_roundtrip',
      'scope':'real_rc_original_openpcie_gen1_pcie_axi_master_generated_pcie0_floonoc_real_sram;not_cpu_boot',
      'qualified_connected_memory_roundtrip':not errors,
      'issues':errors,'source':'original_compiler_and_simulator_log',
      'event_lines':{k:[i+1 for i,_ in v] for k,v in marks.items()},
      'over_link_bar0_qualified':bool(bar['qualified_over_link_bar0']),
    }


def main()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('log',type=Path)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    if not args.log.is_file():ap.error('source simulation log missing')
    result=check(args.log.read_text(errors='replace'))
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'pcie-connected-memory-evidence.json').write_text(json.dumps(result,indent=2)+'\n')
    if not result['qualified_connected_memory_roundtrip']:
        print('FAIL: genuine PCIe connected memory readback',result['issues'])
        return 1
    print('PASS: original RC -> original OpenPCIe -> pinned TLP/AXI bridge -> generated FlooNoC -> actual SRAM -> original RC CplD byte oracle')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
