"""Adapt the existing continuous LiteDRAM DFI probe to shared protocol evidence.

No new DDR monitor or controller is implemented. This is a post-simulation
conversion of *observed* command and behavioral BankModel events to the same
ProtocolTrace schema used by PCIe, Ethernet, AXI, and future buses.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
if str(ROOT/"tools") not in sys.path:sys.path.insert(0,str(ROOT/"tools"))
from dv.common.protocol_trace import ProtocolTrace
import protocol_report

DFI="memory0.ddr0.dfi"
BANK="memory0.ddr0.bankmodel"
DFI_COMMANDS={
    "dfi_activate":"act", "dfi_precharge":"pre",
    "dfi_read":"rd", "dfi_write":"wr", "dfi_refresh":"ref",
    "dfi_rddata_en":"rddata_en", "dfi_rddata_valid":"rddata_valid",
    "dfi_wrdata_en":"wrdata_en",
}
BANK_EVENTS={"bankmodel_read":"read","bankmodel_storage_write":"storage_write"}
CATALOG={
    DFI:{"protocol":"dfi","clock_domain":"ddr_source_clk","role":"link",
         "implementation":"litedram_flat_dfi_probe",
         "modeling":"real_controller_rtl_behavioral_phy"},
    BANK:{"protocol":"dfi","clock_domain":"ddr_source_clk","role":"target",
          "implementation":"litedram_bankmodel_probe",
          "modeling":"behavioral_dram_storage"},
}


def export_fullchip_probe(input_dir:Path, trace):
    """Convert the completed full-chip passive probe to the EXISTING run's
    protocol stream. Fail closed on scope mismatch, missing clock samples,
    count mismatches, incomplete capture, or missing real RD/WR commands.
    The caller opened this ProtocolTrace from SOC_RUN_PLAN before clocks.
    """
    folder=Path(input_dir)
    summary=json.loads((folder/"ddr4_dfi_summary.json").read_text())
    if summary.get("status")!="pass" or summary.get("sampled_cycles",0)<1:
        raise ValueError("no successful continuous full-chip DFI samples")
    rows=[json.loads(line) for line in
          (folder/"ddr4_dfi_events.jsonl").read_text().splitlines()]
    if len(rows)<3 or rows[0].get("scope")!="fullchip_litedram_dfi_sim":
        raise ValueError("wrong full-chip DFI evidence scope")
    last=rows[-1]
    if (last.get("kind")!="probe_end" or last.get("status")!="pass" or
            last.get("sampled_cycles")!=summary["sampled_cycles"]):
        raise ValueError("incomplete full-chip DFI probe end")
    if set(trace.sources)!={DFI,BANK}:
        raise ValueError("full-chip DFI source catalog differs from trusted plan")
    counts={}
    for event in rows[1:-1]:
        kind=event["kind"]
        if kind=="probe_heartbeat":
            counts[kind]=counts.get(kind,0)+1
            continue
        source=DFI if kind in DFI_COMMANDS else BANK if kind in BANK_EVENTS else None
        if source is None:
            raise ValueError(f"unknown full-chip DFI event {kind}")
        fields={k:v for k,v in event.items() if k not in ("kind","time_ps")}
        fields["origin_event"]=kind
        fields["model_boundary"]="controller_dfi" if source==DFI else "behavioral_storage"
        trace.event(source,DFI_COMMANDS.get(kind) or BANK_EVENTS[kind],
                    event["time_ps"],fields)
        counts[kind]=counts.get(kind,0)+1
    if counts!=summary.get("counters"):
        raise ValueError("full-chip DFI summary/event count mismatch")
    if not counts.get("dfi_read") or not counts.get("dfi_write"):
        raise ValueError("missing real full-chip DFI READ/WRITE observation")
    return counts


def convert(input_dir:Path,output_dir:Path):
    input_dir,output_dir=Path(input_dir),Path(output_dir)
    summary=json.loads((input_dir/"ddr4_dfi_summary.json").read_text())
    result=json.loads((input_dir/"ddr4_functional_result.json").read_text())
    if (summary.get("status")!="pass" or result.get("status")!="pass"
            or summary.get("sampled_cycles",0)<1):
        raise ValueError("missing successful continuous DDR4 DFI simulation")
    raw=(input_dir/"ddr4_dfi_events.jsonl").read_text().splitlines()
    if len(raw)<3:raise ValueError("missing DFI observation stream")
    first=json.loads(raw[0]);last=json.loads(raw[-1])
    if (first.get("kind")!="probe_start" or
            first.get("scope")!="standalone_litedram_dfi_sim" or
            last.get("kind")!="probe_end" or last.get("status")!="pass" or
            last.get("sampled_cycles")!=summary["sampled_cycles"]):
        raise ValueError("DFI probe start/end and summary disagree")
    output_dir.mkdir(parents=True,exist_ok=True)
    plan={"target":"ddr4-standalone","engine":"cocotb-verilator",
          "report":{"protocols":{"sources":CATALOG,"max_events":250000}}}
    (output_dir/"plan.json").write_text(json.dumps(plan,indent=2)+"\n")
    counts={}
    trace=ProtocolTrace(output_dir/"protocol-events.jsonl",CATALOG,max_events=250000)
    try:
        for line in raw[1:-1]:
            event=json.loads(line)
            kind=event["kind"]
            if kind=="probe_heartbeat":continue
            source=DFI if kind in DFI_COMMANDS else BANK if kind in BANK_EVENTS else None
            if source is None:raise ValueError(f"unknown DDR4 probe operation: {kind}")
            command=(DFI_COMMANDS.get(kind) or BANK_EVENTS.get(kind))
            time_ps=event["time_ps"]
            fields={key:value for key,value in event.items()
                    if key not in ("kind","time_ps")}
            fields["origin_event"]=kind
            fields["model_boundary"]="controller_dfi" if source==DFI else "behavioral_storage"
            # A DFI command/event has no transaction completion and no AXI
            # ID. Never fabricate correlations with outstanding AXI requests.
            trace.event(source,command,time_ps,fields)
            counts[kind]=counts.get(kind,0)+1
        for kind,value in summary.get("counters",{}).items():
            if kind=="probe_heartbeat":continue
            if counts.get(kind,0)!=value:
                raise ValueError(f"DFI event count mismatch: {kind}")
        if set(counts)-set(summary.get("counters",{})):
            raise ValueError("observed DFI command not present in probe summary")
        if not any(counts.get(k,0) for k in ("dfi_activate","dfi_read","dfi_write")):
            raise ValueError("DDR4 report has no real DFI ACT/RD/WR coverage")
        trace.close("pass")
    except Exception:
        trace.close("fail","source DFI evidence conversion failed")
        raise
    protocol=protocol_report.build(output_dir,plan)
    if not protocol or not protocol["capture_complete"]:
        raise ValueError("incomplete DFI protocol conversion")
    # Historical and new test results must be evaluated only for their
    # original tested SHA. A successful standalone simulation is not a claim
    # of the same command probes in the integrated full-chip test.
    result_data={"target":"ddr4-standalone","passed":True,"stage":"run",
                 "engine":"cocotb-verilator",
                 "scope":"standalone_litedram_behavioral_dfi",
                 "protocol_observations":len(protocol["records"]),
                 "sampled_cycles":summary["sampled_cycles"],
                 "physical_phy":"not_modeled",
                 "dfi_command_counts":{
                     command:counts.get(event,0) for event,command in
                     (("dfi_activate","act"),("dfi_precharge","pre"),
                      ("dfi_read","rd"),("dfi_write","wr"),
                      ("dfi_refresh","ref"))
                 },
                 "dfi_act_coverage":"observed" if counts.get("dfi_activate",0)
                     else "not_observed"}
    (output_dir/"result.json").write_text(json.dumps(result_data,indent=2)+"\n")
    return protocol


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    data=convert(a.input,a.output)
    print("DDR4 shared DFI protocol evidence:",len(data["records"]),"observations")


if __name__=="__main__":main()
