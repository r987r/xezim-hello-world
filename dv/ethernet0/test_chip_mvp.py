"""Real GMII RX/TX ↔ Ethernet0 local/global Data/Config NoCs.

CPU0 data/config AXI BFMs drive existing CPU ports while CPUs are held reset,
as in the shared chip-dma test. Not a CPU C firmware or PCIe endpoint test.
All buffers, queue registers and CQ records use actual frontdoor AXI.
"""
import json
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge,with_timeout
from cocotbext.axi import AxiBus,AxiMaster
from cocotbext.eth import GmiiSource,GmiiSink,GmiiFrame
from dv.ethernet0.frame_contract import Packet,encode
from dv.ethernet0.gmii_trace import GmiiEvidence,RX,TX
from dv.common.axi_trace import attach_observers,trace_phase
from dv.full_chip.test_dma import bounded,check_ok,write_word,read_word

ETH_SRAM=0x13000000
ETH_CTRL=0x40050000
DDR_BASE=0x140000000
RX_RING=ETH_SRAM+0x1000
RX_CQ=ETH_SRAM+0x1200
TX_RING=ETH_SRAM+0x1400
TX_CQ=ETH_SRAM+0x1600
DATA_BUF=ETH_SRAM+0x2000


async def d_write(master,addr,payload,label):
    result=await bounded(master.write(addr,payload),label)
    await check_ok(result,label)


async def d_read(master,addr,length,label):
    result=await bounded(master.read(addr,length),label)
    await check_ok(result,label)
    return bytes(result.data)


async def descriptor(master,base,buffer,capacity,cookie,region=0):
    # Four actual AXI SRAM writes; no direct RAM preload or done pulse.
    words=[
        buffer,
        (cookie<<32)|capacity,
        region<<32,
        0,
    ]
    for i,w in enumerate(words):
        await d_write(master,base+i*8,w.to_bytes(8,'little'),
                      f'descriptor AW/W/B at {base+i*8:#x}')


async def csr_init(cfg):
    for addr,val in (
        (0x20,RX_RING & 0xffffffff),(0x24,RX_RING>>32),
        (0x30,RX_CQ & 0xffffffff),(0x34,RX_CQ>>32),
        (0x40,TX_RING & 0xffffffff),(0x44,TX_RING>>32),
        (0x50,TX_CQ & 0xffffffff),(0x54,TX_CQ>>32),
        (0x74,0x0800),(0x78,0xffff),(0x7c,6000),(0x80,0xffff),
        (0x84,3),(0x08,3)):
        await write_word(cfg,ETH_CTRL+addr,val)


async def poll(cfg,clock,offset,value,label):
    for _ in range(150):
        actual=await read_word(cfg,ETH_CTRL+offset)
        if actual==value:
            return
        await RisingEdge(clock)
    raise AssertionError(f'{label}: CSR {offset:#x} expected {value} got {actual}')


async def cq_check(data,base,cookie,length,queue,label):
    raw=await d_read(data,base,32,label+' CQ AXI read')
    words=[int.from_bytes(raw[i:i+8],'little') for i in (0,8,16,24)]
    expect=[cookie,length,queue<<32,0]
    assert words==expect,f'{label}: bad 32-byte CQ {words!r} expected {expect!r}'


