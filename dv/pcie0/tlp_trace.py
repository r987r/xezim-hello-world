"""Passive, accepted-beat PCIe TLP capture for the real verilog-pcie bridge.

The existing ProtocolTrace owns the JSONL ABI and unified run explorer.
This adapter samples ONLY valid && ready on the 64-bit/one-segment TLP
interface. It neither generates requests nor replaces cocotbext-pcie.
Header bit positions are those of pinned verilog-pcie pcie_axi_master_{rd,wr}.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import os

from dv.common.protocol_trace import ProtocolTrace, open_from_plan

REQUEST = "pcie0.rx_req"
COMPLETION = "pcie0.tx_cpl"
SOURCES = {
    REQUEST: {"protocol": "pcie", "clock_domain": "soc_single_clock",
              "role": "target", "implementation": "verilog_pcie_tlp_handshake",
              "modeling": "rtl_bridge_with_modeled_root_complex"},
    COMPLETION: {"protocol": "pcie", "clock_domain": "soc_single_clock",
                 "role": "initiator", "implementation": "verilog_pcie_tlp_handshake",
                 "modeling": "rtl_bridge_with_modeled_root_complex"},
}


def field(value, shift, bits):
    return (value >> shift) & ((1 << bits) - 1)


def decode_header(header):
    """Decode upstream's normalized 128-bit PCIe header, not an AXI address."""
    fmt, kind = field(header, 125, 3), field(header, 120, 5)
    length = field(header, 96, 10) or 1024  # PCIe 0 means 1024 DWORDs
    tag = field(header, 72, 8) | (field(header, 115, 1) << 8) | (field(header, 119, 1) << 9)
    result = {
        "header_hex": f"0x{header:032x}", "fmt": fmt, "type": kind,
        "length_dw": length, "length_bytes": length * 4,
        "traffic_class": field(header, 116, 3),
        "tag": hex(tag),
    }
    if kind == 0:  # PCIe memory read or memory write, 3DW or 4DW
        operation = "mem_write" if fmt & 2 else "mem_read"
        addr = ((field(header, 2, 62) if fmt & 1 else field(header, 34, 30)) << 2)
        rid = field(header, 80, 16)
        first_be, last_be = field(header, 64, 4), field(header, 68, 4)
        byte_count = (first_be.bit_count() if length == 1 else
                      (length - 2) * 4 + first_be.bit_count() + last_be.bit_count())
        result.update(address=hex(addr), requester_id=hex(rid),
                      first_be=hex(first_be), last_be=hex(last_be),
                      requested_bytes=byte_count)
    elif kind == 0x0a:  # PCIe completion, possibly with data
        operation = "completion"
        rid = field(header, 48, 16)
        result.update(requester_id=hex(rid),
                      completer_id=hex(field(header, 80, 16)),
                      completion_status=field(header, 77, 3),
                      completion_byte_count=field(header, 64, 12) or 4096,
                      lower_address=field(header, 32, 7))
    else:
        operation = "tlp_type_" + format(kind, "02x")
        rid = field(header, 80, 16)
        result["requester_id"] = hex(rid)
    result["request_tag"] = f"{rid:04x}:{tag:03x}"
    return operation, result


