"""Source-neutral firmware/SV test-flow encoding and generated marker syntax.

Python and Cocotb use JSONL spans. RTL observed firmware activity uses
SOC_FLOW_V1 stdout markers from the central full-chip checker.
C can emit compact step values over a caller-allocated monitored MMIO port.
Do not treat an unobserved software request as completed RTL coverage.
"""
from __future__ import annotations
import re

SV_RE=re.compile(r"SOC_FLOW_V1\|([0-9]+)\|(init|run|check)\|([a-z][a-z0-9_.-]*)\|([a-z][a-z0-9_.-]*)\|(start|pass|fail)(?:\r?\n|$)")
PHASE_IDS={"init":0,"run":1,"check":2}
STATUS_IDS={"start":0,"pass":1,"fail":2}

def sv_event(phase,actor,step,status):
    identifier=re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
    if phase not in PHASE_IDS or status not in STATUS_IDS or any(not identifier.fullmatch(v) for v in (actor,step)):
        raise ValueError("invalid RTL step identification")
    return f'$display("SOC_FLOW_V1|%0d|{phase}|{actor}|{step}|{status}", $time);'

def decode_c_marker(word, actors, steps):
    """Validate 0xF1-prefixed observed *32-bit* software trace write."""
    if type(word) is not int or not 0<=word<2**32 or word>>24!=0xF1:
        raise ValueError("unknown C test-flow marker")
    phase=(word>>22)&3
    status=(word>>20)&3
    actor=(word>>12)&255
    step=word&4095
    if phase not in (0,1,2) or status not in (0,1,2) or actor not in actors or step not in steps:
        raise ValueError("unregistered C test-flow event")
    return {"phase":("init","run","check")[phase],
            "status":("start","pass","fail")[status],
            "actor":actors[actor],"step":steps[step]}
