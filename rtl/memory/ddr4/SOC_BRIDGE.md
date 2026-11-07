# LiteDRAM full-chip AXI and Config-NoC bridge

This describes the **opt-in** `chip-ddr4-real` variant. Default `memory0.ddr0` remains bounded behavioral AXI RAM. The real controller has a behavioral DFI PHY/bank model, **not** a physical DDR4 PHY. The [standalone DDR4 guide](README.md) owns controller generation, command probes and model limitations.

## Data path and legality

The generated global/local Data NoCs use 64-bit AXI4 physical addresses. The `ddr_litedram_axi_bridge` wraps the `soc_aperture_guard.sv` and translates legal memory requests to the generated **25-bit LiteDRAM local AXI**. It preserves AXI ID, burst/size, data/WSTRB and read/write ordering; the initial bridge accepts one read and one write burst concurrently.

The architectural `0x140000000–0x17fffffff` DDR window is 1 GiB, but only its **low 32 MiB** has modeled backing. Invalid address aliases, disallowed ATOP/bursts and 4 KiB-crossing accesses must not forward to the controller. The protocol bridge consumes invalid W beats and returns legal `BRESP/RRESP=DECERR` with correct RLAST/backpressure; the *combinational* guard alone is not a responder. Unit and routed negative tests must verify forbidden AW/AR never reaches the real controller and valid neighboring data is unchanged.

## Config NoC and startup

The independent 32-bit Config NoC uses a **16 KiB** controller CSR aperture `0x40030000–0x40033fff` in the selected DDR variant, then AXI-to-Wishbone/DFII initialization. The test's pinned script performs **43 writes and three checked readbacks**, requiring genuine controller `init_done=1` and `init_error=0`. A preboot Config-NoC initiator operates while CPU0 is held in reset; its responses are isolated before the CPU takes ownership. No forced init completion, backdoor SRAM preload or unsupported physical DDR/PHY inference.

The controller-facing `AW/B`, `AR/RLAST`, DFI events and modeled bank writes are independently captured. AW→DFI WRITE per-ID remains **unmeasured** because DFI lacks AXI IDs and write acceptance may precede bank storage.

## Reproduce

```sh
python3 rtl/memory/ddr4/soc_bridge_contract.py --output .tools/ddr4/ddr_soc_bridge_contract.json
python3 rtl/memory/ddr4/soc_bridge_contract.py --generated-verilog .tools/ddr4/litedram_sim/gateware/soc_ddr4_sim.v
python3 tools/regress.py chip-ddr4-real
```

The standalone bridge-contract JSON may label itself `contract_only`; do **not** mistake it for the connected full-chip RTL result. Controller/APB/DFI and returned `DECERR` are real source-matched simulation evidence only when the selected regression and passive monitors pass. Long refresh/backpressure/reset stress is [#35](https://github.com/r987r/xezim-hello-world/issues/35); Ethernet/PCIe to *this same controller* is [#34](https://github.com/r987r/xezim-hello-world/issues/34).
