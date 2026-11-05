# DDR-B: isolated LiteDRAM full-chip integration contract

Issue #40; coordinates with standalone DDR-A #35 and shared generator owner #38.

The live SoC memory0.ddr0 target still uses AXI RAM. This contract is an integration prerequisite, not the completed controller RTL hookup. It does not modify generated SoC files.

## Data versus configuration fabrics

- Keep the 64-bit global/local AXI4 Data NoCs independent from the 32-bit Config NoCs.
- The architectural DDR address window is 0x140000000 through 0x17fffffff (1 GiB). The isolated DDR4 DFI/BankModel supports only the low 32 MiB of that window.
- Translate and validate the full physical address BEFORE driving the LiteDRAM local AXI pins. Do not slice or mask upper address bits or alias unsupported offsets into modeled storage.
- A future RTL bridge MUST send legal DECERR on out-of-range or unsupported accesses, consuming write beats and maintaining AW/W/B/AR/R ordering; the Python contract itself is not a bus responder.
- Validate AWID/ARID, WSTRB, byte widths, burst length, 4 KiB boundary, and ATOP before forwarding. If the crossbar widens ID fields, use an explicit reversible tag mapper rather than silently dropping bits.
- Controller Wishbone/DFII initialization needs a real Config NoC path, resets, init_done and init_error propagation. Do not fake or force initialization or silently preload the controller.
- Use the pinned LiteDRAM controller, simulation PHY and DFI/BankModel; keep the default axi_ram backend available for fast baseline regressions.

## Commands

Run the existing DDR4 Python tests and isolated CI workflow. Then run the contract CLI:

    python3 rtl/memory/ddr4/soc_bridge_contract.py --output .tools/ddr4/ddr_soc_bridge_contract.json

After the pinned controller top has been generated, additionally validate actual exported RTL pins:

    python3 rtl/memory/ddr4/soc_bridge_contract.py --generated-verilog .tools/ddr4/litedram_sim/gateware/soc_ddr4_sim.v

JSON is explicitly labeled integration_state=contract_only, never RTL tested.

## Remaining DDR-B hardware and verification gates

1. Add an isolated memory-only AXI-to-LiteDRAM RTL bridge with real DECERR responses, bounded aperture translation and protocol/ID checking. Test independently with Verilator.
2. Add Wishbone init/status service on the independent Config NoC, with CPU-controlled init and failure timeouts.
3. Hand bridge and Bender source closure to sole #38 generator owner; that track will edit config/soc.yaml, tools/full_chip_gen.py and generated RTL/diagrams. No parallel generator edits here.
4. Add opt-in chip-ddr4-real with actual CPU/iDMA traffic through the generated Data NoC and controller, DFI monitoring, independent INIT/RUN/CHECK, negative aperture tests and comparison against axi_ram timing.
5. Only then claim full-chip DDR4 integration. Standalone DFI and BankModel are simulation models, not a physical DDR PHY.
