"""Real GMII RX -> real FCS/CDC/stager -> descriptor AXI ->
packet AXI SRAM -> real B-gated CQ AXI; not yet the NoC variant."""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer, with_timeout
from cocotbext.eth import GmiiSource, GmiiFrame
from dv.ethernet0.frame_contract import Packet, encode


async def rising_ready(clk, signal, name, limit=2000):
    for _ in range(limit):
        await RisingEdge(clk)
        if int(signal.value):
            return
    raise AssertionError(f"timeout waiting for {name}")


async def setup(dut):
    for n in ("logic_rst","gmii_rx_rst","gmii_tx_rst"):
        getattr(dut,n).value=1
    for n in (
        "gmii_rxd","gmii_rx_dv","gmii_rx_er","cfg_valid","cfg_write",
        "cfg_addr","cfg_wdata","desc_awaddr","desc_awvalid","desc_wdata",
        "desc_wvalid","desc_wlast","desc_bready","pkt_araddr",
        "pkt_arvalid","pkt_rready","cqr_araddr","cqr_arvalid",
        "cqr_rready","cq_release_b"
    ):
        getattr(dut,n).value=0
    dut.cfg_wstrb.value=15
    cocotb.start_soon(Clock(dut.logic_clk,10,units="ns").start())
    cocotb.start_soon(Clock(dut.gmii_rx_clk,8,units="ns").start())
    cocotb.start_soon(Clock(dut.gmii_tx_clk,8,units="ns").start())
    gmii=GmiiSource(dut.gmii_rxd,dut.gmii_rx_er,dut.gmii_rx_dv,
                    dut.gmii_rx_clk,dut.gmii_rx_rst)
    await Timer(100,units="ns")
    dut.logic_rst.value=0
    dut.gmii_rx_rst.value=0
    dut.gmii_tx_rst.value=0
    for _ in range(20):
        await RisingEdge(dut.logic_clk)
    return gmii


async def csr_write(dut,offset,value):
    await FallingEdge(dut.logic_clk)
    dut.cfg_addr.value=offset
    dut.cfg_wdata.value=value
    dut.cfg_write.value=1
    dut.cfg_valid.value=1
    await Timer(1,units="ns")
    assert int(dut.cfg_ready.value) and not int(dut.cfg_error.value), (
        f"CSR write rejected at {offset:#x}")
    await RisingEdge(dut.logic_clk)
    await FallingEdge(dut.logic_clk)
    dut.cfg_valid.value=0
    dut.cfg_write.value=0


async def csr_read(dut,offset):
    await FallingEdge(dut.logic_clk)
    dut.cfg_addr.value=offset
    dut.cfg_write.value=0
    dut.cfg_valid.value=1
    await Timer(1,units="ns")
    assert not int(dut.cfg_error.value),f"CSR read error {offset:#x}"
    out=int(dut.cfg_rdata.value)
    await FallingEdge(dut.logic_clk)
    dut.cfg_valid.value=0
    return out


async def descriptor_word(dut,addr,data):
    await FallingEdge(dut.logic_clk)
    dut.desc_awaddr.value=addr
    dut.desc_awvalid.value=1
    await rising_ready(dut.logic_clk,dut.desc_awready,"descriptor AW")
    await FallingEdge(dut.logic_clk)
    dut.desc_awvalid.value=0
    dut.desc_wdata.value=data
    dut.desc_wlast.value=1
    dut.desc_wvalid.value=1
    await rising_ready(dut.logic_clk,dut.desc_wready,"descriptor W")
    await FallingEdge(dut.logic_clk)
    dut.desc_wvalid.value=0
    dut.desc_wlast.value=0
    dut.desc_bready.value=1
    await rising_ready(dut.logic_clk,dut.desc_bvalid,"descriptor B")
    assert int(dut.desc_bresp.value)==0,"descriptor SRAM B response error"
    await FallingEdge(dut.logic_clk)
    dut.desc_bready.value=0


async def read_word(dut,prefix,addr):
    aw=getattr(dut,prefix+"_araddr")
    av=getattr(dut,prefix+"_arvalid")
    ar=getattr(dut,prefix+"_arready")
    rv=getattr(dut,prefix+"_rvalid")
    rd=getattr(dut,prefix+"_rdata")
    rp=getattr(dut,prefix+"_rresp")
    rl=getattr(dut,prefix+"_rlast")
    rr=getattr(dut,prefix+"_rready")
    await FallingEdge(dut.logic_clk)
    aw.value=addr
    av.value=1
    rr.value=1
    await rising_ready(dut.logic_clk,ar,f"{prefix} AR")
    await FallingEdge(dut.logic_clk)
    av.value=0
    await rising_ready(dut.logic_clk,rv,f"{prefix} R")
    assert int(rp.value)==0 and int(rl.value),"AXI R not OKAY/RLAST"
    observed=int(rd.value)
    await FallingEdge(dut.logic_clk)
    rr.value=0
    return observed