@cocotb.test(timeout_time=12,timeout_unit="ms")
async def gmii_rx_tx_through_real_eth_local_and_global_nocs(dut):
    dut.rst_ni.value=0
    dut.clk_i.value=0
    dut.gmii_rx_rst.value=1
    dut.gmii_tx_rst.value=1
    dut.gmii_rxd.value=0
    dut.gmii_rx_dv.value=0
    dut.gmii_rx_er.value=0
    attach_observers(dut)
    gmii_evidence=GmiiEvidence()
    cocotb.start_soon(Clock(dut.clk_i,10,units='ns').start())
    cocotb.start_soon(Clock(dut.gmii_rx_clk,8,units='ns').start())
    cocotb.start_soon(Clock(dut.gmii_tx_clk,8,units='ns').start())
    gmii_src=GmiiSource(dut.gmii_rxd,dut.gmii_rx_er,dut.gmii_rx_dv,
                        dut.gmii_rx_clk,dut.gmii_rx_rst)
    gmii_dst=GmiiSink(dut.gmii_txd,dut.gmii_tx_er,dut.gmii_tx_en,
                      dut.gmii_tx_clk,dut.gmii_tx_rst)
    data=AxiMaster(AxiBus.from_prefix(dut,'cpu0_data_bfm'),dut.clk_i,
                   dut.rst_ni,reset_active_level=False)
    cfg=AxiMaster(AxiBus.from_prefix(dut,'cpu0_config_bfm'),dut.clk_i,
                  dut.rst_ni,reset_active_level=False)
    for _ in range(20):
        await FallingEdge(dut.clk_i)
    dut.gmii_rx_rst.value=0
    dut.gmii_tx_rst.value=0
    dut.rst_ni.value=1
    for _ in range(20):
        await RisingEdge(dut.clk_i)

    p=Packet(
        src_mac=bytes.fromhex('0250b6000011'),
        dst_mac=bytes.fromhex('0250b6000022'),
        src_ip='10.20.30.40',dst_ip='10.20.30.41',
        src_port=12345,dst_port=6000,
        payload=bytes((i*7+9)&255 for i in range(43)))
    frame=encode(p)[:-4]
    assert len(frame)==85
    await csr_init(cfg)
    assert await read_word(cfg,ETH_CTRL+0x38)==0
    assert await read_word(cfg,ETH_CTRL+0x58)==0

    trace_phase('RUN ETH_RX_SRAM')
    await descriptor(data,RX_RING,DATA_BUF,2048,0xc0febabe)
    await write_word(cfg,ETH_CTRL+0x28,1)
    await gmii_src.send(GmiiFrame.from_payload(frame))
    await gmii_src.wait()
    gmii_evidence.packet(RX,frame)
    await poll(cfg,dut.clk_i,0x38,1,'RX to SRAM completion')
    trace_phase('CHECK ETH_RX_SRAM')
    got=await d_read(data,DATA_BUF,len(frame),'independent AXI SRAM readback')
    assert got==frame,'GMII RX to SRAM data mismatch'
    await cq_check(data,RX_CQ,0xc0febabe,len(frame),0,'RX SRAM')
    assert await read_word(cfg,ETH_CTRL+0x2c)==1,'RX descriptor did not retire'
    assert int(dut.eth_irq.value)==1,'RX IRQ missing'

    trace_phase('RUN ETH_RX_MODELED_DDR')
    ddr_target=DDR_BASE+0x800
    await descriptor(data,RX_RING+32,ddr_target,2048,0xdd00dd00,region=1)
    await write_word(cfg,ETH_CTRL+0x28,2)
    await gmii_src.send(GmiiFrame.from_payload(frame))
    await gmii_src.wait()
    gmii_evidence.packet(RX,frame)
    await poll(cfg,dut.clk_i,0x38,2,'RX to modeled DDR completion')
    trace_phase('CHECK ETH_RX_MODELED_DDR')
    got=await d_read(data,ddr_target,len(frame),'DDR readback through full NoC')
    assert got==frame,'GMII RX to DDR data mismatch'
    await cq_check(data,RX_CQ+32,0xdd00dd00,len(frame),0,'RX DDR')

    trace_phase('RUN ETH_TX_SRAM_GMII')
    await d_write(data,DATA_BUF+0x100,frame,'TX source SRAM')
    await descriptor(data,TX_RING,DATA_BUF+0x100,len(frame),0xfeedcafe)
    await write_word(cfg,ETH_CTRL+0x48,1)
    tx=await with_timeout(gmii_dst.recv(),250,'us')
    assert bytes(tx.get_payload())==frame,'TX SRAM to GMII byte mismatch'
    assert tx.check_fcs() and tx.error is None,'TX SRAM GMII FCS/error'
    gmii_evidence.packet(TX,tx.get_payload(),fcs_valid=tx.check_fcs(),error=tx.error)
    await poll(cfg,dut.clk_i,0x58,1,'TX SRAM completion')
    trace_phase('CHECK ETH_TX_SRAM_GMII')
    await cq_check(data,TX_CQ,0xfeedcafe,len(frame),1,'TX SRAM')

    trace_phase('RUN ETH_TX_DDR_GMII')
    await descriptor(data,TX_RING+32,ddr_target,len(frame),0x55aa55aa,region=1)
    await write_word(cfg,ETH_CTRL+0x48,2)
    tx=await with_timeout(gmii_dst.recv(),250,'us')
    assert bytes(tx.get_payload())==frame,'TX DDR to GMII mismatch'
    gmii_evidence.packet(TX,tx.get_payload(),fcs_valid=tx.check_fcs(),error=tx.error)
    assert tx.check_fcs() and tx.error is None,'TX DDR GMII FCS/error'
    await poll(cfg,dut.clk_i,0x58,2,'TX DDR completion')
    trace_phase('CHECK ETH_TX_DDR_GMII')
    await cq_check(data,TX_CQ+32,0x55aa55aa,len(frame),1,'TX DDR')

    # No extra descriptor posted: wire ingress cannot silently overwrite
    # a stale buffer or synthesize a completion without real packet B.
    trace_phase('RUN ETH_UNPOSTED_RX_NEGATIVE')
    await gmii_src.send(GmiiFrame.from_payload(frame))
    await gmii_src.wait()
    gmii_evidence.packet(RX,frame)
    for _ in range(150):
        await RisingEdge(dut.clk_i)
    assert await read_word(cfg,ETH_CTRL+0x38)==2,'unposted RX generated CQ'
    trace_phase('CHECK ETH_UNPOSTED_RX_NEGATIVE')
    assert int(dut.eth_tx_failed.value)==0,'unexpected TX CQ error'
    gmii_evidence.finish()
    dut._log.info('PASS chip-ethernet: real GMII RX SRAM+DDR and TX SRAM+DDR through generated Ethernet0 Data/Config FlooNoCs with exact CQ AXI B and BFM observability')
