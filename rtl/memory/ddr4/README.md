# LiteDRAM DDR4 controller and behavioral DFI verification

This directory owns the pinned **real LiteDRAM controller/AXI RTL** with its simulation-only `SDRAMPHYModel` and `BankModel`. The full-chip default DDR target is **AXI RAM**. The separate `chip-ddr4-real` variant uses the real RTL controller behind Memory0 and independent Config NoC initialization; it does not instantiate a silicon/electrical DDR4 PHY.

Sources are pinned by [`config/ip.lock.yaml`](../../../config/ip.lock.yaml) and [`toolchain.lock.yml`](toolchain.lock.yml). Generated Verilog, initialization plan and probe manifest belong under ignored `.tools/ddr4/`, not the tracked SoC `gen/`.

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
