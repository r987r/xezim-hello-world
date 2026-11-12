# LiteDRAM DDR4 controller and behavioral DFI verification

This directory owns the pinned **real LiteDRAM controller/AXI RTL** with its simulation-only `SDRAMPHYModel` and `BankModel`. The full-chip default DDR target is **AXI RAM**. The separate `chip-ddr4-real` variant uses the real RTL controller behind Memory0 and independent Config NoC initialization; it does not instantiate a silicon/electrical DDR4 PHY.

Sources are pinned by [`config/ip.lock.yaml`](../../../config/ip.lock.yaml) and [`toolchain.lock.yml`](toolchain.lock.yml). Generated Verilog, initialization plan and probe manifest belong under ignored `.tools/ddr4/`, not the tracked SoC `gen/`.

## SystemRDL device mode registers and actual DFII MRS validation

The **virtual** [MR0–MR6 SystemRDL source](../../../csr/rdl/ddr4_mode_registers.rdl)
describes *device protocol mode-register images*, **not** memory-mapped
LiteDRAM CSRs. The native LiteDRAM CSR catalog and its software-driven
DFII MRS initialization remain the single hardware interface; no RDL-
generated shadow CSR bank is instantiated. The first-pass independent
checker in [mrs_check.py](mrs_check.py) compares an observed read-only DFI
MRS stream against all seven upstream-derived mode-register commands and
the source-qualified RDL field layout. Missing, extra, out-of-order or
corrupted commands and premature DFI memory traffic fail the regression.
MR evidence is emitted as `ddr4_mrs_evidence.json` for standalone, opt-in
full-chip DDR and combined Ethernet/DDR/PCIe runs.

**Qualification boundary:** pinned LiteDRAM `SDRAMPHYModel`/`BankModel`
does **not** retain/enforce MR state or verify CL/CWL changes from MRS;
the current checker proves *the command sequence and observed values only*.
No JEDEC tMRD/tMOD, reset/ZQ timing, training, electrical PHY or physical
DRAM qualification is implied. Do not read software-set `init_done` as
independent device-state acceptance. The CSR workflow separately elaborates
the RDL using pinned SystemRDL and checks compiler-produced fields against
the virtual catalog.

## Standalone generation and functional test

```sh
python3 -m unittest discover -s rtl/memory/ddr4 -p 'test_*.py' -v
python3 rtl/memory/ddr4/bringup.py check
python3 tools/ip_fetch.py litedram
python3 rtl/memory/ddr4/bringup.py generate
python3 rtl/memory/ddr4/check_rtl.py --tool verilator
python3 rtl/memory/ddr4/run_functional.py
python3 rtl/memory/ddr4/report_html.py --dir .tools/ddr4/litedram_sim
```

