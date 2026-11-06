"""Protocol-neutral Ethernet frame evidence at the real GMII VIP boundary.

Do not implement a second Ethernet MAC/BFM or call stimulus a DUT response:
RX records mean the upstream GmiiSource finished injecting on GMII;
TX records mean upstream GmiiSink returned an observed RTL frame.
All timing is cocotb simulation time. No inferred physical PHY delay.
"""
from __future__ import annotations

from dv.common.protocol_trace import open_from_plan

RX="ethernet0.gmii_rx"
TX="ethernet0.gmii_tx"


def frame_fields(raw: bytes, *, observed: bool, fcs_valid=None, error=None):
    raw=bytes(raw)
    fields={
        "direction": "rtl_to_external" if observed else "external_to_rtl",
        "boundary": "gmii_tx_sink_observed" if observed else "gmii_rx_source_injected",
        "length_bytes": len(raw),
        "payload_hex": raw.hex(),
        "dst_mac": ":".join(f"{v:02x}" for v in raw[:6]),
        "src_mac": ":".join(f"{v:02x}" for v in raw[6:12]),
        "ether_type": f"0x{int.from_bytes(raw[12:14], 'big'):04x}" if len(raw)>=14 else None,
    }
    if len(raw)>=14+20+8 and raw[12:14]==b"\x08\x00" and raw[14]>>4==4:
        ihl=(raw[14]&15)*4
        fields.update(src_ip=".".join(str(b) for b in raw[26:30]),
                      dst_ip=".".join(str(b) for b in raw[30:34]),
                      ip_protocol=int(raw[23]))
        offset=14+ihl
        if raw[23]==17 and len(raw)>=offset+8:
            fields.update(src_port=int.from_bytes(raw[offset:offset+2],"big"),
                          dst_port=int.from_bytes(raw[offset+2:offset+4],"big"))
    if fcs_valid is not None:
        fields["fcs_valid"]=bool(fcs_valid)
    if error is not None:
        fields["error"]=str(error)
    return fields


class GmiiEvidence:
    def __init__(self, plan_path=None):
        self.trace=open_from_plan(plan_path)
        if self.trace is None or set(self.trace.sources)!={RX,TX}:
            raise ValueError("Ethernet GMII evidence source inventory differs from regression plan")
        self.seq={RX:0,TX:0}

    def packet(self, source, payload, *, fcs_valid=None, error=None):
        if source not in self.seq:
            raise ValueError("unknown GMII evidence source")
        from cocotb.utils import get_sim_time
        t=int(get_sim_time(units="ps"))
        observed=source==TX
        self.seq[source]+=1
        self.trace.event(source,"frame_tx" if observed else "frame_rx_injected",t,
            {**frame_fields(payload,observed=observed,fcs_valid=fcs_valid,error=error),
             "sequence":self.seq[source]})

    def finish(self):
        if not all(self.seq.values()):
            raise AssertionError("missing either injected GMII RX or observed RTL GMII TX frame")
        self.trace.close("pass")
