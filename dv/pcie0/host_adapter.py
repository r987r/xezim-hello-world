"""PCIe Root Complex participant: actions only, NO second phase coordinator.

Called by dv/full_chip/test_boot.py, the sole INIT/RUN/CHECK entrypoint.
Real pinned verilog-pcie TLP->AXI RTL, generated PCIe0 NoC, real PULP SRAM.
PHY/LTSSM and RootComplex/Endpoint are behaviorally modeled.
"""
from pathlib import Path
import os
import sys
from cocotb.triggers import Timer, with_timeout, RisingEdge
from cocotbext.pcie.core import RootComplex
from dv.pcie0.discovery import enumerate_root_complex
from tools.memory_service import Pattern
from dv.common.axi_trace import trace_phase

ROOT=Path(__file__).resolve().parents[2]
UPSTREAM_TB=ROOT/".tools/verilog_pcie/tb/pcie_axi_master"
if not (UPSTREAM_TB/"pcie_if.py").is_file():
    raise RuntimeError("pinned PCIe RC/Endpoint helper missing")
sys.path.insert(0,str(UPSTREAM_TB))
from pcie_if import PcieIfDevice, PcieIfRxBus, PcieIfTxBus


async def poll_bar(bar, offset, value, *, attempts=5000, interval_ns=20):
    for _ in range(attempts):
        current=int.from_bytes(await bar.read(offset,4),"little")
        if current==value:
            return
        await Timer(interval_ns,units="ns")
    raise AssertionError(f"PCIe host never observed firmware handshake {offset:#x}={value:#x}")


