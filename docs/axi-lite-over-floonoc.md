# AXI4-Lite register access across FlooNoC

FlooGen's pinned FlooNoC transport is AXI4; **Config NoCs carry 32-bit AXI4**, even where CPUs and register subordinates use AXI4-Lite. Never invent a separate AXI-Lite NoC or discard AXI channel IDs/lengths to fit a bridge.

## Physical data path

CPU AXI4-Lite → upstream `axi_lite_to_axi` → local/global/remote Config FlooNoCs → upstream `axi_to_axi_lite` → selected subordinate. Supported conversions use the **pinned** upstream PULP AXI source from FlooNoC's `Bender.lock`, not an arbitrarily newer `config/ip.lock.yaml` AXI pin. Width changes require the actual `axi_lite_dw_converter` and verified alignment/strobes.

Core upstream references:
- [AXI-Lite to AXI](https://github.com/pulp-platform/axi/blob/0ccc838fe06aeeb857eb83c6be9a915c4bf99566/src/axi_lite_to_axi.sv)
- [AXI to AXI-Lite](https://github.com/pulp-platform/axi/blob/0ccc838fe06aeeb857eb83c6be9a915c4bf99566/src/axi_to_axi_lite.sv)
- [AXI-Lite width conversion](https://github.com/pulp-platform/axi/blob/0ccc838fe06aeeb857eb83c6be9a915c4bf99566/src/axi_lite_dw_converter.sv)
- [FlooNoC Bender source](https://github.com/pulp-platform/FlooNoC/blob/05368bdff914f91a48b47c4ceddfc6ff266c6b3a/Bender.yml)

CPU/reset and iDMA submission CSR paths have qualified **separately selected** boot/DMA regressions. Ethernet queue CSR is real in its opt-in variant, and the real-DDR variant uses Config-NoC→Wishbone/DFII initialization. The **default** modeled-memory controller and PCIe management windows remain reserved. A register catalog or configured address does not prove an active subordinate.

## Verification requirements

Across the actual selected local/global Config NoC, verify single-beat writes and reads, 32-bit data/strobes, AW/W decoupling, B/R return with legal AXI IDs, bounded backpressure, byte enables, decoded remote addresses and legitimate error responses. Interactions with Data-NoC DMA require an independent concurrency test; a successful NoC BFM route or compilation alone does not qualify every controller/CSR variant.

Read port widths, pending budgets and atomic/RoB parameters from [interface contracts](../config/interface_contracts.yaml); maintain upstream assertion checks. See [boot](full-chip-boot.md), [DMA](dma-bringup.md), [DDR Config-NoC](../rtl/memory/ddr4/SOC_BRIDGE.md) and [CSR evidence](csr-generation.md). Never count a backdoor read as a frontdoor MMIO transaction.