async def wait_count(dut,signal,count,limit=30000):
    for _ in range(limit):
        await RisingEdge(dut.logic_clk)
        if int(signal.value)>=count:
            return
    raise AssertionError(f"timeout waiting for {signal._name}={count}")


@cocotb.test(timeout_time=3,timeout_unit="ms")
async def real_gmii_rx_and_b_gated_cq(dut):
    gmii=await setup(dut)
    # Independent host frontdoor descriptor AW/W/B, not RAM preload.
    await descriptor_word(dut,0x100,0x2100)
    await descriptor_word(dut,0x108,(0xc0febabe<<32)|2048)
    await descriptor_word(dut,0x110,0)
    await descriptor_word(dut,0x118,0)
    for addr,val in (
        (0x20,0x100),(0x24,0),(0x30,0x500),(0x34,0),
        (0x74,0x800),(0x78,0xffff),(0x7c,6000),(0x80,0xffff),
        (0x84,3),(0x28,1),(0x08,1),
    ):
        await csr_write(dut,addr,val)
    assert await csr_read(dut,0x38)==0,"premature CQ producer before GMII"

    p=Packet(
        src_mac=bytes.fromhex("0250b6000011"),
        dst_mac=bytes.fromhex("0250b6000022"),
        src_ip="10.20.30.40",dst_ip="10.20.30.41",
        src_port=12345,dst_port=6000,
        payload=bytes((i*7+9)&255 for i in range(43)))
    frame=encode(p)[:-4]
    assert len(frame)==85
    dut._log.info("RUN ETH_RX_SRAM_SLICE real GMII peer + posted descriptor")
    await gmii.send(GmiiFrame.from_payload(frame))
    await wait_count(dut,dut.packet_b_count,1)
    assert int(dut.desc_ar_count.value)>=1,"missing real descriptor AXI AR"
    assert int(dut.cq_b_count.value)==0,"CQ retired during held B"
    assert not int(dut.irq.value),"IRQ asserted before accepted CQ B"
    assert await csr_read(dut,0x38)==0,"CQ producer advanced before B"

    observed=bytearray()
    for offset in range(0,len(frame),8):
        raw=await read_word(dut,"pkt",0x2100+offset)
        observed.extend(raw.to_bytes(8,"little"))
    assert bytes(observed[:len(frame)])==frame,"real RX AXI payload bytes mismatch"
    assert await csr_read(dut,0x38)==0,"CQ producer advanced during stalled AXI B"

    dut.cq_release_b.value=1
    await wait_count(dut,dut.cq_b_count,1)
    for _ in range(5):
        await RisingEdge(dut.logic_clk)
    assert int(dut.irq.value),"IRQ missing after successful real CQ B"
    assert await csr_read(dut,0x38)==1,"CQ producer did not advance"
    assert await csr_read(dut,0x2c)==1,"RX descriptor consumer did not advance"
    cq=[await read_word(dut,"cqr",0x500+8*i) for i in range(4)]
    assert cq==[0xc0febabe,85,0,0],f"real CQ words mismatch {cq!r}"
    dut._log.info("CHECK ETH_RX_SRAM_SLICE bytes=85 desc_AR=%d packet_B=%d CQ_B=%d",
                  int(dut.desc_ar_count.value),
                  int(dut.packet_b_count.value),
                  int(dut.cq_b_count.value))

    # No posted second buffer: do not overwrite the first payload or append CQ.
    await gmii.send(GmiiFrame.from_payload(frame))
    await gmii.wait()
    for _ in range(100):
        await RisingEdge(dut.logic_clk)
    assert int(dut.packet_b_count.value)==1,"no-buffer frame reached DMA"
    assert int(dut.cq_b_count.value)==1,"unposted frame got CQ"
    assert await csr_read(dut,0x38)==1,"CQ producer changed on no-buffer"

    # FCS corrupted by the external upstream GMII peer, before MAC.
    bad_fcs=[0]
    async def watch_bad():
        while True:
            await RisingEdge(dut.gmii_rx_clk)
            bad_fcs[0]+=int(dut.bad_fcs.value)
    monitor=cocotb.start_soon(watch_bad())
    bad=GmiiFrame.from_payload(frame)
    bad.data[-1]^=0x80
    await gmii.send(bad)
    await gmii.wait()
    for _ in range(120):
        await RisingEdge(dut.logic_clk)
    assert bad_fcs[0]>0,"real MAC did not detect injected bad FCS"
    assert int(dut.packet_b_count.value)==1,"bad FCS reached packet DMA"
    assert int(dut.cq_b_count.value)==1,"bad FCS generated completion"
    monitor.kill()
    dut._log.info("PASS real GMII RX to AXI packet and true B-gated CQ; no-buffer and bad-FCS negatives")
