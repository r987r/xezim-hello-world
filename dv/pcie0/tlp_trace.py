"""Passive bridge-interface TLP reporting, using pinned upstream TLP models.

Reuse verilog-pcie's PcieIfFrame.to_tlp() and cocotbext-pcie Tlp rather than
inventing PCIe header parsing. Only the minimal valid/ready beat observation
is local, because PcieIfSink would drive READY and conflict with the DUT.
All storage, validation, HTML and AXI/TLP merging use ProtocolTrace.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import os

from dv.common.protocol_trace import open_from_plan

REQUEST = "pcie0.rx_req"
COMPLETION = "pcie0.tx_cpl"
SOURCES = {
    REQUEST: {"protocol": "pcie", "clock_domain": "soc_single_clock",
              "role": "target", "implementation": "verilog_pcie_pcieifframe",
              "modeling": "rtl_bridge_with_modeled_root_complex"},
    COMPLETION: {"protocol": "pcie", "clock_domain": "soc_single_clock",
                 "role": "initiator", "implementation": "verilog_pcie_pcieifframe",
                 "modeling": "rtl_bridge_with_modeled_root_complex"},
}


def describe(tlp, raw_header, *, source, data):
    """Fields come from upstream's parsed Tlp object; keep raw bytes too."""
    from cocotbext.pcie.core.tlp import TlpType
    kinds = {
        TlpType.MEM_READ: "mem_read",
        TlpType.MEM_READ_64: "mem_read",
        TlpType.MEM_WRITE: "mem_write",
        TlpType.MEM_WRITE_64: "mem_write",
        TlpType.CPL: "completion",
        TlpType.CPL_DATA: "completion",
    }
    operation = kinds.get(tlp.fmt_type, "other_tlp")
    requester_id = str(tlp.requester_id)
    tag = int(tlp.tag)
    fields = {
        "direction": "host_to_bridge" if source == REQUEST else "bridge_to_host",
        "fmt_type": str(tlp.fmt_type),
        "requester_id": requester_id,
        "tag": hex(tag),
        "header_hex": f"0x{raw_header:032x}",
        "payload_hex": data.hex(),
        "payload_bytes": len(data),
        "length_dw": int(tlp.length),
        "traffic_class": str(tlp.tc),
    }
    if operation in ("mem_read", "mem_write"):
        fields.update(address=hex(int(tlp.address)), first_be=hex(int(tlp.first_be)),
                      last_be=hex(int(tlp.last_be)),
                      requested_bytes=int(tlp.get_be_byte_count()))
    if operation == "completion":
        fields.update(completer_id=str(tlp.completer_id),
                      completion_status=str(tlp.status),
                      byte_count=int(tlp.byte_count),
                      lower_address=int(tlp.lower_address))
    return operation, fields, requester_id + ":" + str(tag)


