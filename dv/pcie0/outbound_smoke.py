"""Real outbound PCIe requester transactions against independently checked host RAM.

This is an isolated pinned dma_if_pcie RTL test.  It does not claim that the
segmented RAM port is yet connected to the generated SoC AXI/iDMA fabric.
"""
import json
import os
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, with_timeout
from cocotbext.pcie.core import RootComplex
from cocotbext.axi.stream import define_stream

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / ".tools/verilog_pcie"
sys.path.insert(0, str(VENDOR / "tb/pcie_axi_master"))
sys.path.insert(0, str(VENDOR / "tb/dma_if_pcie_wr"))
from pcie_if import PcieIfDevice, PcieIfRxBus, PcieIfTxBus
from dma_psdp_ram import PsdpRam, PsdpRamBus

DescBus, DescTransaction, DescSource, _, _ = define_stream(
    "Desc", signals=["pcie_addr", "ram_addr", "ram_sel", "len", "tag", "valid", "ready"])
WriteDescBus, WriteDescTransaction, WriteDescSource, _, _ = define_stream(
    "WriteDesc", signals=["pcie_addr", "ram_addr", "ram_sel", "imm", "imm_en",
                           "len", "tag", "valid", "ready"])
StatusBus, _, _, StatusSink, _ = define_stream(
    "Status", signals=["tag", "error", "valid"])


async def accepted_tlp_counts(dut, counts):
    while True:
        await RisingEdge(dut.clk)
        for name, signal in (
            ("tx_mem_write_tlps", "tx_wr_req_tlp"),
            ("tx_mem_read_tlps", "tx_rd_req_tlp"),
        ):
            if int(getattr(dut, signal + "_valid").value) and int(
                    getattr(dut, signal + "_ready").value) and int(
                    getattr(dut, signal + "_sop").value):
                counts[name] += 1
        if int(dut.rx_cpl_tlp_valid.value) and int(
                dut.rx_cpl_tlp_ready.value) and int(dut.rx_cpl_tlp_sop.value):
            counts["rx_completion_tlps"] += 1


async def wait_host_bytes(mem, at, expected, clk):
    for _ in range(5000):
        if bytes(mem[at:at+len(expected)]) == expected:
            return
        await RisingEdge(clk)
    raise AssertionError(f"host DMA write timeout or corrupted bytes at {at:#x}")


