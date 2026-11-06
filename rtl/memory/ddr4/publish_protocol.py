"""Publish REAL standalone LiteDRAM DFI probe as standard source-verified CI evidence.

Adapts existing read-only DFIProbe JSONL. It is not a new DDR driver, monitor,
PHY, protocol checker or full-chip capture. See docs/protocol-run-reports.md.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import argparse
import json
import os
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
TOOLS=ROOT/"tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0,str(TOOLS))
from protocol_report import render as render_protocol_report

COMMANDS={
    "dfi_activate":"act", "dfi_precharge":"pre", "dfi_read":"rd",
    "dfi_write":"wr", "dfi_refresh":"ref",
}
DFI_DATA={"dfi_rddata_en":"rddata_en","dfi_rddata_valid":"rddata_valid",
          "dfi_wrdata_en":"wrdata_en"}
BANK={"bankmodel_read":"model_read","bankmodel_storage_write":"model_storage_write"}
IGNORED={"probe_heartbeat"}
ALLOWED=set(COMMANDS)|set(DFI_DATA)|set(BANK)|IGNORED
TARGET="ddr4-standalone"
PERIOD_PS=10000


def validate_and_adapt(output:Path):
    """Require complete, internally consistent, timestamped source probe data."""
    path=output/"ddr4_dfi_events.jsonl"
    summary=json.loads((output/"ddr4_dfi_summary.json").read_text())
    result=json.loads((output/"ddr4_functional_result.json").read_text())
    if summary.get("status")!="pass" or result.get("status")!="pass":
        raise ValueError("standalone LiteDRAM did not pass continuous RTL/DFI tests")
    if summary.get("period_source")!="configured_and_observed_standalone_clk":
        raise ValueError("unknown DFI sample time source")
    sample_count=summary.get("sampled_cycles")
    if type(sample_count) is not int or sample_count<1:
        raise ValueError("missing continuously observed DFI cycles")
    lines=path.read_text().splitlines()
    if len(lines)<3:
        raise ValueError("DFI event stream missing start/end/data")
    events=[json.loads(line) for line in lines]
    start,end=events[0],events[-1]
    if start.get("kind")!="probe_start" or start.get("scope")!="standalone_litedram_dfi_sim":
        raise ValueError("invalid DFI source model/scope")
    if start.get("physical_phy")!="not_modeled" or start.get("physical_dram")!="not_modeled":
        raise ValueError("DFI model scope not explicit")
    if end.get("kind")!="probe_end" or end.get("status")!="pass" or end.get("sampled_cycles")!=sample_count:
        raise ValueError("DFI probe did not terminate successfully")
    if summary.get("models",{}).get("full_chip")!="not_connected":
        raise ValueError("source scope differs from standalone simulation")
    counters=Counter()
    sources={}
    records=[]
    last_time=-1
    previous_cycle=0
    command_counts=Counter()
    for e in events[1:-1]:
        kind=e.get("kind")
        if kind not in ALLOWED:
            raise ValueError(f"unrecognized DDR DFI probe event: {kind}")
        time=e.get("time_ps")
        cycle=e.get("cycle")
        if (type(time) is not int or type(cycle) is not int
                or time<last_time or not 1<=cycle<=sample_count
                or cycle<previous_cycle):
            raise ValueError("non-monotonic / missing DFI sample timestamps")
        if last_time>=0 and time-last_time>PERIOD_PS*(cycle-previous_cycle):
            raise ValueError("DFI event timestamp/cycle mismatch")
        last_time,previous_cycle=time,cycle
        counters[kind]+=1
        if kind in IGNORED:
            continue
        if kind in COMMANDS or kind in DFI_DATA:
            phase=e.get("dfi_phase")
            if type(phase) is not int or not 0<=phase<4:
                raise ValueError("unrecognized pinned four-phase DFI bus")
            name=f"memory0.ddr0.dfi.phase{phase}"
            operation=COMMANDS.get(kind,DFI_DATA.get(kind))
            owner="generated_litedram_controller"
            role="link"
            source_type="dfi"
            if kind in COMMANDS:
                command_counts[operation]+=1
        else:
            bank=e.get("bank")
            if type(bank) is not int or not 0<=bank<16:
                raise ValueError("unrecognized pinned sixteen-bank model")
            name=f"memory0.ddr0.bankmodel.bank{bank}"
            operation=BANK[kind]
            owner="litedram_behavioral_bankmodel"
            role="target"
            source_type="ddr_model"
        sources.setdefault(name,{
            "id":name,"protocol":source_type,"role":role,
            "clock_domain":"ddr_standalone_100mhz",
            "implementation":owner,
        })
        fields={key:value for key,value in e.items()
                if key not in ("kind","time_ps")}
        fields["capture_scope"]="standalone_controller_behavioral_phy_not_fullchip"
        records.append({
            "kind":"event","source":name,"protocol":source_type,
            "operation":operation,"id":None,
            "start_ps":time,"end_ps":time,"status":"observed",
            "fields":fields,
        })
    if dict(counters)!=summary.get("counters",{}):
        raise ValueError("DFI raw command counts disagree with source probe summary")
    if not records or not command_counts:
        raise ValueError("DFI source emitted no actual command observations")
    if not any(r["operation"]=="rd" for r in records) or not any(r["operation"]=="wr" for r in records):
        raise ValueError("DDR evidence missing observed read/write commands")
    return list(sources.values()),records,dict(command_counts),sample_count


def publish(output:Path,destination:Path,*,commit:str,run_id:str,attempt:str):
    if not re.fullmatch("[0-9a-f]{40}",commit):
        raise ValueError("must pin a real Git source commit")
    if not run_id.isdecimal() or not attempt.isdecimal():
        raise ValueError("missing CI run identity")
    sources,records,command_counts,sampled=validate_and_adapt(output)
    if destination.is_symlink():
        raise ValueError("refusing symlinked published evidence directory")
    destination.mkdir(parents=True,exist_ok=True)
    run={"target":TARGET,"engine":"cocotb-verilator",
         "commit":commit,"dirty":False,"workflow_run_id":run_id,
         "workflow_attempt":attempt,
         "capture_scope":"standalone_litedram_dfi_phy_model",
         "source_model":"pinned LiteDRAM RTL + behavioral SDRAMPHYModel/BankModel"}
    report={"schema_version":1,"run":run,"sources":sources,
            "records":records,"capture_complete":True,"issues":[],
            "modeling":"Standalone generated LiteDRAM controller RTL with behavioral DDR4 PHY and model; not full chip, physical DRAM or JEDEC compliance"}
    (destination/"protocol-transactions.json").write_text(json.dumps(report,indent=2)+"\n")
    render_protocol_report(report,destination/"protocols.html")
    (destination/"plan.json").write_text(json.dumps({
        "target":TARGET,"engine":"cocotb-verilator",
        "report":{"context":"Standalone pinned LiteDRAM/DFI; NOT DDR-B fullchip, no electrical PHY or real DDR4 die"}
    },indent=2)+"\n")
    (destination/"result.json").write_text(json.dumps({
        "target":TARGET,"passed":True,"stage":"all",
        "dfi_commands":command_counts,"dfi_sampled_cycles":sampled,
        "scope":"standalone_real_controller_behavioral_phy"
    },indent=2)+"\n")
    return {"commands":command_counts,"sources":len(sources),
            "records":len(records),"sampled_cycles":sampled}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--destination",type=Path,required=True)
    args=parser.parse_args()
    sha=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    dirty=subprocess.check_output(["git","status","--porcelain"],cwd=ROOT,text=True)
    if dirty:
        raise ValueError("refusing to publish protocol evidence from dirty Git checkout")
    result=publish(args.source,args.destination,commit=sha,
                   run_id=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"])
    print("PASS source-verified standalone DDR DFI protocol capture:",json.dumps(result))


if __name__=="__main__":
    main()
