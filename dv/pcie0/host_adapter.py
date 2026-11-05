"""PCIe Root Complex participant: actions only, NO second phase coordinator.

Called by dv/full_chip/test_boot.py, the sole INIT/RUN/CHECK entrypoint.
Real pinned verilog-pcie TLP->AXI RTL, generated PCIe0 NoC, real PULP SRAM.
PHY/LTSSM and RootComplex/Endpoint are behaviorally modeled.
"""
from pathlib import Path
import os
import sys
from cocotb.triggers import Timer, with_timeout
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


async def poll_bar(bar, offset, value):
    for _ in range(5000):
        current=int.from_bytes(await bar.read(offset,4),"little")
        if current==value:
            return
        await Timer(20,units="ns")
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
        ep=PcieIfDevice(
            clk=dut.clk,rst=dut.rst,
            rx_req_tlp_bus=PcieIfRxBus.from_prefix(dut,"rx_req_tlp"),
            tx_cpl_tlp_bus=PcieIfTxBus.from_prefix(dut,"tx_cpl_tlp"),
            cfg_max_payload=dut.max_payload_size)
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
                await with_timeout(poll_bar(self.bar,0x808,self.magic["run_enable"]),1000,"us")
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
        dut._log.info("PASS pciehost: real CPU0/host handshake and PCIe0 SRAM data; "
                      "writes=%d reads=%d",int(dut.pcie_sram_write_count.value),
                      int(dut.pcie_sram_read_count.value))
