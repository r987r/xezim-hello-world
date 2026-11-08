"""Regression for PCIe trace: use the PINNED upstream TLP/frame parser.

These tests exercise accepted handshake capture without driving an RTL bus.
The real full-chip test/CI supplies the DUT interface and actual AXI evidence.
"""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".tools/verilog_pcie/tb/pcie_axi_master"))
sys.path.insert(0, str(ROOT / "tools"))

# Other CI jobs intentionally do not fetch or install the optional pinned
# PCIe BFM. Keep test discovery importable, but require upstream for
# the dedicated real-PCIe job rather than substituting a custom parser.
HAS_UPSTREAM = (ROOT / ".tools/verilog_pcie/tb/pcie_axi_master/pcie_if.py").is_file()
if HAS_UPSTREAM:
    from pcie_if import PcieIfFrame
    from cocotbext.pcie.core.tlp import Tlp, TlpType
    from cocotbext.pcie.core.utils import PcieId
else:
    PcieIfFrame = Tlp = TlpType = PcieId = None
from dv.common.protocol_trace import ProtocolTrace
from dv.pcie0.tlp_trace import (AcceptedTlpPackets, REQUEST, COMPLETION, SOURCES,
    OUTBOUND_READ, OUTBOUND_WRITE, OUTBOUND_COMPLETION, OUTBOUND_SOURCES)
import protocol_report


