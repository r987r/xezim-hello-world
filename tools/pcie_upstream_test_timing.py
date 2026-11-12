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
    if path == "pcie_phy.core":
        return replace_once(source,CORE_BEFORE,CORE_AFTER,path)
    if path == "verif/tests/test_pcie_core.py":
        return replace_once(source,TEST_BEFORE,TEST_AFTER,path)
    if path == "verif/sequences/pcie_enumeration_seq.py":
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
        if rel == "verif/sequences/pcie_enumeration_seq.py":
            print("OPENPCIE_SELFTEST_STALL_PROBE: read-only AXIS/FC snapshot "
                  "on original memory timeout, re-raise unchanged")
        else:
            print(f"OPENPCIE_SELFTEST_TIMING: pinned {rel}: "
                  "Gen1 LTSSM 512x acceleration, 250us explicit test timeout")
    print("OPENPCIE_SELFTEST_TIMING: TEST-ONLY; not production or dual-sided L0 evidence")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkout",required=True,type=Path)
    a=p.parse_args()
    apply(a.checkout)
