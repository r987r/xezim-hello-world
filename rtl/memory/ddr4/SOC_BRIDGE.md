# DDR-B: isolated LiteDRAM full-chip integration contract

Issue #40; coordinates with standalone DDR-A #35 and shared generator owner #38.

The **default** SoC memory0.ddr0 target still uses fast AXI RAM, but
DDR-B PR #74 now generates an **opt-in real LiteDRAM** target behind the
Memory0 crossbar. [Exact-head CI #42217902632](https://github.com/r987r/xezim-hello-world/actions/runs/42217902632) passed CPU0
C/PULP iDMA frontdoor SRAM↔DDR traffic, real Config NoC initialization,
controller AXI completions, DFI read/write, modeled bank writes and bytes.
This document retains standalone preflight history below; it is no longer
accurate to describe the opt-in full-chip controller as unwired.

## Data versus configuration fabrics

- Keep the 64-bit global/local AXI4 Data NoCs independent from the 32-bit Config NoCs.
- The architectural DDR address window is 0x140000000 through 0x17fffffff (1 GiB). The isolated DDR4 DFI/BankModel supports only the low 32 MiB of that window.
- Translate and validate the full physical address BEFORE driving the LiteDRAM local AXI pins. Do not slice or mask upper address bits or alias unsupported offsets into modeled storage.
- The implemented RTL bridge sends legal DECERR on out-of-range or unsupported accesses, consuming write beats while maintaining AW/W/B/AR/R ordering; the Python contract itself is not a bus responder.
- Validate AWID/ARID, WSTRB, byte widths, burst length, 4 KiB boundary, and ATOP before forwarding. If the crossbar widens ID fields, use an explicit reversible tag mapper rather than silently dropping bits.
- Controller Wishbone/DFII initialization needs a real Config NoC path, resets, init_done and init_error propagation. Do not fake or force initialization or silently preload the controller.
- Use the pinned LiteDRAM controller, simulation PHY and DFI/BankModel; keep the default axi_ram backend available for fast baseline regressions.

## Commands

Run the existing DDR4 Python tests and isolated CI workflow. Then run the contract CLI:

    python3 rtl/memory/ddr4/soc_bridge_contract.py --output .tools/ddr4/ddr_soc_bridge_contract.json

After the pinned controller top has been generated, additionally validate actual exported RTL pins:

    python3 rtl/memory/ddr4/soc_bridge_contract.py --generated-verilog .tools/ddr4/litedram_sim/gateware/soc_ddr4_sim.v

This **standalone CLI's** JSON is intentionally labeled `integration_state=contract_only`; it is not the full-chip controller runtime evidence. The separately verified full-chip run and source files are linked above.

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
same CI job. The isolated bridge test alone is not end-to-end proof;
the separate `chip-ddr4-real` full-chip CPU/iDMA test now provides
that proof within its behavioral-DFI simulation scope.

## Verified standalone report and source provenance

The actual modeled-controller run is [CI 42057781622](https://github.com/r987r/xezim-hello-world/actions/runs/42057781622)
at merged PR head `dd3e9879cc87c2918a78c28931d5af3060029058`.
Its `ddr4-foundation-generated-rtl` artifact includes measured
`ddr4_latency.json`, `ddr4_internal_latency.json`,
`ddr4_dfi_summary.json`, `ddr4_traffic_summary.json`, complete
raw AXI/DFI JSONL, the actual generated `soc_ddr4_sim.v`, warning
audit and pinned source manifest. Read-side AR→DFI/BankModel and
AW→B boundary observations are distinct; **AW→DFI WRITE per-ID remains
unmeasured**. This is standalone modeled controller timing, never a
current-source NoC→DDR latency claim.

## DDR-B Config NoC: implemented 16-KiB controller initialization

The original **standalone** `config_noc_init_contract.py` established
that the former 4-KiB `memory0.ctrl` aperture could not accommodate
the pinned LiteX DDR control/PHY/SDRAM CSR pages. Its old
`contract_only_not_driven_in_full_chip` result remains an accurate
historical standalone *preflight*, not a statement about today's DDR-B
runtime. DDR-B now uses an opt-in 16-KiB window
`0x40030000–0x40033fff`, an independent Config NoC
and synthesizable 32-bit AXI-to-Wishbone transport. During the full-chip
simulation the existing `init_plan.wishbone_script` genuinely executes
43 writes and three readbacks; controller `init_done=1`,
`init_error=0` are required. CPU0 is held in reset while the
preboot Config-NoC AXI initiator is active; the initiator's response
wires are electrically isolated before CPU0 takes control. The normal
fast boot profile is unchanged.

The independent Data NoC routes 64-bit-physical AXI4 transactions
through the Memory0 crossbar to the verified 64→25-bit guarded
`ddr_litedram_axi_bridge` and generated `soc_ddr4_sim`. The
architectural 1-GiB DDR window is unchanged; only the low 32 MiB has
behavioral DFI/BankModel backing. Invalid bursts and addresses must
return DECERR, not wrap into the backing store. The bridge's standalone
invalid-aperture negative passed; the **full-chip routed**
negative also **passed** at final PR head `026cd1f` in
[DDR-B CI 42246102337](https://github.com/r987r/xezim-hello-world/actions/runs/42246102337).
After CPU/iDMA CHECK and drained AXI responses, a simulation-only
master exclusively takes over the existing compute0 DMA NoC manager.
Its `0x142001000` off-model write and read return `DECERR`;
the controller sees no corresponding AW/AR forwarding, and a
subsequent read at `0x140001000` proves that valid data was not
aliased. The default behavioral targets are unchanged.

## Verified status and remaining gates

- **Final-PR-head DDR-B PASS at `026cd1f`:**
  [CI #42246102337](https://github.com/r987r/xezim-hello-world/actions/runs/42246102337).
  Genuine CPU0/PULP iDMA SRAM→DDR→SRAM bytes, complete INIT/RUN/CHECK,
  real controller AW/B and AR/RLAST equality, DFI R/W, bank-model writes,
  passive AXI reports, and source-observed routed negative all passed.
  Earlier positive-only [CI 42217902632](https://github.com/r987r/xezim-hello-world/actions/runs/42217902632)
  remains historical evidence.
- **Preserved:** standalone LiteDRAM/DFI plus bridge/DECERR tests,
  fast default AXI RAM, independent HBM model and merged NoC response-ordering fix.
- **Common boot PASS:** [CI 42246102437](https://github.com/r987r/xezim-hello-world/actions/runs/42246102437)
  passed all five `dv-chip` targets and report/artifact finalization under the
  corrected 65-minute budget.
- **Merged milestone:** [PR #74](https://github.com/r987r/xezim-hello-world/pull/74)
  merged into `main` as [`d6f9612`](https://github.com/r987r/xezim-hello-world/commit/d6f9612a1a391593630ba49ba5384c3866faaf1a);
  [issue #40](https://github.com/r987r/xezim-hello-world/issues/40) closed.
  Later publication and protocol-neutral traffic viewer work remains preserved.
- **Outside DDR-B scope:** physical DDR PHY, JEDEC/silicon timing,
  long forced backpressure/refresh/reset stress (DDR-A #35),
  and joint Ethernet/PCIe-to-*real-controller* traffic (epic #34).