class AcceptedTlpPackets:
    """No bus drivers: rebuild upstream PcieIfFrame from accepted beats."""
    def __init__(self, trace, frame_type):
        self.trace, self.frame_type = trace, frame_type
        self.active = {REQUEST: None, COMPLETION: None}
        self.counts = Counter()
        self.pending = {}
        self.max_beats = 1024

    def beat(self, source, time_ps, *, valid, ready, sop=0, eop=0,
             header=0, data=0, strobe=None):
        if source not in self.active:
            raise ValueError("unknown TLP monitor")
        if not (valid and ready):
            return
        packet = self.active[source]
        if sop:
            if packet is not None:
                raise AssertionError("overlapping TLP SOP")
            packet = {"start_ps": time_ps, "frame": self.frame_type(), "beats": 0}
            packet["frame"].hdr = int(header)
            self.active[source] = packet
        elif packet is None:
            raise AssertionError("accepted TLP beat without SOP")
        packet["beats"] += 1
        if packet["beats"] > self.max_beats:
            raise AssertionError("TLP exceeded capture bound")
        # Header bit 126 (fmt[1]) is upstream's payload-present flag.
        if (packet["frame"].hdr >> 126) & 1:
            remaining = ((packet["frame"].hdr >> 96) & 0x3ff) or 1024
            remaining -= len(packet["frame"].data)
            for lane in range(min(2, remaining)):
                if strobe is not None and not ((strobe >> lane) & 1):
                    raise AssertionError("PCIe completion missing active DWORD strobe")
                packet["frame"].data.append((int(data) >> (32 * lane)) & 0xffffffff)
        if eop:
            self._commit(source, time_ps, packet)
            self.active[source] = None

    def _commit(self, source, time_ps, packet):
        frame = packet["frame"]
        tlp = frame.to_tlp()  # Pinned verilog-pcie + cocotbext-pcie parser
        data = tlp.get_data()
        operation, fields, key = describe(tlp, frame.hdr, source=source, data=data)
        if source == COMPLETION and operation != "completion":
            raise AssertionError("expected bridge completion output")
        if source == REQUEST and operation == "completion":
            raise AssertionError("unexpected bridge ingress completion")
        fields["accepted_beats"] = packet["beats"]
        if source == REQUEST and operation == "mem_read":
            if key in self.pending:
                raise AssertionError("duplicate outstanding PCIe tag " + key)
            self.pending[key] = {"time_ps": packet["start_ps"],
                                 "address": fields["address"],
                                 "remaining": fields["requested_bytes"]}
        if source == COMPLETION:
            req = self.pending.get(key)
            if req is None:
                raise AssertionError("unmatched PCIe completion " + key)
            from cocotbext.pcie.core.tlp import CplStatus
            if tlp.status != CplStatus.SC:
                raise AssertionError("PCIe completion status not successful")
            fields["matched_request_address"] = req["address"]
            fields["request_to_completion_ps"] = time_ps - req["time_ps"]
            if len(data) == 0:
                raise AssertionError("PCIe completion with no payload")
            req["remaining"] -= min(req["remaining"], max(0, len(data) - (int(tlp.lower_address) & 3)))
            if req["remaining"] <= 0:
                del self.pending[key]
            fields["request_remaining_bytes"] = max(0, req["remaining"])
        self.trace.transaction(source, operation, packet["start_ps"], time_ps,
                               identifier=key, fields=fields)
        self.counts[(source, operation)] += 1

    def finish(self):
        try:
            if any(v is not None for v in self.active.values()):
                raise AssertionError("TLP capture ended with partial packet")
            if self.pending:
                raise AssertionError("TLP capture has dangling requester/tag " +
                                     ", ".join(sorted(self.pending)))
            for key in ((REQUEST, "mem_write"), (REQUEST, "mem_read"),
                        (COMPLETION, "completion")):
                if not self.counts[key]:
                    raise AssertionError(f"PCIe TLP evidence missing {key}")
        except BaseException as exc:
            self.trace.close("fail", exc)
            raise
        self.trace.close("pass")


class LiveTlpCapture:
    def __init__(self, dut, *, frame_type, plan_path=None):
        import cocotb
        self.dut = dut
        self.trace = open_from_plan(Path(plan_path or os.environ["SOC_RUN_PLAN"]))
        if self.trace is None or self.trace.sources != SOURCES:
            raise ValueError("PCIe TLP catalog mismatch")
        for source in SOURCES:
            prefix = "rx_req_tlp" if source == REQUEST else "tx_cpl_tlp"
            for field in ("data", "hdr", "valid", "sop", "eop", "ready"):
                getattr(dut, prefix + "_" + field)
            if source == COMPLETION:
                getattr(dut, prefix + "_strb")
        self.packets = AcceptedTlpPackets(self.trace, frame_type)
        self.task = cocotb.start_soon(self.run())

    async def run(self):
        from cocotb.triggers import RisingEdge
        from cocotb.utils import get_sim_time
        while True:
            await RisingEdge(self.dut.clk)
            if not int(self.dut.rst_n.value):
                continue
            now = int(get_sim_time(units="ps"))
            for source in (REQUEST, COMPLETION):
                prefix = "rx_req_tlp" if source == REQUEST else "tx_cpl_tlp"
                def signal(name):
                    return int(getattr(self.dut, prefix + "_" + name).value)
                self.packets.beat(
                    source, now, valid=signal("valid"), ready=signal("ready"),
                    sop=signal("sop"), eop=signal("eop"),
                    header=signal("hdr"), data=signal("data"),
                    strobe=signal("strb") if source == COMPLETION else None)

    def finish(self):
        self.task.kill()
        self.packets.finish()
        return {f"{source}/{operation}": count
                for (source, operation), count in self.packets.counts.items()}