@cocotb.test()
async def outbound_bidirectional_real_tlps(dut):
    cocotb.start_soon(Clock(dut.clk, 4, units="ns").start())
    dut.rst.value = 1
    dut.s_axis_rd_req_tx_seq_num.value = 0
    dut.s_axis_rd_req_tx_seq_num_valid.value = 0
    dut.s_axis_wr_req_tx_seq_num.value = 0
    dut.s_axis_wr_req_tx_seq_num_valid.value = 0
    dut.read_enable.value = 0
    dut.write_enable.value = 0
    dut.ext_tag_enable.value = 0
    dut.rcb_128b.value = 0
    dut.requester_id.value = 0
    dut.max_read_request_size.value = 0
    dut.max_payload_size.value = 0
    dut.s_axis_read_desc_valid.value = 0
    dut.s_axis_write_desc_valid.value = 0
    await Timer(32, units="ns")
    dut.rst.value = 0

    rc = RootComplex()
    endpoint = PcieIfDevice(
        clk=dut.clk, rst=dut.rst,
        tx_wr_req_tlp_bus=PcieIfTxBus.from_prefix(dut, "tx_wr_req_tlp"),
        tx_rd_req_tlp_bus=PcieIfTxBus.from_prefix(dut, "tx_rd_req_tlp"),
        rx_cpl_tlp_bus=PcieIfRxBus.from_prefix(dut, "rx_cpl_tlp"),
        cfg_max_read_req=dut.max_read_request_size,
        cfg_max_payload=dut.max_payload_size,
        cfg_ext_tag_enable=dut.ext_tag_enable,
        cfg_rcb=dut.rcb_128b,
    )
    rc.make_port().connect(endpoint)
    ram = PsdpRam(PsdpRamBus.from_prefix(dut, "ram"), dut.clk, dut.rst, size=2**16)

    read_source = DescSource(DescBus.from_prefix(dut, "s_axis_read_desc"), dut.clk, dut.rst)
    write_source = WriteDescSource(
        WriteDescBus.from_prefix(dut, "s_axis_write_desc"), dut.clk, dut.rst)
    read_status = StatusSink(
        StatusBus.from_prefix(dut, "m_axis_read_desc_status"), dut.clk, dut.rst)
    write_status = StatusSink(
        StatusBus.from_prefix(dut, "m_axis_write_desc_status"), dut.clk, dut.rst)

    counts = {"tx_mem_write_tlps": 0, "tx_mem_read_tlps": 0,
              "rx_completion_tlps": 0, "host_bytes_verified": 0,
              "device_bytes_verified": 0}
    cocotb.start_soon(accepted_tlp_counts(dut, counts))

    await with_timeout(rc.enumerate(), 250, "us")
    device = rc.find_device(endpoint.functions[0].pcie_id)
    assert device is not None, "Root Complex did not enumerate the endpoint"
    await with_timeout(device.enable_device(), 100, "us")
    await with_timeout(device.set_master(), 100, "us")
    dut.requester_id.value = endpoint.bus_num << 8

    host = rc.mem_pool.alloc_region(1 << 20)
    host_base = host.get_absolute_address(0)
    dut.read_enable.value = 1
    dut.write_enable.value = 1

    # Include unaligned source/destination and two 4KiB boundary crossings.
    # Both directions use actual RTL and the host Root Complex memory pool.
    vectors = [
        (0x200, 0x400, 17),
        (0x605, 0x801, 64),
        (0x900, 0xff7, 257),
        (0x1403, 0x1ffb, 1031),
    ]
    for index, (local_addr, host_off, length) in enumerate(vectors):
        payload = bytes(((index * 73 + i * 29) ^ (i >> 2)) & 0xff
                        for i in range(length))
        guard = 0x5a
        ram.write(local_addr-1, bytes([guard]) + payload + bytes([guard]))
        host[host_off-1:host_off+length+1] = bytes([0xa5]) * (length+2)
        await with_timeout(write_source.send(WriteDescTransaction(
            pcie_addr=host_base+host_off, ram_addr=local_addr,
            ram_sel=0, imm=0, imm_en=0, len=length, tag=index+1)), 100, "us")
        status = await with_timeout(write_status.recv(), 200, "us")
        assert int(status.tag) == index+1 and int(status.error) == 0, (
            f"write DMA status vector {index}: {status}")
        await with_timeout(wait_host_bytes(host, host_off, payload, dut.clk),
                           200, "us")
        assert bytes(host[host_off-1:host_off+length+1]) == (
            bytes([0xa5]) + payload + bytes([0xa5])), "host buffer guard overwritten"
        assert ram.read(local_addr-1, length+2) == (
            bytes([0x5a]) + payload + bytes([0x5a])), "local source altered during DMA"
        counts["host_bytes_verified"] += length

        # Replace local RAM with sentinels, then DMA back from host over
        # actual PCIe memory-read requests and completion TLPs.
        ram.write(local_addr-1, bytes([guard]) * (length+2))
        await with_timeout(read_source.send(DescTransaction(
            pcie_addr=host_base+host_off, ram_addr=local_addr,
            ram_sel=0, len=length, tag=0x41+index)), 100, "us")
        read_done = await with_timeout(read_status.recv(), 200, "us")
        assert int(read_done.tag) == 0x41+index and int(read_done.error) == 0, (
            f"read DMA status vector {index}: {read_done}")
        assert ram.read(local_addr-1, length+2) == (
            bytes([0x5a]) + payload + bytes([0x5a])), "DMA read bytes or RAM guard mismatch"
        counts["device_bytes_verified"] += length

    assert counts["tx_mem_write_tlps"] >= len(vectors), "no real posted outbound writes"
    assert counts["tx_mem_read_tlps"] >= len(vectors), "no real outbound read requests"
    assert counts["rx_completion_tlps"] >= len(vectors), "no real inbound completions"
    assert not int(dut.status_error_cor.value), "PCIe correctable status set"
    assert not int(dut.status_error_uncor.value), "PCIe uncorrectable status set"

    counts.update(passed=True, vectors=len(vectors),
                  vendor_pin="25156a9a162c41c60f11f41590c7d006d015ae5a",
                  scope="isolated dma_if_pcie + segmented RAM + modeled RC; no SoC AXI/iDMA")
    output = Path(os.environ["SOC_PCIE_OUTBOUND_RESULT"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(counts, indent=2, sort_keys=True) + "\n")
    dut._log.info("PASS PCIE0_OUTBOUND_REQUESTER_REAL_TLP %s", counts)
