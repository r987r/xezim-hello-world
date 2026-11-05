"""True GMII PHY peer -> real MAC FCS/CDC -> real frame FIFO -> header tap.

No DMA/SoC is instantiated in this test. Packet source is independent
cocotbext-eth GMII VIP and golden packets are independently Python-encoded.
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, with_timeout
from cocotbext.axi import AxiStreamBus, AxiStreamSink
from cocotbext.eth import GmiiFrame, GmiiSource
from dv.ethernet0.frame_contract import Packet, encode

async def setup(dut):
    dut.logic_rst.value=1
    dut.gmii_rx_rst.value=1
    dut.gmii_tx_rst.value=1
    dut.gmii_rxd.value=0
    dut.gmii_rx_dv.value=0
    dut.gmii_rx_er.value=0
    dut.meta_ready.value=0
    cocotb.start_soon(Clock(dut.gmii_rx_clk,8,units="ns").start())
    cocotb.start_soon(Clock(dut.gmii_tx_clk,8,units="ns").start())
    cocotb.start_soon(Clock(dut.logic_clk,10,units="ns").start())
    gmii=GmiiSource(dut.gmii_rxd,dut.gmii_rx_er,dut.gmii_rx_dv,
                    dut.gmii_rx_clk,dut.gmii_rx_rst)
    frames=AxiStreamSink(AxiStreamBus.from_prefix(dut,"rx_axis"),
                         dut.logic_clk,dut.logic_rst)
    await Timer(100,units="ns")
    dut.logic_rst.value=0
    dut.gmii_rx_rst.value=0
    dut.gmii_tx_rst.value=0
    for _ in range(20):
        await RisingEdge(dut.logic_clk)
    return gmii,frames

async def recv_meta(dut,length,ethertype,udp,udp_port=0):
    await with_timeout(RisingEdge(dut.meta_valid),350,"us")
    assert int(dut.meta_length.value)==length, "packet length miscounted"
    assert int(dut.meta_ethertype.value)==ethertype, "EtherType mismatch"
    assert bool(int(dut.meta_is_udp.value))==udp, "unsupported/valid UDP mismatch"
    if udp:
        assert int(dut.meta_udp_dst_port.value)==udp_port, "UDP port mismatch"
    dut.meta_ready.value=1
    await RisingEdge(dut.logic_clk)
    await Timer(1,units="ns")
    dut.meta_ready.value=0

@cocotb.test(timeout_time=3,timeout_unit="ms")
async def gmii_to_metadata_and_preserved_ethernet_bytes(dut):
    gmii,frames=await setup(dut)
    p=Packet(
        src_mac=bytes.fromhex("0250b6000011"),
        dst_mac=bytes.fromhex("0250b6000022"),
        src_ip="10.20.30.40",dst_ip="10.20.30.41",
        src_port=12345,dst_port=6000,
        payload=bytes((i*7+9)&255 for i in range(43)))
    valid=encode(p)[:-4]  # Full Ethernet frame without wire FCS
    assert len(valid)==85
    await gmii.send(GmiiFrame.from_payload(valid))
    await recv_meta(dut,85,0x0800,True,6000)
    out=await with_timeout(frames.recv(),350,"us")
    assert bytes(out.tdata)==valid, "MAC->stager altered received frame"
    assert out.tuser==0, "valid frame carried error marker"

    # ARP-ish Ethernet frame does not get accidentally marked as IPv4/UDP.
    arp=(bytes.fromhex("ffffffffffff0250b6000011")+
         b"\x08\x06"+bytes(range(46)))
    assert len(arp)==60
    await gmii.send(GmiiFrame.from_payload(arp))
    await recv_meta(dut,60,0x0806,False)
    out=await with_timeout(frames.recv(),350,"us")
    assert bytes(out.tdata)==arp, "non-IPv4 frame corrupted"
    assert frames.empty(), "duplicate frame buffered"
    dut._log.info("PASS real GMII->MAC->CDC->frame staging: UDP/ARP, 2 good packets")

@cocotb.test(timeout_time=2,timeout_unit="ms")
async def gmii_bad_fcs_never_becomes_policy_metadata(dut):
    gmii,frames=await setup(dut)
    bad_count=[0]
    async def monitor():
        while True:
            await RisingEdge(dut.gmii_rx_clk)
            bad_count[0]+=int(dut.rx_error_bad_fcs.value)
    task=cocotb.start_soon(monitor())
    payload=(bytes.fromhex("0250b60000220250b60000110800")+
             bytes(range(60)))
    bad=GmiiFrame.from_payload(payload)
    bad.data[-1]^=0x80
    await gmii.send(bad)
    await with_timeout(gmii.wait(),300,"us")
    for _ in range(100):
        await RisingEdge(dut.logic_clk)
    assert bad_count[0]>0,"real RX MAC failed to report bad FCS"
    assert int(dut.meta_valid.value)==0,"bad-FCS frame reached policy table"
    assert frames.empty(),"bad-FCS frame reached packet stream"
    task.kill()
    dut._log.info("PASS real GMII bad-FCS suppression before policy metadata")
