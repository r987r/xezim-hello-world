#!/usr/bin/env python3
"""Pin-qualified *standalone test-only* OpenPCIe Cocotb timing adapter.

The normal RTL default stays SIM_FAST_LINK=0. This alters ONLY the ignored
upstream FuseSoC self-test checkout; cross-provider tests get their own
explicit -GSIM_FORCE_FAST_LTSSM=1 already. Do not represent this as a
production IP patch, force state, or qualify host ↔ endpoint L0.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

SOURCES = {
    "pcie_phy.core": "283a8e4156f18368115037532dc19490a73d97bc",
    "verif/tests/test_pcie_core.py": "9592f1377c8ca42cde1dde08aa249190a4467593",
    "verif/sequences/pcie_enumeration_seq.py": "57c6591d4936b2f795a059b8df8dbc2648667df8",
    "verif/agents/pipe_agent/pipe_agent.py": "ae0dab3a77c6f3ce0427aecf7faf926cd6d535fc",
}
CORE_BEFORE = """  sim:
    flow: sim
    flow_options:
      tool : verilator
      cocotb_module : test_pcie_core
      timescale: 1ns/1ns
      verilator_options:
        - --trace-fst --trace-structs
        - -j 4
        - waiver.vlt
"""
CORE_AFTER = CORE_BEFORE.replace(
    "        - waiver.vlt\n",
    "        - waiver.vlt\n        - -GSIM_FAST_LINK=1\n")
TEST_BEFORE = "await with_timeout(self.test_all.start(),25000,'ns')"
TEST_AFTER = "await with_timeout(self.test_all.start(),250000,'ns')"

# A/B DIAGNOSTIC ONLY, applied to the detached upstream standalone self-test.
# The selected/checked-in SoC OpenPCIe RTL overlay is NOT changed here.
# Original source is checked against the exact locked Git blob; the working
# tree must already carry the reviewed 16-byte transmit credit fix.
CPLD_READY_REL = "src/dllp/tlp2dllp.sv"
CPLD_ORIGINAL_BLOB = "4971e61449f76ef5530288844b0937b936547ccb"
CPLD_ROUNDING = "data_credits_required = (data_length == '0) ? 16'd256 : ((data_length + 16'd3) >> 2);"
CPLD_READY_BEFORE = "        if (has_cplh_credit && has_cpld_credit) begin"
CPLD_READY_AFTER = "        if (has_cplh_credit && has_cpld_credit && tlp_axis_tready && skid_axis_tvalid) begin"

# Reuse the provider's original active PIPE decoder callback, rather than
# introducing an independent TLP/DLLP decoder. These events are emitted only
# when OpenPCIe's original pipe_monitor_bfm reconstructs a packet from
# phy_txdata/phy_txdatak. This is EP -> wire, not guaranteed host receipt.
# Keep the original UVM queues/callbacks unchanged.
PIPE_MONITOR_SOURCE = "verif/agents/pipe_agent/pipe_agent.py"
PIPE_MONITOR_TLP_BEFORE = """    def notify_tlp_received(self,tlp) :
        # Creating the sequnce item
        self.pipe_agent_config.tlp_received.append(tlp)"""
PIPE_MONITOR_TLP_AFTER = """    def notify_tlp_received(self,tlp) :
        # Existing PHY data/K monitor callback, not a new TLP decoder.
        # Cocotb's actual time is essential to the shared protocol timeline.
        observed_ps = int(cocotb.utils.get_sim_time(units="ps"))
        try:
            raw = bytes(int(v) & 0xff for v in tlp)
            print("PCIE_UPSTREAM_PIPE_MON_TLP: direction=EP_TO_RC time_ps=%d bytes=%d raw=%s" %
                  (observed_ps, len(raw), raw.hex()), flush=True)
        except (TypeError, ValueError):
            print("PCIE_UPSTREAM_PIPE_MON_TLP_UNDECODED: direction=EP_TO_RC time_ps=%d" %
                  observed_ps, flush=True)
        # Preserve original UVM queue/callback semantics exactly.
        self.pipe_agent_config.tlp_received.append(tlp)"""
PIPE_MONITOR_DLLP_BEFORE = """        self.pipe_agent_config.dllp_received.append(dllp)
        self.pipe_agent_config.dllp_data_detected_e.set()"""
PIPE_MONITOR_DLLP_AFTER = """        # Original PIPE monitor's decoded DLLP, not synthetic ACK/FC.
        observed_ps = int(cocotb.utils.get_sim_time(units="ps"))
        try:
            raw = bytes(int(v) & 0xff for v in dllp)
            print("PCIE_UPSTREAM_PIPE_MON_DLLP: direction=EP_TO_RC time_ps=%d bytes=%d raw=%s" %
                  (observed_ps, len(raw), raw.hex()), flush=True)
        except (TypeError, ValueError):
            print("PCIE_UPSTREAM_PIPE_MON_DLLP_UNDECODED: direction=EP_TO_RC time_ps=%d" %
                  observed_ps, flush=True)
        self.pipe_agent_config.dllp_received.append(dllp)
        self.pipe_agent_config.dllp_data_detected_e.set()"""


# Test-only passive RTL observation when the original CplD transmitter has
# been waiting for its first beat. Never synthesize credits, ACKs or packets.
CPLD_STALL_PROBE = """`ifndef SYNTHESIS
  logic [9:0] pcie_upstream_cpld_wait_r;
  always_ff @(posedge clk_i) begin
    if (rst_i || curr_state != ST_CHECK_CREDITS_CPLH_CPLD ||
        !skid_axis_tvalid || skid_axis_tready) begin
      pcie_upstream_cpld_wait_r <= '0;
    end else if (pcie_upstream_cpld_wait_r != 10'd1023) begin
      pcie_upstream_cpld_wait_r <= pcie_upstream_cpld_wait_r + 1'b1;
      if (pcie_upstream_cpld_wait_r == 10'd64 ||
          pcie_upstream_cpld_wait_r == 10'd512) begin
        $display("PCIE_UPSTREAM_CPLD_CREDIT_STALL: time=%0t cycles=%0d seq=%0d cplh_limit=%0d cplh_used=%0d cpld_limit=%0d cpld_used=%0d stream_ready=%b skid_valid=%b",
                 $time, pcie_upstream_cpld_wait_r, next_transmit_seq_r,
                 cplh_credit_limit_r, cplh_credits_consumed_r,
                 cpld_credit_limit_r, cpld_credits_consumed_r,
                 tlp_axis_tready, skid_axis_tvalid);
      end
    end
  end
`endif
"""

# The original memory regression is NOT shortened or made to pass. Only when
# its original 10us posted-write flush times out, sample the DUT's real AXIS
# handshake and link/FC state. This distinguishes source starvation, credit
# backpressure and a completion dropped downstream without inventing traffic.

# Additional *passive* model-side trace, restricted to the late BAR stress
# region to avoid flooding the original UVM log. It shows whether the
# independent Cocotb RC actually submitted the missing TLP to PIPE.
ENUM_MODEL_BEFORE = """                uvm_root().logger.info("Memory operation (32-bit BAR) length: %d offset: %d", length, offset)"""
ENUM_MODEL_AFTER = """                self._stall_diag_active = length >= 20
                uvm_root().logger.info("Memory operation (32-bit BAR) length: %d offset: %d", length, offset)"""
# The pinned cocotbext-pcie v0.2.16 RC intentionally rate-limits UpdateFC
# to 30us by default; the original BAR smoke test only waits 10us/read.
# Trial a faster *genuine* host UpdateFC cadence (real DLLPs on the original
# PHY link) without changing the endpoint credit limit or TLP byte oracle.
# Preserve original 30us value in the log and validate the pinned API.
ENUM_RC_FC_BEFORE = """        port = self.rc.make_port()
        port.connect(self.dev)"""
ENUM_RC_FC_AFTER = """        port = self.rc.make_port()
        port.connect(self.dev)
        # Real external root complex's original FC scheduler, not a credit
        # injection into DUT or BFM. Every update remains a host DLLP.
        host_port = self.dev.upstream_port.other
        original_fc_steps = cocotb.utils.get_sim_steps(30, 'us')
        assert host_port.fc_update_steps == original_fc_steps, (
            "original cocotbext-pcie 0.2.16 host FC scheduling API changed")
        host_port.fc_update_steps = cocotb.utils.get_sim_steps(1, 'us')
        print("PCIE_UPSTREAM_RC_FC_PROFILE: provider=cocotbext-pcie-0.2.16 "
              "default_us=30 selected_us=1 real_updatefc_dllp=1 "
              "no_credit_override=1", flush=True)"""

ENUM_HOST_FC_BEFORE = """        if isinstance(pkt,Dllp):
            pipe_seq_item_h.pipe_operation = pipe_operation_t.DLLP_TRANSFER
            pipe_seq_item_h.dllp = pkt
            await self.start_item (pipe_seq_item_h)
            await self.finish_item (pipe_seq_item_h)"""
ENUM_HOST_FC_AFTER = """        if isinstance(pkt,Dllp):
            if pkt.type == DllpType.UPDATE_FC_CPL:
                print("PCIE_UPSTREAM_RC_UPDATEFC_CPL_TX: time_ps=%d "
                      "hdr_fc=%d data_fc=%d" %
                      (int(cocotb.utils.get_sim_time(units="ps")),
                       pkt.hdr_fc, pkt.data_fc), flush=True)
            pipe_seq_item_h.pipe_operation = pipe_operation_t.DLLP_TRANSFER
            pipe_seq_item_h.dllp = pkt
            await self.start_item (pipe_seq_item_h)
            await self.finish_item (pipe_seq_item_h)
            if pkt.type == DllpType.UPDATE_FC_CPL:
                print("PCIE_UPSTREAM_RC_UPDATEFC_CPL_DONE: time_ps=%d "
                      "hdr_fc=%d data_fc=%d" %
                      (int(cocotb.utils.get_sim_time(units="ps")),
                       pkt.hdr_fc, pkt.data_fc), flush=True)"""

ENUM_HOST_BEFORE = """        elif isinstance(pkt,Tlp):
            tlp_pkt = pkt
            pipe_seq_item_h.pipe_operation = pipe_operation_t.TLP_TRANSFER
            pipe_seq_item_h.tlp = tlp_pkt
            await self.start_item (pipe_seq_item_h)
            await self.finish_item (pipe_seq_item_h)"""
ENUM_HOST_AFTER = """        elif isinstance(pkt,Tlp):
            tlp_pkt = pkt
            if getattr(self, "_stall_diag_active", False):
                print("PCIE_UPSTREAM_RC_TX_BEGIN: type=%s tag=%s length=%s addr=%s" %
                      (getattr(pkt, "fmt_type", "?"), getattr(pkt, "tag", "?"),
                       getattr(pkt, "length", "?"), getattr(pkt, "address", "?")),
                      flush=True)
            pipe_seq_item_h.pipe_operation = pipe_operation_t.TLP_TRANSFER
            pipe_seq_item_h.tlp = tlp_pkt
            await self.start_item (pipe_seq_item_h)
            await self.finish_item (pipe_seq_item_h)
            if getattr(self, "_stall_diag_active", False):
                print("PCIE_UPSTREAM_RC_TX_DONE: type=%s tag=%s" %
                      (getattr(pkt, "fmt_type", "?"), getattr(pkt, "tag", "?")),
                      flush=True)"""

ENUM_BEFORE = "                await dev_bar0.read(offset, 0, timeout=10000, timeout_unit='ns')"
ENUM_AFTER = """                try:
                    await dev_bar0.read(offset, 0, timeout=10000, timeout_unit='ns')
                except Exception:
                    dut = cocotb.top
                    values = {}
                    for name in ("s_tlp_axis_tvalid", "s_tlp_axis_tready",
                                 "m_tlp_axis_tvalid", "m_tlp_axis_tready",
                                 "fc_initialized_o", "link_up_o",
                                 "ltssm_debug_state"):
                        try:
                            values[name] = int(getattr(dut, name).value)
                        except (AttributeError, ValueError, TypeError):
                            values[name] = "unavailable"
                    print("PCIE_UPSTREAM_MEM_STALL: length=%d offset=%d "
                          "posted_write_flush=TIMEOUT dut=%r" %
                          (length, offset, values), flush=True)
                    # Passive snapshot of the ORIGINAL cocotbext-pcie FC
                    # accounting. No private counter writes, FC injections,
                    # timer changes or synthetic request/completion.
                    for owner, port in (("rc", self.dev.upstream_port.other),
                                        ("ep", self.dev.upstream_port)):
                        try:
                            vc = port.fc_state[0]
                            fc = {}
                            for kind in ("ph", "pd", "nph", "npd", "cplh", "cpld"):
                                channel = getattr(vc, kind)
                                fc[kind] = dict(
                                    tx_limit=int(channel.tx_credit_limit),
                                    tx_consumed=int(channel.tx_credits_consumed),
                                    tx_available=int(channel.tx_credits_available),
                                    rx_allocated=int(channel.rx_credits_allocated),
                                    rx_received=int(channel.rx_credits_received))
                            depth = port.tx_queue.qsize()
                            print("PCIE_UPSTREAM_FC_SNAPSHOT: owner=%s "
                                  "initialized=%s tx_queue_depth=%s vc0=%r" %
                                  (owner, port.fc_initialized, depth, fc),
                                  flush=True)
                        except (AttributeError, IndexError, TypeError, ValueError):
                            print("PCIE_UPSTREAM_FC_SNAPSHOT: owner=%s "
                                  "unavailable" % owner, flush=True)
                    raise"""


# Passive diagnostics for the original upstream payload readback, separate
# from the zero-length posted-write flush already traced above. Never change
# timeouts, returned data, TLP credits, or success predicates.
ENUM_READ_BEFORE = """                assert await dev_bar0.read(offset, length, timeout=10000, timeout_unit='ns') == test_data"""
ENUM_READ_AFTER = """                try:
                    readback = await dev_bar0.read(offset, length, timeout=10000, timeout_unit='ns')
                except Exception as exc:
                    print("PCIE_UPSTREAM_READBACK_TIMEOUT: length=%d offset=%d error=%r" %
                          (length, offset, exc), flush=True)
                    # Original DUT transmitter status, observed at failure.
                    # If Verilator does not expose an internal hierarchy
                    # member, print not_exposed instead of guessing a value.
                    rtl_paths = (
                        "s_tlp_axis_tvalid", "s_tlp_axis_tready",
                        "pcie_datalink_layer_inst.tx_tlp_tvalid",
                        "pcie_datalink_layer_inst.tx_tlp_tready",
                        "pcie_datalink_layer_inst.m_phy_axis_tvalid",
                        "pcie_datalink_layer_inst.m_phy_axis_tready",
                        "pcie_datalink_layer_inst.dllp_transmit_inst.tlp2dllp_inst.curr_state",
                        "pcie_datalink_layer_inst.dllp_transmit_inst.tlp2dllp_inst.skid_axis_tvalid",
                        "pcie_datalink_layer_inst.dllp_transmit_inst.tlp2dllp_inst.skid_axis_tready",
                        "pcie_datalink_layer_inst.dllp_transmit_inst.tlp2dllp_inst.tlp_axis_tvalid",
                        "pcie_datalink_layer_inst.dllp_transmit_inst.tlp2dllp_inst.tlp_axis_tready",
                        "pcie_datalink_layer_inst.dllp_transmit_inst.tlp2dllp_inst.cplh_credit_limit_r",
                        "pcie_datalink_layer_inst.dllp_transmit_inst.tlp2dllp_inst.cpld_credit_limit_r",
                        "pcie_datalink_layer_inst.dllp_transmit_inst.tlp2dllp_inst.cplh_credits_consumed_r",
                        "pcie_datalink_layer_inst.dllp_transmit_inst.tlp2dllp_inst.cpld_credits_consumed_r",
                        "pcie_datalink_layer_inst.dllp_transmit_inst.tlp2dllp_inst.next_transmit_seq_r",
                    )
                    snapshot = {}
                    for rtl_path in rtl_paths:
                        try:
                            handle = cocotb.top
                            for segment in rtl_path.split("."):
                                handle = getattr(handle, segment)
                            snapshot[rtl_path] = int(handle.value)
                        except (AttributeError, TypeError, ValueError):
                            snapshot[rtl_path] = "not_exposed"
                    print("PCIE_UPSTREAM_READBACK_RTL_SNAPSHOT: %r" %
                          snapshot, flush=True)
                    for owner, port in (("rc", self.dev.upstream_port.other),
                                        ("ep", self.dev.upstream_port)):
                        try:
                            vc = port.fc_state[0]
                            fc = {}
                            for kind in ("ph", "pd", "nph", "npd", "cplh", "cpld"):
                                channel = getattr(vc, kind)
                                fc[kind] = (int(channel.tx_credit_limit),
                                            int(channel.tx_credits_consumed),
                                            int(channel.tx_credits_available),
                                            int(channel.rx_credits_allocated),
                                            int(channel.rx_credits_received))
                            print("PCIE_UPSTREAM_READBACK_FC: owner=%s tx_queue=%d "
                                  "credit=(limit,used,available,rx_alloc,rx_recv) %r" %
                                  (owner, port.tx_queue.qsize(), fc), flush=True)
                        except (AttributeError, IndexError, TypeError, ValueError):
                            print("PCIE_UPSTREAM_READBACK_FC: owner=%s unavailable" %
                                  owner, flush=True)
                    try:
                        outstanding = [(i, q.qsize()) for i, q in
                                       enumerate(self.rc.rx_cpl_queues) if q.qsize()]
                        print("PCIE_UPSTREAM_READBACK_RC: tag_active=%r queued_cpl=%r" %
                              (self.rc.tag_active[:32], outstanding[:32]), flush=True)
                    except (AttributeError, TypeError, ValueError):
                        print("PCIE_UPSTREAM_READBACK_RC: unavailable", flush=True)
                    raise
                assert readback == test_data"""

# Original TestEndpoint produces CplD through this callback. Trace its
# actual payload/tag; a SEND_MAC_TLP driver event is not proof that a packet
# emerged from the endpoint PHY and reached the root complex.
ENUM_EP_CPL_BEFORE = """    async def send_tlp_mac(self,tlp):
        pipe_seq_item_h = pipe_seq_item("pipe_seq_item")
        pipe_seq_item_h.pipe_operation = pipe_operation_t.SEND_MAC_TLP
        pipe_seq_item_h.tlp = tlp
        await self.start_item (pipe_seq_item_h)
        await self.finish_item (pipe_seq_item_h)"""
ENUM_EP_CPL_AFTER = """    async def send_tlp_mac(self,tlp):
        if getattr(self, "_stall_diag_active", False):
            print("PCIE_UPSTREAM_EP_CPL_BEGIN: type=%s tag=%s length=%s byte_count=%s lower_addr=%s" %
                  (getattr(tlp, "fmt_type", "?"), getattr(tlp, "tag", "?"),
                   getattr(tlp, "length", "?"), getattr(tlp, "byte_count", "?"),
                   getattr(tlp, "lower_address", "?")), flush=True)
        pipe_seq_item_h = pipe_seq_item("pipe_seq_item")
        pipe_seq_item_h.pipe_operation = pipe_operation_t.SEND_MAC_TLP
        pipe_seq_item_h.tlp = tlp
        await self.start_item (pipe_seq_item_h)
        await self.finish_item (pipe_seq_item_h)
        if getattr(self, "_stall_diag_active", False):
            print("PCIE_UPSTREAM_EP_CPL_DRIVER_DONE: type=%s tag=%s" %
                  (getattr(tlp, "fmt_type", "?"), getattr(tlp, "tag", "?")),
                  flush=True)"""


def replace_once(text: str, before: str, after: str, label: str) -> str:
    if text.count(before) != 1:
        raise ValueError(f"{label}: pinned upstream self-test source changed")
    return text.replace(before, after, 1)


def patched(path: str, source: str) -> str:
    if path == PIPE_MONITOR_SOURCE:
        source = replace_once(source, PIPE_MONITOR_TLP_BEFORE,
                              PIPE_MONITOR_TLP_AFTER,
                              path + " original PIPE TLP monitor")
        return replace_once(source, PIPE_MONITOR_DLLP_BEFORE,
                            PIPE_MONITOR_DLLP_AFTER,
                            path + " original PIPE DLLP monitor")
    if path == CPLD_READY_REL:
        # A credit grant is not an accepted AXI beat. The original RTL can
        # consume the first CplD beat even when the downstream mux is stalled.
        if source.count(CPLD_ROUNDING) != 2:
            raise ValueError(f"{path}: reviewed credit overlay changed")
        if source.count("dllp_valid_o            = '0;") != 1:
            raise ValueError(f"{path}: experimental retry-enable drift")
        source = replace_once(source, CPLD_READY_BEFORE, CPLD_READY_AFTER,
                              path + " CplD accepted first beat")
        return replace_once(source, "\nendmodule\n",
                            "\n" + CPLD_STALL_PROBE + "endmodule\n",
                            path + " passive credit stall diagnostic")
    if path == "pcie_phy.core":
        return replace_once(source,CORE_BEFORE,CORE_AFTER,path)
    if path == "verif/tests/test_pcie_core.py":
        return replace_once(source,TEST_BEFORE,TEST_AFTER,path)
    if path == "verif/sequences/pcie_enumeration_seq.py":
        source = replace_once(source, ENUM_RC_FC_BEFORE, ENUM_RC_FC_AFTER,
                              path + " original RC legal FC schedule")
        source = replace_once(source, ENUM_HOST_FC_BEFORE, ENUM_HOST_FC_AFTER,
                              path + " original RC UpdateFC DLLP TX")
        source = replace_once(source, ENUM_MODEL_BEFORE, ENUM_MODEL_AFTER, path + " model progress")
        source = replace_once(source, ENUM_HOST_BEFORE, ENUM_HOST_AFTER, path + " RC packets")
        source = replace_once(source, ENUM_EP_CPL_BEFORE, ENUM_EP_CPL_AFTER,
                              path + " actual endpoint completion packets")
        source = replace_once(source, ENUM_READ_BEFORE, ENUM_READ_AFTER,
                              path + " real payload readback")
        return replace_once(source,ENUM_BEFORE,ENUM_AFTER,path)
    raise ValueError(f"unknown timing-source path {path}")


def apply(root:Path) -> None:
    for rel, expected in SOURCES.items():
        path=root/rel
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"original upstream timing input missing: {rel}")
        actual=subprocess.run(["git","-C",str(root),"hash-object",rel],
                              check=True,capture_output=True,text=True).stdout.strip()
        if actual!=expected:
            raise ValueError(f"original upstream {rel} drift: {actual} != {expected}")
        content=patched(rel,path.read_text())
        path.write_text(content)
        if rel == PIPE_MONITOR_SOURCE:
            print("OPENPCIE_SELFTEST_NATIVE_PIPE_MON: enabled original "
                  "OpenPCIe TLP/DLLP PHY callbacks (endpoint transmit)")
        elif rel == "verif/sequences/pcie_enumeration_seq.py":
            print("OPENPCIE_SELFTEST_RC_FC_A_B: source-pinned real host "
                  "UpdateFC_Cpl period=1us versus cocotbext-pcie default=30us; "
                  "no synthetic credits/timeout changes")
            print("OPENPCIE_SELFTEST_STALL_PROBE: read-only AXIS/FC snapshot "
                  "on original memory timeout, re-raise unchanged")
        else:
            print(f"OPENPCIE_SELFTEST_TIMING: pinned {rel}: "
                  "Gen1 LTSSM 512x acceleration, 250us explicit test timeout")
    # A/B experiment for an actual first-beat ready/valid bug. Applied only
    # to the original upstream standalone qualification checkout; no new
    # host packets, synthetic CplD, timeout changes, or PASS exemptions.
    original_blob = subprocess.run(
        ["git", "-C", str(root), "rev-parse", f"HEAD:{CPLD_READY_REL}"],
        check=True, capture_output=True, text=True).stdout.strip()
    if original_blob != CPLD_ORIGINAL_BLOB:
        raise ValueError(f"original upstream {CPLD_READY_REL} drift: "
                         f"{original_blob} != {CPLD_ORIGINAL_BLOB}")
    cpld_path = root / CPLD_READY_REL
    if not cpld_path.is_file() or cpld_path.is_symlink():
        raise ValueError(f"missing standalone upstream source {CPLD_READY_REL}")
    cpld_path.write_text(patched(CPLD_READY_REL, cpld_path.read_text()))
    print("OPENPCIE_SELFTEST_CPLD_READY_AB: test-only first-beat ready/valid "
          "guard and passive credit-stall probes on pinned RTL; "
          "original Cocotb byte oracle retained")
    print("OPENPCIE_SELFTEST_TIMING: TEST-ONLY; not production or dual-sided L0 evidence")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkout",required=True,type=Path)
    a=p.parse_args()
    apply(a.checkout)
