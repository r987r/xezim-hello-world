"""Root Complex BFM -> real PCIe TLP/AXI4 bridge -> AXI RAM BFM.

No PCIe PHY/LTSSM, local FlooNoC or PULP SRAM exists in this test.
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotbext.pcie.core import RootComplex
from cocotbext.axi import AxiBus, AxiRam
from pcie_if import PcieIfDevice, PcieIfRxBus, PcieIfTxBus
from discovery import enumerate_root_complex


@cocotb.test()
async def pcie_host_bar_to_real_axi4_bridge(dut):
    cocotb.start_soon(Clock(dut.clk, 4, units="ns").start())

    host = RootComplex()
    endpoint = PcieIfDevice(
        clk=dut.clk,
        rst=dut.rst,
        rx_req_tlp_bus=PcieIfRxBus.from_prefix(dut, "rx_req_tlp"),
        tx_cpl_tlp_bus=PcieIfTxBus.from_prefix(dut, "tx_cpl_tlp"),
        cfg_max_payload=dut.max_payload_size,
    )
    endpoint.functions[0].configure_bar(0, 16 * 1024 * 1024)
    host.make_port().connect(endpoint)
    ram = AxiRam(AxiBus.from_prefix(dut, "m_axi"), dut.clk, dut.rst, size=65536)

    dut.rst.setimmediatevalue(0)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    missing_count = await enumerate_root_complex(host)
    dut._log.info("PCIE0_EXPECTED_DISCOVERY_MISSES=%d", missing_count)
    device = host.find_device(endpoint.functions[0].pcie_id)
    assert device is not None, "Root Complex must enumerate modeled Endpoint"
    await device.enable_device()
    bar0 = device.bar_window[0]
    dut.completer_id.value = int(endpoint.functions[0].pcie_id)

    # Actual TLP-to-AXI4 RTL handles both directions. Checking memory
    # through model backdoor is a golden reference, not accepted AXI evidence.
    vectors = [
        (0x1000, bytes([0xa5])),
        (0x1023, bytes((i * 17 + 7) % 256 for i in range(19))),
        (0x1ff8, bytes((i * 11 + 3) % 256 for i in range(39))),
        (0x3020, bytes((i * 31 + 9) % 256 for i in range(128))),
    ]
    for address, payload in vectors:
        ram.write(address - 1, b"\x55" * (len(payload) + 2))
        await bar0.write(address, payload)
        # Following non-posted read acts as a PCIe ordering fence for writes.
        await bar0.read(0, 4, timeout=20000, timeout_unit="ns")
        expected = b"\x55" + payload + b"\x55"
        assert ram.read(address - 1, len(expected)) == expected, (
            f"AXI4 write or byte-strobe mismatch at {address:#x}"
        )
        received = await bar0.read(
            address, len(payload), timeout=20000, timeout_unit="ns"
        )
        assert received == payload, (
            f"PCIe completion payload mismatch at {address:#x}"
        )

    await Timer(100, units="ns")
    dut._log.info("PCIE0_REAL_AXI4_BRIDGE_PASS vectors=%d", len(vectors))