def packets(sink, source, tlp, start_ps):
    frame = PcieIfFrame.from_tlp(tlp)
    # PcieIfFrame uses 32-bit DW payload, a 64-bit bridge beat.
    beats = max(1, (len(frame.data) + 1) // 2)
    for index in range(beats):
        dwords = frame.data[index * 2: index * 2 + 2]
        data = sum(int(dw) << (32 * lane) for lane, dw in enumerate(dwords))
        sink.beat(source, start_ps + index * 10000, valid=1, ready=1,
                  sop=int(index == 0), eop=int(index == beats - 1),
                  header=frame.hdr if index == 0 else 0, data=data,
                  strobe=(1 << len(dwords)) - 1 if source in (COMPLETION, OUTBOUND_COMPLETION, OUTBOUND_WRITE) else None)
    return start_ps + (beats - 1) * 10000


@unittest.skipUnless(HAS_UPSTREAM, "pinned PCIe test BFM is not installed in this CI job")
class TestTlpCapture(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / "protocol-events.jsonl"
        self.trace = ProtocolTrace(self.output, SOURCES)
        self.monitor = AcceptedTlpPackets(self.trace, PcieIfFrame)

    def test_real_upstream_packets_and_shared_html(self):
        wr = Tlp()
        wr.fmt_type = TlpType.MEM_WRITE
        wr.requester_id = PcieId(0, 1, 0)
        wr.tag = 1
        wr.set_addr_be_data(0x12000100, b"ABCDEFGH")
        packets(self.monitor, REQUEST, wr, 10000)
        rd = Tlp()
        rd.fmt_type = TlpType.MEM_READ
        rd.requester_id = PcieId(0, 1, 0)
        rd.tag = 2
        rd.set_addr_be(0x12000100, 8)
        packets(self.monitor, REQUEST, rd, 40000)
        cpl = Tlp.create_completion_data_for_tlp(rd, PcieId(0, 0, 0))
        cpl.set_data(b"ABCDEFGH")
        cpl.byte_count = 8
        cpl.lower_address = rd.address & 0x7f
        packets(self.monitor, COMPLETION, cpl, 60000)
        self.monitor.finish()
        parsed = protocol_report.parse_capture(self.output, SOURCES)
        self.assertEqual([r["operation"] for r in parsed["records"]],
                         ["mem_write", "mem_read", "completion"])
        self.assertEqual(parsed["records"][0]["fields"]["address"], "0x12000100")
        self.assertEqual(parsed["records"][-1]["fields"]["request_remaining_bytes"], 0)
        plan = {"target":"chip-pcie-host", "engine":"cocotb-verilator",
                "report":{"protocols":{"sources":SOURCES}}}
        result = protocol_report.build(Path(self.tmp.name), plan)
        self.assertTrue(result["capture_complete"])
        self.assertIn("pcie", (Path(self.tmp.name)/"protocols.html").read_text())
        self.assertEqual(result["records"][-1]["fields"]["matched_request_address"], "0x12000100")

    def test_bidirectional_requesters_use_disjoint_tag_spaces(self):
        # Outbound device and inbound host may choose the same tag value.
        # Their completions must not be accidentally correlated across
        # opposite directions in a full-chip PCIe test.
        self.trace.close("pass")
        self.output.unlink()
        source_catalog = {**SOURCES, **OUTBOUND_SOURCES}
        trace = ProtocolTrace(self.output, source_catalog)
        monitor = AcceptedTlpPackets(trace, PcieIfFrame, outbound=True)
        requester = PcieId(0, 1, 0)
        host = PcieId(0, 0, 0)
        host_write = Tlp()
        host_write.fmt_type = TlpType.MEM_WRITE
        host_write.requester_id = host
        host_write.tag = 1
        host_write.set_addr_be_data(0x12000100, b"HOSTBYTS")
        packets(monitor, REQUEST, host_write, 10000)

        host_read = Tlp()
        host_read.fmt_type = TlpType.MEM_READ
        host_read.requester_id = host
        host_read.tag = 7
        host_read.set_addr_be(0x12000100, 8)
        packets(monitor, REQUEST, host_read, 20000)

        outbound_write = Tlp()
        outbound_write.fmt_type = TlpType.MEM_WRITE
        outbound_write.requester_id = requester
        outbound_write.tag = 9
        outbound_write.set_addr_be_data(0x20001000, b"DEVBYTES")
        packets(monitor, OUTBOUND_WRITE, outbound_write, 30000)

        outbound_read = Tlp()
        outbound_read.fmt_type = TlpType.MEM_READ
        outbound_read.requester_id = requester
        outbound_read.tag = 7
        outbound_read.set_addr_be(0x20002000, 8)
        packets(monitor, OUTBOUND_READ, outbound_read, 40000)

        for request, source, data, when in (
            (outbound_read, OUTBOUND_COMPLETION, b"HOSTMEM!", 50000),
            (host_read, COMPLETION, b"SRAMDATA", 60000),
        ):
            cpl = Tlp.create_completion_data_for_tlp(
                request, host if source == OUTBOUND_COMPLETION else requester)
            cpl.set_data(data)
            cpl.byte_count = 8
            cpl.lower_address = request.address & 0x7f
            packets(monitor, source, cpl, when)
        monitor.finish()
        parsed = protocol_report.parse_capture(self.output, source_catalog)
        self.assertEqual(len(parsed["records"]), 6)
        types = [(x["source"], x["operation"]) for x in parsed["records"]]
        self.assertIn((OUTBOUND_WRITE, "mem_write"), types)
        self.assertIn((OUTBOUND_READ, "mem_read"), types)
        self.assertIn((OUTBOUND_COMPLETION, "completion"), types)
        cpls = [x for x in parsed["records"] if x["operation"] == "completion"]
        self.assertEqual({x["fields"]["matched_request_address"] for x in cpls},
                         {"0x12000100", "0x20002000"})

    def test_outbound_missing_completion_rejected(self):
        self.trace.close("pass")
        self.output.unlink()
        catalog = {**SOURCES, **OUTBOUND_SOURCES}
        trace = ProtocolTrace(self.output, catalog)
        monitor = AcceptedTlpPackets(trace, PcieIfFrame, outbound=True)
        rd = Tlp()
        rd.fmt_type = TlpType.MEM_READ
        rd.requester_id = PcieId(0, 1, 0)
        rd.tag = 2
        rd.set_addr_be(0x20002000, 8)
        packets(monitor, OUTBOUND_READ, rd, 10000)
        with self.assertRaisesRegex(AssertionError, "dangling"):
            monitor.finish()
        with self.assertRaisesRegex(ValueError, "ended with failure"):
            protocol_report.parse_capture(self.output, catalog)

    def test_missing_completion_fails_closed(self):
        rd = Tlp()
        rd.fmt_type = TlpType.MEM_READ
        rd.requester_id = PcieId(0, 1, 0)
        rd.tag = 2
        rd.set_addr_be(0x12000100, 4)
        packets(self.monitor, REQUEST, rd, 10000)
        with self.assertRaisesRegex(AssertionError, "dangling"):
            self.monitor.finish()
        with self.assertRaisesRegex(ValueError, "ended with failure"):
            protocol_report.parse_capture(self.output, SOURCES)

    def test_valid_not_ready_not_counted(self):
        wr = Tlp()
        wr.fmt_type = TlpType.MEM_WRITE
        wr.requester_id = PcieId(0, 1, 0)
        wr.set_addr_be_data(0x12000100, b"ABCD")
        frame = PcieIfFrame.from_tlp(wr)
        self.monitor.beat(REQUEST, 10000, valid=1, ready=0, sop=1, eop=1,
                          header=frame.hdr, data=0x44434241)
        self.assertFalse(self.monitor.counts)
        with self.assertRaisesRegex(AssertionError, "evidence missing"):
            self.monitor.finish()


if __name__ == "__main__":
    unittest.main()