class PcieHostParticipant:
    def __init__(self, flow, manifest):
        if flow is None:
            raise AssertionError("PCIe participant requires registered shared test-flow recorder")
        ext=manifest.get("external_host")
        if not ext or ext.get("type")!="pcie_root_complex_model":
            raise ValueError("missing shared CPU0 firmware host ABI")
        self.flow=flow
        self.ext=ext
        self.dma_exchange=os.environ.get('SOC_PCIE_DMA_HOST_MODE')=='1'
        self.outbound_mode=os.environ.get('SOC_PCIE_OUTBOUND_MODE')=='1'
        if self.outbound_mode and not self.dma_exchange:
            raise ValueError('outbound PCIe test requires CPU0 C-driven iDMA staged payload')
        self.outbound_verified=None
        self.host_mem=None
        self.host_mem_base=None
        self.outbound_counters={'posted_writes':0,'read_requests':0,'read_completions':0}
        self.outbound_monitor=None
        self.source_sram=manifest['cores'][0]['sram_base']
        self.base=ext["mailbox_base"]
        self.sram_base=self.base-0x800
        self.magic=ext["magic"]
        self.bar=None
        self.dut=None
        self.before_write=0
        self.before_read=0

    async def setup(self,dut):
        self.dut=dut
        dut.completer_id.value=0
        dut.max_payload_size.value=0
        rc=RootComplex()
        # Pinned cocotbext-pcie needs explicit RC outbound low BAR mapping.
        rc.mem_pool.register_region(rc.mem_region,self.sram_base,0x100000,offset=None)
        rc.mem_base=self.sram_base
        requester_ports = ({
            'tx_rd_req_tlp_bus': PcieIfTxBus.from_prefix(dut, 'tx_rd_req_tlp'),
            'tx_wr_req_tlp_bus': PcieIfTxBus.from_prefix(dut, 'tx_wr_req_tlp'),
            'rx_cpl_tlp_bus': PcieIfRxBus.from_prefix(dut, 'rx_cpl_tlp'),
            'cfg_max_read_req': dut.max_payload_size,
        } if self.outbound_mode else {})
        ep=PcieIfDevice(
            clk=dut.clk,rst=dut.rst,
            rx_req_tlp_bus=PcieIfRxBus.from_prefix(dut,"rx_req_tlp"),
            tx_cpl_tlp_bus=PcieIfTxBus.from_prefix(dut,"tx_cpl_tlp"),
            cfg_max_payload=dut.max_payload_size,**requester_ports)
        ep.functions[0].configure_bar(0,1024*1024)
        rc.make_port().connect(ep)
        with self.flow.step("init","host0","enumerate",origin="stimulus"):
            missing=await with_timeout(enumerate_root_complex(rc,timeout_us=80),150,"us")
            dut._log.info("PCIE0_EXPECTED_DISCOVERY_MISSES=%d",missing)
            device=rc.find_device(ep.functions[0].pcie_id)
            assert device is not None,"modeled RC could not enumerate PCIe endpoint"
            await with_timeout(device.enable_device(),100,"us")
        dut.completer_id.value=int(ep.functions[0].pcie_id)
        self.bar=device.bar_window[0]
        if self.outbound_mode:
            # Input descriptors are idle until after the C/iDMA stage has
            # completed, never accidentally asserted at power-on.
            dut.s_axis_read_desc_valid.value=0
            dut.s_axis_write_desc_valid.value=0
            from cocotbext.axi.stream import define_stream
            rd_bus,rd_tx,rd_src,_,_=define_stream(
                'PcieOutRdDesc',
                signals=['pcie_addr','ram_addr','len','tag','valid','ready'])
            wr_bus,wr_tx,wr_src,_,_=define_stream(
                'PcieOutWrDesc',
                signals=['pcie_addr','ram_addr','len','tag','valid','ready'])
            st_bus,_,_,st_sink,_=define_stream(
                'PcieOutStatus',signals=['tag','error','valid'])
            self.out_rd_tx=rd_tx
            self.out_wr_tx=wr_tx
            self.out_rd_desc=rd_src(rd_bus.from_prefix(dut,'s_axis_read_desc'),dut.clk,dut.rst)
            self.out_wr_desc=wr_src(wr_bus.from_prefix(dut,'s_axis_write_desc'),dut.clk,dut.rst)
            self.out_rd_status=st_sink(st_bus.from_prefix(dut,'m_axis_read_desc_status'),dut.clk,dut.rst)
            self.out_wr_status=st_sink(st_bus.from_prefix(dut,'m_axis_write_desc_status'),dut.clk,dut.rst)
            await with_timeout(device.set_master(),100,'us')
            self.host_mem=rc.mem_pool.alloc_region(1<<20)
            self.host_mem_base=self.host_mem.get_absolute_address(0)
            import cocotb
            self.outbound_monitor=cocotb.start_soon(self.watch_outbound(dut))

    async def before_phase(self,stage):
        if stage=="init":
            with self.flow.step(stage,"host0","wait_device_ready",origin="observed"):
                await with_timeout(poll_bar(self.bar,0x800,self.magic["device_init_ready"]),1000,"us")
                assert int(self.dut.init_mask.value)==3, "CPU INIT not complete when host ready"
            if self.dma_exchange:
                # Host -> real PCIe bridge -> SRAM first; CPU0 iDMA later
                # copies these bytes into modeled DDR and proves via readback.
                input_payload=bytes((0x63+13*i)&255 for i in range(64))
                with self.flow.step(stage,"host0","seed_ddr_input",origin="checker",
                                    details={"address":hex(self.sram_base+0x500),"bytes":64}):
                    await with_timeout(self.bar.write(0x500,input_payload),100,"us")
                    got=await with_timeout(self.bar.read(0x500,64),100,"us")
                    assert bytes(got)==input_payload,"PCIe DDR seed readback mismatch"
            with self.flow.step(stage,"host0","init_ack",origin="stimulus"):
                await with_timeout(self.bar.write(0x804,self.magic["host_init_ack"].to_bytes(4,"little")),100,"us")
            trace_phase("PCIe host INIT acknowledged through real BAR")
        elif stage=="run":
            with self.flow.step(stage,"host0","wait_run_enable",origin="observed"):
                # Real CPU C/iDMA takes ~3.2 ms before the extra PCIe
                # exchange; poll sparingly to avoid creating bus congestion.
                # CPU/iDMA continues executing for milliseconds while the
                # host waits. A 1us BAR polling cadence adds thousands of
                # simulated PCIe TLPs and can exhaust the CI wall-clock
                # budget before firmware reaches RUN. Poll every 20us instead
                # with the SAME 9ms simulated timeout and unchanged handshake.
                # This is a wait optimization, not a relaxed RTL check.
                await with_timeout(poll_bar(
                    self.bar,0x808,self.magic["run_enable"],
                    attempts=450 if self.dma_exchange else 5000,
                    interval_ns=20000 if self.dma_exchange else 20),
                    9000 if self.dma_exchange else 1000,"us")
            self.before_write=int(self.dut.pcie_sram_write_count.value)
            self.before_read=int(self.dut.pcie_sram_read_count.value)
            with self.flow.step(stage,"host0","bar_roundtrip",origin="checker",details={"vectors":4}):
                for index,(offset,length) in enumerate(((0x100,8),(0x125,17),(0x200,64),(0x327,33))):
                    payload=Pattern("address_xor",seed=0x5a33).chunk(self.sram_base+offset,length)
                    with self.flow.step(stage,"host0",f"bar_write_{index}",origin="stimulus",
                                        details={"address":hex(self.sram_base+offset),"bytes":length}):
                        await with_timeout(self.bar.write(offset,payload),100,"us")
                    with self.flow.step(stage,"host0",f"bar_read_{index}",origin="checker",
                                        details={"address":hex(self.sram_base+offset),"bytes":length}):
                        result=await with_timeout(self.bar.read(offset,length),100,"us")
                        assert bytes(result)==payload, f"PCIe0 SRAM data mismatch at {offset:#x}"
                assert int(self.dut.pcie_sram_write_count.value)>self.before_write, "no real SRAM write"
                assert int(self.dut.pcie_sram_read_count.value)>self.before_read, "no real SRAM read"
                assert not int(self.dut.status_error_cor.value), "PCIe correctable status set"
                assert not int(self.dut.status_error_uncor.value), "PCIe uncorrectable status set"
            if self.dma_exchange:
                # DDR -> PULP iDMA -> PCIe SRAM, then actual host BAR read.
                expected=bytes((self.source_sram+0x2000+i+0x35)&255 for i in range(64))
                with self.flow.step(stage,"host0","read_ddr_dma_output",origin="checker",
                                    details={"address":hex(self.sram_base+0x600),"bytes":64}):
                    got=await with_timeout(self.bar.read(0x600,64),100,"us")
                    assert bytes(got)==expected,"DDR to PCIe host data mismatch"
            if self.outbound_mode:
                await self.exercise_outbound_device_dma()
            with self.flow.step(stage,"host0","run_ack",origin="stimulus"):
                await with_timeout(self.bar.write(0x80c,self.magic["host_run_ack"].to_bytes(4,"little")),100,"us")
            trace_phase("PCIe host RUN verified four actual BAR roundtrips")
        elif stage=="check":
            with self.flow.step(stage,"host0","wait_check_enable",origin="observed"):
                await with_timeout(poll_bar(self.bar,0x810,self.magic["check_enable"]),800,"us")
            with self.flow.step(stage,"host0","check_ack",origin="stimulus"):
                await with_timeout(self.bar.write(0x814,self.magic["host_check_ack"].to_bytes(4,"little")),100,"us")
        else:
            raise ValueError("unregistered shared CPU test phase")

    async def watch_outbound(self,dut):
        # Passive accepted-handshake evidence; no extra PCIe bus driver.
        while True:
            await RisingEdge(dut.clk)
            if not int(dut.rst_n.value):
                continue
            for signal,counter in (
                    ('tx_wr_req_tlp','posted_writes'),
                    ('tx_rd_req_tlp','read_requests'),
                    ('rx_cpl_tlp','read_completions')):
                if all(int(getattr(dut,signal+'_'+field).value)
                       for field in ('valid','ready','sop')):
                    self.outbound_counters[counter]+=1

    async def exercise_outbound_device_dma(self):
        """The CPU has staged DDR bytes into PCIe SRAM using *real* iDMA.

        TLP requester descriptor submission is testbench-owned at this stage;
        future PCIe0 Config-NoC CSRs will own it for CPU/software.
        """
        from pathlib import Path
        import json
        source=self.source_sram+0x2000
        expected=bytes((source+i+0x35)&255 for i in range(64))
        host=self.host_mem
        assert host is not None
        host_offset=0xff9  # cross a 4-KiB host-memory boundary
        host[host_offset-1:host_offset+65]=bytes([0xa5])*66
        before=dict(self.outbound_counters)
        with self.flow.step("run","host0","pcie_dma_write_host",origin="checker",
                            details={"source":"pcie0.sram+0x600",
                                     "host_address":hex(self.host_mem_base+host_offset),
                                     "bytes":64}):
            await with_timeout(self.out_wr_desc.send(self.out_wr_tx(
                pcie_addr=self.host_mem_base+host_offset,ram_addr=0x600,
                len=64,tag=0x25)),100,'us')
            status=await with_timeout(self.out_wr_status.recv(),250,'us')
            assert int(status.tag)==0x25 and int(status.error)==0, (
                "real PCIe requester write returned error")
            # PCIe posted writes have no completion. Read modeled RC memory
            # independently after accepted TLP and check adjacent guards.
            for _ in range(5000):
                if bytes(host[host_offset:host_offset+64])==expected:
                    break
                await RisingEdge(self.dut.clk)
            assert bytes(host[host_offset-1:host_offset+65])==(
                bytes([0xa5])+expected+bytes([0xa5])), (
                "device iDMA-staged DDR->PCIe SRAM->host RAM bytes/guards mismatch")
            assert self.outbound_counters['posted_writes']>before['posted_writes'], (
                "PCIe requester posted no real Memory Write TLP")
        # Opposite direction: actual outbound Memory Read into shared PCIe
        # SRAM. BAR read is only an independent checker, NOT the transfer.
        inbound=bytes((0x7b+17*i)&255 for i in range(64))
        reverse_off=0x2ff9
        host[reverse_off-1:reverse_off+65]=bytes([0xa5])+inbound+bytes([0xa5])
        with self.flow.step("run","host0","pcie_dma_read_host",origin="checker",
                            details={"destination":"pcie0.sram+0x700",
                                     "host_address":hex(self.host_mem_base+reverse_off),
                                     "bytes":64}):
            await with_timeout(self.out_rd_desc.send(self.out_rd_tx(
                pcie_addr=self.host_mem_base+reverse_off,ram_addr=0x700,
                len=64,tag=0x26)),100,'us')
            status=await with_timeout(self.out_rd_status.recv(),250,'us')
            assert int(status.tag)==0x26 and int(status.error)==0, (
                "real PCIe requester read completion error")
            got=bytes(await with_timeout(self.bar.read(0x700,64),100,'us'))
            assert got==inbound, "host memory read TLP did not fill shared PCIe SRAM"
            assert self.outbound_counters['read_requests']>before['read_requests']
            assert self.outbound_counters['read_completions']>before['read_completions']
        self.outbound_verified={
            "iDMA_staged_DDR_to_PCIe_SRAM":True,
            "host_memory_bytes_verified":64,
            "reverse_host_memory_bytes_verified":64,
            "host_memory_offset":hex(host_offset),
            "read_host_memory_offset":hex(reverse_off),
            "requester_descriptor_control":"cocotb_direct_until_config_noc_csr",
            "physical_path":"real CPU0 PULP iDMA -> actual FlooNoC -> shared tc_sram -> pinned dma_if_pcie -> modeled RC RAM",
            "accepted_tlps":{k:self.outbound_counters[k]-before[k] for k in before}
        }
        assert all(n>0 for n in self.outbound_verified['accepted_tlps'].values())
        plan=Path(os.environ["SOC_RUN_PLAN"])
        (plan.parent/"outbound-dma-proof.json").write_text(
            json.dumps(self.outbound_verified,indent=2,sort_keys=True)+"\\n")
        self.dut._log.info("PCIE0_OUTBOUND_REAL_IDMA_HOST_PASS=%s",self.outbound_verified)

    def finish(self):
        dut=self.dut
        with self.flow.step("check","host0","final_verify",origin="checker"):
            assert int(dut.pass_flag.value)==1, "CPU checker PASS was not observed"
            assert int(dut.init_mask.value)==3
            assert int(dut.hello_mask.value)==3
            assert int(dut.check_mask.value)==3
            for signal in ("pcie_sram_last_read_addr","pcie_sram_last_write_addr"):
                address=int(getattr(dut,signal).value)
                assert self.sram_base<=address<self.sram_base+16384
            assert int(dut.pcie_sram_write_count.value)>0
            assert int(dut.pcie_sram_read_count.value)>0
        if self.outbound_mode:
            assert self.outbound_verified is not None, 'outbound host-memory proof was never reached'
            assert self.outbound_verified['host_memory_bytes_verified']==64
            assert self.outbound_verified['reverse_host_memory_bytes_verified']==64
            self.outbound_monitor.kill()
            dut._log.info("PASS pcieoutbound: real iDMA staged bytes and outbound PCIe TLPs verified")
        dut._log.info("PASS pciehost: real CPU0/host handshake and PCIe0 SRAM data; "
                      "writes=%d reads=%d",int(dut.pcie_sram_write_count.value),
                      int(dut.pcie_sram_read_count.value))