class AcceptedTlpPackets:
    """Reassemble accepted SOP/EOP, track outstanding non-posted reads."""
    def __init__(self, trace):
        self.trace = trace
        self.active = {REQUEST: None, COMPLETION: None}
        self.stalls = Counter()
        self.counts = Counter()
        self.pending_reads = {}
        self.packet_count = 0
        self.max_beats = 1024

    def beat(self, source, time_ps, *, valid, ready, sop=0, eop=0,
             header=0, data=0, strobe=None):
        if source not in self.active:
            raise ValueError("uncataloged TLP lane")
        if not valid:
            return
        if not ready:
            self.stalls[source] += 1
            return
        current = self.active[source]
        if sop:
            if current is not None:
                raise AssertionError("TLP SOP before prior EOP: " + source)
            current = {"start_ps": time_ps, "header": header,
                       "beats": [], "strobes": [], "stalls": self.stalls[source]}
            self.stalls[source] = 0
            self.active[source] = current
        elif current is None:
            raise AssertionError("accepted TLP beat without SOP: " + source)
        if len(current["beats"]) >= self.max_beats:
            raise AssertionError("TLP exceeded maximum captured beats")
        current["beats"].append(int(data).to_bytes(8, "little").hex())
        current["strobes"].append(None if strobe is None else int(strobe))
        if eop:
            self._commit(source, time_ps, current)
            self.active[source] = None

    def _commit(self, source, end_ps, packet):
        operation, info = decode_header(packet["header"])
        if source == COMPLETION and operation != "completion":
            raise AssertionError("non-completion TLP on bridge completion output")
        if source == REQUEST and operation == "completion":
            raise AssertionError("unexpected completion on bridge request input")
        info.update(direction="ingress_request" if source == REQUEST else "egress_completion",
                    accepted_beats=len(packet["beats"]),
                    stall_cycles=packet["stalls"],
                    raw_beat_data_hex="".join(packet["beats"]),
                    raw_beat_strobes=("".join(f"{value:02x}" for value in packet["strobes"])
                                      if packet["strobes"][0] is not None else "unavailable"))
        key = info["request_tag"]
        if source == REQUEST and operation == "mem_read":
            if key in self.pending_reads:
                raise AssertionError("duplicate outstanding PCIe requester/tag: " + key)
            self.pending_reads[key] = {
                "start_ps": packet["start_ps"], "address": info["address"],
                "remaining": info["requested_bytes"], "fragments": 0,
            }
        if source == COMPLETION:
            request = self.pending_reads.get(key)
            if request is None:
                raise AssertionError("unmatched PCIe completion: " + key)
            if info["completion_status"] != 0:
                raise AssertionError("non-success PCIe completion: " + key)
            info["matched_request_address"] = request["address"]
            info["request_to_completion_ps"] = end_ps - request["start_ps"]
            request["fragments"] += 1
            info["completion_fragment"] = request["fragments"]
            # Strb enumerates valid DWORDs. The lower-address offset can
            # contain leading bytes outside the requested byte range.
            valid_dw = sum(mask.bit_count() for mask in packet["strobes"])
            valid_bytes = max(0, valid_dw * 4 - (info["lower_address"] & 3))
            if valid_bytes <= 0:
                raise AssertionError("PCIe completion has no valid payload")
            info["valid_data_bytes"] = valid_dw * 4
            request["remaining"] -= min(request["remaining"], valid_bytes)
            info["request_remaining_bytes"] = request["remaining"]
            if request["remaining"] == 0:
                del self.pending_reads[key]
        self.trace.transaction(source, operation, packet["start_ps"], end_ps,
                               identifier=key, fields=info)
        self.counts[(source, operation)] += 1
        self.packet_count += 1

    def finish(self):
        """Strict acceptance: at least one write/read/completion, no dangling tags."""
        try:
            for source, packet in self.active.items():
                if packet is not None:
                    self.trace.transaction(source, "unfinished_tlp", packet["start_ps"],
                                           status="incomplete",
                                           fields={"accepted_beats": len(packet["beats"])})
                    raise AssertionError("TLP capture ended without EOP: " + source)
            if self.pending_reads:
                raise AssertionError("TLP reads without completed responses: " +
                                     ", ".join(sorted(self.pending_reads)))
            for source, operation in ((REQUEST, "mem_read"), (REQUEST, "mem_write"),
                                      (COMPLETION, "completion")):
                if self.counts[(source, operation)] < 1:
                    raise AssertionError(f"missing accepted PCIe TLP {source}/{operation}")
        except BaseException as exc:
            self.trace.close("fail", exc)
            raise
        self.trace.close("pass")


class LiveTlpCapture:
    """Cocotb task samples RTL ports passively; no activity is inferred."""
    def __init__(self, dut, plan_path=None):
        import cocotb
        self.dut = dut
        plan_path = Path(plan_path or os.environ["SOC_RUN_PLAN"])
        self.trace = open_from_plan(plan_path)
        if self.trace is None or set(self.trace.sources) != set(SOURCES):
            raise ValueError("PCIe0 TLP catalog must declare both bridge directions")
        for source in SOURCES:
            prefix = "rx_req_tlp" if source == REQUEST else "tx_cpl_tlp"
            for field_name in ("data", "hdr", "valid", "sop", "eop", "ready"):
                getattr(dut, prefix + "_" + field_name)  # Missing real signal fails closed.
            if source == COMPLETION:
                getattr(dut, prefix + "_strb")
        self.packets = AcceptedTlpPackets(self.trace)
        self.task = cocotb.start_soon(self.run())

    async def run(self):
        from cocotb.triggers import RisingEdge, ReadOnly
        from cocotb.utils import get_sim_time
        while True:
            await RisingEdge(self.dut.clk)
            await ReadOnly()
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
                    strobe=signal("strb") if source == COMPLETION else None,
                )

    def finish(self):
        self.task.kill()
        self.packets.finish()
        return dict((f"{source}/{operation}", count)
                    for (source, operation), count in self.packets.counts.items())