The pinned controller uses a 100 MHz simulation reference clock (10 ns). Wishbone/DFII initialization, controller-facing AXI read/write, low/middle/high geometry, 1/4/8/16-beat bursts, multiple IDs, byte-strobe preservation and concurrency submission have independent RTL tests. Storage is artificially bounded to **32 MiB** inside a larger **1 GiB architectural DDR aperture**; accesses outside the model must be rejected, not aliased. The standalone regression does **not** prove sustained multi-master saturation, long forced stalls, bank/row/refresh collisions, reset/reinitialization or a physical PHY; see [#35](https://github.com/r987r/xezim-hello-world/issues/35).

## Measurements and DFI ownership

The existing continuous passive AXI/Wishbone capture starts before the clock and runs through teardown. Actual AR→final R and AW→B acceptance is paired by AXI ID and order. `ddr4_latency.json` retains per-sample ps, measured clock, min/avg/max cycles and explicit **unmeasured** stages; an RTL compile does not create timing.

A narrow, read-only 72-signal VPI inventory captures four flattened DFI phases and sixteen behavioral BankModels without exposing the entire 32 MiB storage array. Existing `dfi_to_protocol.py` exports real observed DFI READ/WRITE/PRE/REF/ACT and data-enables to the unified protocol viewer. It reuses the upstream model and timing checks; this probe is **not a custom DFI compliance VIP**. An absent ACT event is missing coverage, not something to synthesize in a report.

**Do not correlate AXI AW to DFI WRITE by ID or timestamps alone.** DFI commands have no AXI ID; AXI B can precede BankModel storage commit. The report separately measures AW→B and pairs observed DFI WRITE→BankModel storage events, leaving unsupported AW→DFI attribution **unmeasured**. Read-side stage timing is similarly accepted only when captured boundary pairs exist. These are simulated RTL/controller and behavioral model delays, **not** physical DDR4 performance.

The selective Verilator adapter rejects changes to its read-only signal/public-control allowlist. Compiler raw warnings and exact expected source-pinned diagnostic inventory are retained; warnings are not silently globally suppressed, and a green report-only lint check is not a clean lint result. See [lint qualification](../../../docs/rtl-lint.md) and [#32](https://github.com/r987r/xezim-hello-world/issues/32).

## Opt-in full-chip DDR and aperture safety

```sh
python3 rtl/memory/ddr4/soc_bridge_contract.py --output .tools/ddr4/ddr_soc_bridge_contract.json
python3 rtl/memory/ddr4/bringup.py generate
python3 tools/regress.py chip-ddr4-real --stage build --fail-fast
python3 tools/regress.py chip-ddr4-real --stage run --fail-fast
```

The full-chip configuration uses the real AXI `ddr_litedram_axi_bridge` (64-bit SoC physical addresses → generated 25-bit LiteDRAM local AXI) and **16 KiB** Config-NoC/Wishbone DFII initialization, with real CPU0 C/iDMA SRAM↔DDR data and passive AXI/DFI/BankModel checks. The bridge returns real `DECERR` to out-of-bounds/unsupported bursts without forwarding forbidden AW/AR; the routed negative additionally checks nonalias readback. Full-chip and standalone tests are distinct source-selected runs; they may not borrow each other's measured stage timings. See [bridge/protocol details](SOC_BRIDGE.md) and [integrated functional acceptance](../../../docs/multiprotocol-integration-readiness.md).

## Real forced R-channel backpressure (partial #35 stress gate)

The standalone pinned LiteDRAM functional test now uses the original
`cocotbext-axi` master R-channel pause API to force repeated RREADY-low
intervals during a 512-byte hardware read. The independent always-on AXI
observer records *actual* VALID && !READY cycles and longest consecutive
stall streak on every channel, while the DFI probe stays active. The test
requires at least 12 real stalled R cycles and 8 consecutive stalls, then
checks the original returned bytes and OKAY response. The post-simulation
report verifier independently requires those measurements; simply requesting
a pause without seeing an RTL pin stall is not a PASS.

This demonstrates one bounded read-backpressure and data-integrity case,
**not** #35 completion. Refresh/bank conflict, reset/reinit, W/B stalls,
true measured internal controller concurrency, and silicon DDR PHY remain
unqualified. Source-only unit tests never count as hardware stress evidence.

## Opt-in B-channel response stall qualification

The same standalone LiteDRAM regression now also holds `BREADY` low using the pinned upstream Cocotb AXI master's response-channel pause mechanism while a real controller response asserts `BVALID`. It checks a stable ID/OKAY response through 20 held clock cycles and requires the continuously running independent passive observer to see at least 12 `BVALID && !BREADY` cycles with an 8-cycle sustained streak. After release, the normal write must complete and an independent 256-byte AXI readback must exactly match.

The post-run gate requires both the previous R-channel and the new B-channel observations. This does **not** prove W-channel stalls, refresh/bank contention, reset/reinitialization, true internal outstanding-depth, full-chip physical DDR, or a silicon PHY. The user-side pause is not counted as a hardware stall unless VALID was observed simultaneously.
