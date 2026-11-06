"""Real CPU0 compiled C owns Ethernet queue/CSR/CQ while GMII VIP is wire-only.

The existing cold-boot PicoRV32 and SERV boot, firmware C hook, actual
Data/Config FlooNoCs and passive AXI monitors are reused unchanged.
No CPU0 AXI BFM, zero SRAM preload and no testbench CQ/IRQ pulses.
"""
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge,Timer,with_timeout
from cocotb.utils import get_sim_time
from cocotbext.eth import GmiiSource,GmiiSink,GmiiFrame

from dv.ethernet0.frame_contract import Packet,encode
from dv.ethernet0.gmii_trace import GmiiEvidence,RX,TX
from dv.common.protocol_trace import open_from_plan
from dv.common.axi_trace import attach_observers,trace_phase
from dv.full_chip.test_boot import phase

ROOT=Path(__file__).resolve().parents[2]
READY=0xe7000001
PASS=0xe700600d

def packet():
    return encode(Packet(
        src_mac=bytes.fromhex('0250b6000011'),
        dst_mac=bytes.fromhex('0250b6000022'),
        src_ip='10.20.30.40',dst_ip='10.20.30.41',
        src_port=12345,dst_port=6000,
        payload=bytes((i*7+9)&255 for i in range(43))))[:-4]

async def wait_cpu_marker(dut,expected):
    for _ in range(270000):
        observed=int(dut.cpu_dma_evidence.value)
        if observed==expected:
            return
        if (observed&0xfffff000)==0xe700f000:
            raise AssertionError(f'CPU0 C Ethernet error code {observed:#x}')
        await RisingEdge(dut.clk)
    raise AssertionError(f'CPU0 C never emitted {expected:#x}, last={int(dut.cpu_dma_evidence.value):#x}')

def verify_accepted_axi(plan):
    records=Path(plan).parent/'axi-events.jsonl'
    assert records.is_file(),'passive AXI observations missing'
    matched={key:0 for key in (
        'cpu_cfg_aw','cpu_cfg_ar','cpu_desc_aw','cpu_cq_ar',
        'ethernet_pkt_aw','ethernet_pkt_ar',
        'ethernet_cq_b','ethernet_cfg_aw'
    )}
    for line in records.read_text().splitlines():
        e=json.loads(line)
        channel=e.get('channel')
        monitor=e.get('monitor')
        fields=e.get('fields',{})
        address=int(fields.get('addr','0x0'),16)
        if monitor=='compute0_local_config.cpu':
            if channel=='aw' and 0x40050000<=address<0x40050100:
                matched['cpu_cfg_aw']+=1
            if channel=='ar' and 0x40050000<=address<0x40050100:
                matched['cpu_cfg_ar']+=1
        if monitor=='compute0_local_data.cpu':
            if channel=='aw' and 0x13001000<=address<0x13002160:
                matched['cpu_desc_aw']+=1
            if channel=='ar' and 0x13001200<=address<0x13001620:
                matched['cpu_cq_ar']+=1
        if monitor=='ethernet0_local_data.packet_dma':
            if channel=='aw' and 0x13002000<=address<0x13002100:
                matched['ethernet_pkt_aw']+=1
            if channel=='ar' and 0x13002100<=address<0x13002160:
                matched['ethernet_pkt_ar']+=1
            if channel=='b':
                matched['ethernet_cq_b']+=1
        if monitor=='ethernet0_local_config.controller_regs' and channel=='aw':
            matched['ethernet_cfg_aw']+=1
    assert all(value>0 for value in matched.values()),(
        f'CPU0 C Ethernet missing true AXI accepted events: {matched}')
    return matched


@cocotb.test(timeout_time=12,timeout_unit='ms')
async def cpu0_c_programs_real_rx_tx_queue_and_checks_cq(dut):
    assert os.environ.get('SOC_ETHERNET_CPU_MODE')=='1'
    assert os.environ.get('SOC_CPU_DMA_MODE')=='1'
    assert os.environ.get('SOC_RUN_PLAN')
    dut.rst_n.value=0
    dut.clk.value=0
    dut.gmii_rx_clk.value=0
    dut.gmii_tx_clk.value=0
    dut.gmii_rx_rst.value=1
    dut.gmii_tx_rst.value=1
    dut.gmii_rxd.value=0
    dut.gmii_rx_dv.value=0
    dut.gmii_rx_er.value=0
    attach_observers(dut)
    protocol_trace=open_from_plan()
    gmii_evidence=GmiiEvidence(protocol_trace)
    cocotb.start_soon(Clock(dut.clk,10,units='ns').start())
    cocotb.start_soon(Clock(dut.gmii_rx_clk,8,units='ns').start())
    cocotb.start_soon(Clock(dut.gmii_tx_clk,8,units='ns').start())
    gmii_src=GmiiSource(dut.gmii_rxd,dut.gmii_rx_er,dut.gmii_rx_dv,
                        dut.gmii_rx_clk,dut.gmii_rx_rst)
    gmii_sink=GmiiSink(dut.gmii_txd,dut.gmii_tx_er,dut.gmii_tx_en,
                       dut.gmii_tx_clk,dut.gmii_tx_rst)
    for _ in range(15):
        await FallingEdge(dut.clk)
    dut.gmii_rx_rst.value=0
    dut.gmii_tx_rst.value=0
    dut.rst_n.value=1
    await phase(dut,dut.init_complete,'init')
    trace_phase('INIT: real PicoRV32 and SERV boot, no CPU BFM')
    await wait_cpu_marker(dut,READY)
    trace_phase('RUN: CPU0 C installed descriptors, policy, queue and IRQ CSR')
    frame=packet()
    assert len(frame)==85
    await gmii_src.send(GmiiFrame.from_payload(frame))
    await gmii_src.wait()
    gmii_evidence.packet(RX,frame)
    observed=await with_timeout(gmii_sink.recv(),5,'ms')
    assert bytes(observed.get_payload())==frame,'CPU0 C TX descriptor produced wrong GMII bytes'
    assert observed.check_fcs(),'TX physical GMII missing correct FCS'
    assert observed.error is None,'GMII TX error indication'
    gmii_evidence.packet(TX,observed.get_payload(),fcs_valid=observed.check_fcs(),error=observed.error)
    trace_phase('CHECK: external GMII received exact CPU-owned TX payload and FCS')
    await wait_cpu_marker(dut,PASS)
    await phase(dut,dut.run_complete,'run')
    await phase(dut,dut.check_complete,'check')
    await Timer(1,units='us')
    assert int(dut.pass_flag.value)==1,'real cold-boot CHECK did not retire'
    assert int(dut.cpu_dma_success.value)==1,'C firmware evidence not accepted'
    assert int(dut.cpu_dma_evidence.value)==PASS
    assert int(dut.eth_irq.value)==0,'C did not ack both IRQ causes'
    assert int(dut.eth_tx_failed.value)==0,'TX completion writer failed'
    assert int(dut.eth_bad_fcs.value)==0,'bad GMII RX FCS'
    assert int(dut.app_fetch.value)==3,'both CPUs must fetch real SRAM firmware'
    counts=verify_accepted_axi(os.environ['SOC_RUN_PLAN'])
    dut._log.info('CPU_ETHERNET_ACCEPTED_AXI=%s',counts)
    gmii_evidence.finish()
    protocol_trace.close("pass")
    dut._log.info('PASS ethernet-cpu: real CPU0 C queue and CQ; GMII RX/TX, SRAM bytes, IRQ ack, B-gated CQ and shared cold boot')
