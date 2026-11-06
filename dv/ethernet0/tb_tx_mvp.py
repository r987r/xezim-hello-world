"""TX memory descriptor -> pinned AXI DMA read -> 1GbE GMII -> CQ AXI B."""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge,FallingEdge,Timer,with_timeout
from cocotbext.eth import GmiiSink
from dv.ethernet0.frame_contract import Packet,encode


async def until(clk,signal,label,limit=10000):
    for _ in range(limit):
        await RisingEdge(clk)
        if int(signal.value):
            return
    raise AssertionError(f"timeout {label}")


async def host_word(dut,prefix,address,data):
    await FallingEdge(dut.logic_clk)
    getattr(dut,prefix+"_host_awaddr").value=address
    getattr(dut,prefix+"_host_awvalid").value=1
    await until(dut.logic_clk,getattr(dut,prefix+"_host_awready"),prefix+" AW")
    await FallingEdge(dut.logic_clk)
    getattr(dut,prefix+"_host_awvalid").value=0
    getattr(dut,prefix+"_host_wdata").value=data
    getattr(dut,prefix+"_host_wvalid").value=1
    getattr(dut,prefix+"_host_wlast").value=1
    await until(dut.logic_clk,getattr(dut,prefix+"_host_wready"),prefix+" W")
    await FallingEdge(dut.logic_clk)
    getattr(dut,prefix+"_host_wlast").value=0
    getattr(dut,prefix+"_host_wvalid").value=0
    getattr(dut,prefix+"_host_bready").value=1
    await until(dut.logic_clk,getattr(dut,prefix+"_host_bvalid"),prefix+" B")
    assert int(getattr(dut,prefix+"_host_bresp").value)==0
    await FallingEdge(dut.logic_clk)
    getattr(dut,prefix+"_host_bready").value=0


async def cq_read(dut,addr):
    await FallingEdge(dut.logic_clk)
    dut.cqr_araddr.value=addr
    dut.cqr_arvalid.value=1
    dut.cqr_rready.value=1
    await until(dut.logic_clk,dut.cqr_arready,"CQ AR")
    await FallingEdge(dut.logic_clk)
    dut.cqr_arvalid.value=0
    await until(dut.logic_clk,dut.cqr_rvalid,"CQ R")
    assert int(dut.cqr_rresp.value)==0 and int(dut.cqr_rlast.value)
    data=int(dut.cqr_rdata.value)
    await FallingEdge(dut.logic_clk)
    dut.cqr_rready.value=0
    return data


@cocotb.test(timeout_time=2,timeout_unit="ms")
async def tx_descriptor_through_real_gmii_and_cq(dut):
    dut.logic_rst.value=1;dut.gmii_tx_rst.value=1;dut.gmii_rx_rst.value=1
    dut.tx_desc_valid.value=0
    dut.cq_release_b.value=0
    for prefix in ("desc","data"):
        for part in ("awaddr","awvalid","wdata","wvalid","wlast","bready"):
            getattr(dut,prefix+"_host_"+part).value=0
    dut.cqr_araddr.value=0;dut.cqr_arvalid.value=0;dut.cqr_rready.value=0
    cocotb.start_soon(Clock(dut.logic_clk,10,units="ns").start())
    cocotb.start_soon(Clock(dut.gmii_rx_clk,8,units="ns").start())
    cocotb.start_soon(Clock(dut.gmii_tx_clk,8,units="ns").start())
    gmii=GmiiSink(dut.gmii_txd,dut.gmii_tx_er,dut.gmii_tx_en,
                  dut.gmii_tx_clk,dut.gmii_tx_rst)
    await Timer(100,units="ns")
    dut.logic_rst.value=0;dut.gmii_tx_rst.value=0;dut.gmii_rx_rst.value=0
    for _ in range(20):
        await RisingEdge(dut.logic_clk)

    pkt=Packet(
        src_mac=bytes.fromhex("0250b6000011"),
        dst_mac=bytes.fromhex("0250b6000022"),
        src_ip="10.20.30.40",dst_ip="10.20.30.41",
        src_port=12345,dst_port=6000,
        payload=bytes((i*7+9)&255 for i in range(43)))
    frame=encode(pkt)[:-4]
    assert len(frame)==85
    # CPU/host publishes TX frame and descriptor using real AXI writes.
    for ofs in range(0,len(frame),8):
        word=int.from_bytes(frame[ofs:ofs+8].ljust(8,b"\x00"),"little")
        await host_word(dut,"data",0x2100+ofs,word)
    await host_word(dut,"desc",0x600,0x2100)
    await host_word(dut,"desc",0x608,(0xfeedcafe<<32)|len(frame))
    await host_word(dut,"desc",0x610,0)
    await host_word(dut,"desc",0x618,0)

    dut._log.info("RUN ETH_TX_GMII_SLICE real descriptor AR -> payload AR/RLAST -> MAC TX -> CQ")
    await FallingEdge(dut.logic_clk)
    dut.tx_desc_valid.value=1
    await until(dut.logic_clk,dut.tx_desc_ready,"queue TX descriptor request")
    await FallingEdge(dut.logic_clk)
    dut.tx_desc_valid.value=0
    try:
        transmitted=await with_timeout(gmii.recv(),350,"us")
    except Exception as exc:
        raise AssertionError("real GMII TX frame never completed") from exc
    assert bytes(transmitted.get_payload())==frame,"TX GMII payload differs from posted SRAM"
    assert transmitted.check_fcs(),"missing/corrupt real TX Ethernet FCS"
    assert transmitted.error is None,"physical GMII error on positive TX"

    # CQ is not retired simply because upstream DMA/TX FIFO accepted a frame.
    assert int(dut.descriptor_ar_count.value)>=1,"missing actual descriptor AXI AR"
    assert int(dut.packet_ar_count.value)>=1,"missing actual TX payload AXI AR"
    assert int(dut.cq_b_count.value)==0,"premature TX CQ B"
    assert not int(dut.tx_cpl_written.value),"premature TX producer advance"
    for _ in range(40):
        await RisingEdge(dut.logic_clk)
    assert not int(dut.tx_cpl_written.value),"completion without CQ B"
    dut.cq_release_b.value=1

    seen_cpl=[False]
    async def watch():
        for _ in range(2000):
            await RisingEdge(dut.logic_clk)
            if int(dut.tx_cpl_written.value):
                seen_cpl[0]=True
            if int(dut.cq_b_count.value)>0 and seen_cpl[0]:
                return
        raise AssertionError("TX never completed real CQ B")
    await watch()
    for _ in range(4):
        await RisingEdge(dut.logic_clk)
    cq=[await cq_read(dut,0x700+i*8) for i in range(4)]
    assert cq==[0xfeedcafe,len(frame),1<<32,0],f"TX CQ bytes wrong: {cq!r}"
    assert int(dut.tx_failed_o.value)==0,"real TX CQ writer failed"
    dut._log.info("CHECK ETH_TX_GMII_SLICE desc_AR=%d payload_AR=%d CQ_B=%d bytes=%d",
                  int(dut.descriptor_ar_count.value),
                  int(dut.packet_ar_count.value),
                  int(dut.cq_b_count.value),len(frame))
    dut._log.info("PASS real SRAM AXI -> GMII FCS+wire-end -> B-gated 32B TX CQ")
