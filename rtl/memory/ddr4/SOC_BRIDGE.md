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

## Real RTL aperture checker (initial DDR-B hardware)
The memory-only soc_aperture_guard.sv is a **synthesizable combinational
physical-to-local address/burst guard**, tested with tb_soc_aperture_guard.sv
under Verilator --binary --assert --timing in the DDR4 CI job. It rejects
address aliasing into the 32 MiB modeled storage, unsupported AXI ATOP,
burst type/size, and 4 KiB boundary crossing. It does not consume AW/W or
AR traffic and therefore cannot synthesize a legal DECERR response on its
own. The follow-on full AXI bridge must use its allow/fault outputs and
implement that handshake/response behavior. Keep bus-side AXI ID mapping
in the bridge, not this independent combinational address decoder.

## Actual AXI protocol bridge (standalone RTL)

The memory-only `ddr_litedram_axi_bridge` in `soc_axi_bridge.sv`
instantiates two copies of the verified aperture guard and implements real
upstream AW/W/B and AR/R slave handshakes. Accepted in-range requests are
address-translated to the **generated 25-bit LiteDRAM AXI local address**
and forwarded with the original 4-bit ID, LEN/SIZE/BURST, data and WSTRB.
Unsupported addresses/bursts/ATOP are not forwarded; the slave consumes
their write beats, returns `BRESP=DECERR` after the final W beat, or returns
the requested number of `RRESP=DECERR` beats with a correct final RLAST.
Responses are retained under backpressure. The initial bridge allows one
write burst and one read burst in flight independently; the SoC integration
owner must verify the actual crossbar output ID width and arbitration.

The bridge deliberately does **not** instantiate or initialize the
controller and never fabricates memory read data for valid addresses. It
blocks new AW/AR requests until `controller_ready_i` is asserted by a
real DFII/Wishbone initialization service. `tb_soc_axi_bridge.sv` drives
a real HDL test for successful pass-through and invalid-address DECERR,
including B/R backpressure and ID preservation; the standalone pinned
DDR4 controller/DFI test is still a separate functional test in the
same CI job. This is stronger than a host-only contract, **but is not
yet an end-to-end full-chip controller path**.

## Remaining DDR-B hardware and verification gates

1. Finish sign-off for the standalone AXI response adapter: verify exact-head Verilator bridge test, clock/reset readiness, malformed write bursts, extra AXI attributes and concurrency/ID constraints; preserve the existing DDR4 AXI/DFI functional test. The initial one-read + one-write implementation and DECERR handling are in soc_axi_bridge.sv.
2. Add Wishbone init/status service on the independent Config NoC, with CPU-controlled init and failure timeouts.
3. Hand bridge and Bender source closure to sole #38 generator owner; that track will edit config/soc.yaml, tools/full_chip_gen.py and generated RTL/diagrams. No parallel generator edits here.
4. Add opt-in chip-ddr4-real with actual CPU/iDMA traffic through the generated Data NoC and controller, DFI monitoring, independent INIT/RUN/CHECK, negative aperture tests and comparison against axi_ram timing.
5. Only then claim full-chip DDR4 integration. Standalone DFI and BankModel are simulation models, not a physical DDR PHY.
