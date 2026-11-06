#!/usr/bin/env python3
"""DV-MEM-TRACE: source-neutral buffer lifetime and real AXI access view.

Reuses SCN-1 planner metadata, actual CPU run checker and existing AXI
correlator. Never infer a CPU allocation/token, buffer release, or real DDR4
PHY timing from a predicted virtual allocation or DMA data traffic.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from html import escape
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from dv.common.action_events import parse_plan, ActionEvidenceError


def n(value):
    if type(value) is int and 0 <= value < 1 << 64:
        return value
    if isinstance(value,str) and value.startswith('0x'):
        return int(value,16)
    raise ActionEvidenceError(f'invalid physical address/value {value!r}')


def _data_actions(a):
    args=a.get('args',{})
    if a['kind']=='memory.allocate': return []
    if a['kind']=='dma.copy': return [args['src'],args['dst']]
    if a['kind'] in ('memory.initialize','memory.check','memory.release'):
        return [args['buffer']]
    if a['kind']=='dma.configure': return [args['descriptor_buffer']]
    return []


def _checked_run(execution, result, plan, sha):
    if execution is None:
        if result is not None:
            raise ActionEvidenceError('result without scenario execution cannot establish memory proof')
        return None
    if (not isinstance(execution,dict) or not isinstance(result,dict)
            or result.get('passed') is not True
            or not isinstance(result.get('results'),list)
            or len(result['results']) != 1
            or result['results'][0].get('passed') is not True
            or result['results'][0].get('exit_code') != 0
            or execution.get('scenario_id') != plan['scenario_id']
            or execution.get('plan_sha256') != sha
            or execution.get('execution_state') != 'rtl_observed'
            or execution.get('intent_is_not_evidence') is not True):
        raise ActionEvidenceError('scenario run was not independently RTL-qualified')
    profile=execution.get('profile')
    if profile == 'real_cpu0_compiled_c':
        flow=result.get('test_flow') or {}
        if (execution.get('cpu_result_checked') is not True
                or flow.get('status') != 'complete'
                or flow.get('passed') is not True
                or flow.get('issues') != 0):
            raise ActionEvidenceError('CPU allocator/firmware proof missing')
        if plan['scenario_id'] != 'cpu_bfm_ddr_roundtrip':
            raise ActionEvidenceError('legacy unnamed CPU allocations supported only for one exact scenario')
        addresses=execution.get('observed_cpu_allocations')
        if (not isinstance(addresses,list) or len(addresses)!=3
                or any(type(v) is not int for v in addresses)):
            raise ActionEvidenceError('missing observed CPU mailbox physical allocations')
        return dict(profile=profile,observed_phys=dict(zip(('src','return','ddr'),addresses)),
                    bytes_checked='real_cpu0_firmware')
    if profile == 'reset_isolated_cocotb_bfm':
        if result.get('test_flow',{}).get('status') != 'unmeasured':
            raise ActionEvidenceError('BFM falsely claims CPU firmware phase coverage')
        if plan['scenario_id'] != 'cpu_bfm_ddr_roundtrip':
            raise ActionEvidenceError('legacy unnamed BFM byte-check supported only for one scenario')
        length=next((a['args']['length'] for a in plan['actions'] if a['kind']=='memory.check'),None)
        if execution.get('independently_readback_bytes')!=length:
            raise ActionEvidenceError('BFM byte readback incomplete')
        return dict(profile=profile,observed_phys={},bytes_checked='cocotb_axi_readback')
    raise ActionEvidenceError('unsupported SCN2 runtime evidence profile')


def build(plan_bytes:bytes, *, axi=None, execution=None, result=None):
    plan,sha,actions=parse_plan(plan_bytes)
    regions={r['name']:r for r in plan.get('regions',[])}
    if not regions: raise ActionEvidenceError('no modeled region inventory')
    allocations=plan.get('allocations')
    if not isinstance(allocations,list): raise ActionEvidenceError('no predicted buffer allocations')
    runtime=_checked_run(execution,result,plan,sha)
    if runtime and axi is None:
        raise ActionEvidenceError('runtime proof requires independent correlated AXI capture')
    rows=[]
    identities=set()
    by_name={}
    for item in allocations:
        if not isinstance(item,dict): raise ActionEvidenceError('invalid allocation')
        buffer=item.get('buffer')
        if not isinstance(buffer,str) or buffer in by_name:
            raise ActionEvidenceError('duplicate/invalid buffer handle')
        region=regions.get(item.get('region'))
        if not isinstance(region,dict): raise ActionEvidenceError('unknown physical region')
        base,capacity=n(region['base']),n(region['modeled_bytes'])
        phys,size=n(item.get('phys')),n(item.get('size'))
        token,generation=item.get('token'),item.get('generation')
        if (not size or phys < base or phys + size > base + capacity or
                type(token) is not int or token<1 or
                type(generation) is not int or generation<1):
            raise ActionEvidenceError('invalid/overflowed modeled allocation')
        key=(item['region'],generation,token)
        if key in identities: raise ActionEvidenceError('duplicate C-compatible allocation token')
        identities.add(key)
        alloc=actions.get(item.get('allocated_by'))
        if alloc is None or alloc['kind']!='memory.allocate' or alloc['args'].get('buffer')!=buffer:
            raise ActionEvidenceError('buffer lacks a matching plan allocation action')
        release_id=item.get('released_by')
        if release_id is not None:
            release=actions.get(release_id)
            if release is None or release['kind']!='memory.release' or release['args'].get('buffer')!=buffer:
                raise ActionEvidenceError('buffer release not declared in scenario')
        row={'buffer':buffer,'region':item['region'],'region_kind':region['kind'],
             'cpu_visible':region['cpu_visible'],'phys':hex(phys),'size_bytes':size,
             'token':token,'generation':generation,'token_provenance':'planner_only',
             'owner':item['owner'],'phase':item['phase'],
             'allocated_by':item['allocated_by'],'released_by':release_id,
             'release_status':'planned_only' if release_id is not None else 'retained_at_run_end',
             'phys_provenance':'planner_only','actual_cpu_phys':None,
             'planned_consumers':[a['action_instance_id'] for a in actions.values()
                                  if buffer in _data_actions(a) and a['kind']!='memory.release'],
             'observed_accesses':[], 'checks':[], 'initializations':[]}
        for a in actions.values():
            if a['args'].get('buffer')==buffer and a['kind']=='memory.initialize':
                row['initializations'].append({'action':a['action_instance_id'],
                     'pattern':a['args']['pattern'],'policy':a['args']['policy'],
                     'status':'intent_only'})
            if a['args'].get('buffer')==buffer and a['kind']=='memory.check':
                row['checks'].append({'action':a['action_instance_id'],
                     'pattern':a['args']['pattern'],'policy':a['args']['policy'],
                     'status':'intent_only'})
        rows.append(row)
        by_name[buffer]=row
    if runtime:
        for buffer,phys in runtime['observed_phys'].items():
            row=by_name.get(buffer)
            if row is None or n(row['phys'])!=phys:
                raise ActionEvidenceError(f'actual CPU MMIO allocation differs from plan: {buffer}')
            row['actual_cpu_phys']=hex(phys)
            row['phys_provenance']='rtl_cpu_mailbox_checked_by_existing_test'
        if 'return' in by_name:
            for check in by_name['return']['checks']:
                check['status']=runtime['bytes_checked']
    if axi is not None:
        head=axi.get('run',{})
        block=axi.get('sections',{}).get('axi',{})
        if (head.get('capture_bound') is not True or
                head.get('capture_overflow') is not False or
                block.get('issues') or not isinstance(block.get('transactions'),list)):
            raise ActionEvidenceError('not a complete real AXI source capture')
        # Stable interval index avoids O(transactions * buffers). Reused
        # physical ranges have ambiguous ownership without real lifetime times.
        intervals=sorted(((n(r['phys']),n(r['phys'])+r['size_bytes'],r) for r in rows),
                         key=lambda v:(v[0],v[1]))
        if any(a[1]>b[0] for a,b in zip(intervals,intervals[1:])):
            raise ActionEvidenceError('ambiguous physical address reuse without observed lifetimes')
        starts=[a[0] for a in intervals]
        uids=set()
        for txn in block['transactions']:
            if txn.get('role')!='initiator': continue
            start=n(txn.get('address'))
            index=bisect_right(starts,start)-1
            if index<0 or start>=intervals[index][1]: continue
            row=intervals[index][2]
            uid=txn.get('uid')
            if not isinstance(uid,str) or not uid.startswith(str(txn.get('monitor'))+':') or uid in uids:
                raise ActionEvidenceError('missing/reused AXI source-scoped UID')
            uids.add(uid)
            if (txn.get('status')!='complete' or txn.get('issues') or
                    txn.get('operation') not in ('read','write') or n(txn.get('response'))!=0 or
                    type(txn.get('start_ps')) is not int or type(txn.get('end_ps')) is not int or
                    txn['end_ps'] < txn['start_ps']):
                raise ActionEvidenceError('matching physical buffer has incomplete/error AXI evidence')
            # Do not infer that the whole buffer was transferred. This match
            # proves only that the accepted source-side start address lies in it.
            row['observed_accesses'].append({'uid':uid,'monitor':txn['monitor'],
                'operation':txn['operation'],'start_ps':txn['start_ps'],
                'end_ps':txn['end_ps'],'matching':'start_address_within_buffer'})
    if runtime:
        expected=execution['observed_dma_axi_counts']
        if (not isinstance(expected,dict) or
                not all(type(expected.get(k)) is int and expected[k]>0
                        for k in ('src_ar','ddr_aw','ddr_ar','return_aw'))):
            raise ActionEvidenceError('SCN2 CPU/BFM observed DMA acceptance counts missing')
        counts={'src_ar':len([a for a in by_name['src']['observed_accesses'] if a['operation']=='read' and a['monitor']=='compute0_local_data.dma']),
                'ddr_aw':len([a for a in by_name['ddr']['observed_accesses'] if a['operation']=='write' and a['monitor']=='compute0_local_data.dma']),
                'ddr_ar':len([a for a in by_name['ddr']['observed_accesses'] if a['operation']=='read' and a['monitor']=='compute0_local_data.dma']),
                'return_aw':len([a for a in by_name['return']['observed_accesses'] if a['operation']=='write' and a['monitor']=='compute0_local_data.dma'])}
        if counts!=expected:
            raise ActionEvidenceError(f'SCN2 independently correlated AXI counts differ: {counts} != {expected}')
    return {'schema_version':1,'kind':'soc_scenario_memory_lifetimes',
            'scenario_id':plan['scenario_id'],'plan_sha256':sha,
            'source_revision':plan.get('provenance',{}).get('source_revision'),
            'target_model':'modeled_memory_only_not_litedram_phy',
            'execution_profile':runtime['profile'] if runtime else None,
            'status':('cpu_phys_correlated_lifetimes_planned_only' if runtime and runtime['observed_phys'] else
                      'bfm_traffic_observed_allocation_unmeasured' if runtime else
                      'plan_only_unmeasured'),
            'real_allocation_tokens_proven':False,'release_quiescence_proven':False,
            'buffers':rows}


def embed_in_run_report(report_path:Path, payload:dict):
    """Single existing run page, not a second dashboard or invented pass."""
    path=Path(report_path)
    text=path.read_text(encoding='utf-8')
    marker='<!-- DV-MEM-LIFETIME-V1 -->'
    if '<main>' not in text or marker in text:
        raise ActionEvidenceError('report.html lacks injection point or already contains memory view')
    rows=[]
    for b in payload['buffers']:
        counts={'read':0,'write':0}
        for a in b['observed_accesses']:
            counts[a['operation']]+=1
        values=(b['buffer'],b['region'],b['region_kind'],b['phys'],str(b['size_bytes']),
                b['phys_provenance'],b['token_provenance'],
                str(counts['read']),str(counts['write']),b['release_status'])
        rows.append('<tr>'+''.join('<td>'+escape(v)+'</td>' for v in values)+'</tr>')
    heading='<thead><tr>'+''.join('<th>'+escape(h)+'</th>' for h in
        ('Buffer','Region','Kind','Physical base','Bytes','Address proof',
         'Token proof','AXI reads','AXI writes','Release'))+'</tr></thead>'
    section=(marker+'<section id="memory-lifetime-evidence"><h2>Memory allocation and lifetime evidence</h2>'
        '<p>Physical locations and tokens are planner predictions unless explicitly marked '
        'CPU mailbox checked. AXI counts are accepted source-side start-address matches. '
        'No release or LiteDRAM PHY timing proof is inferred.</p><table>'+heading+
        '<tbody>'+''.join(rows)+'</tbody></table></section>')
    path.write_text(text.replace('<main>','<main>'+section,1),encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--axi',type=Path)
    p.add_argument('--scenario-execution',type=Path)
    p.add_argument('--result',type=Path)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--report-html',type=Path,
                   help='inject safe buffer table into EXISTING per-run report.html')
    a=p.parse_args()
    try:
        def maybe(path): return json.loads(path.read_text()) if path else None
        payload=build(a.plan.read_bytes(),axi=maybe(a.axi),
                      execution=maybe(a.scenario_execution),result=maybe(a.result))
    except (OSError,ValueError,TypeError) as exc:
        p.error(str(exc))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(payload,sort_keys=True,indent=2)+'\n')
    if a.report_html:
        embed_in_run_report(a.report_html,payload)
    print('DV-MEM-TRACE: '+payload['status']+'; no inferred CPU tokens or real DDR PHY')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
