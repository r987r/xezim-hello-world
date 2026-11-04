# DDR4 verified foundation (independent of SoC boot)

This directory contains the independent LiteDRAM controller/DFI simulation
configuration, contracts, and standalone functional verification. The
**foundation merged to main in PR #21**; the real AXI read/write functional
test was merged through **PR #22**, without wiring DDR into the chip.
The full-chip DDR address map still uses the original AXI SRAM stand-in.

The implementation uses the upstream LiteDRAM source pinned in
`config/ip.lock.yaml` (SHA `3506dc02e2b790011c1c147e2aad4541a6ddf836`),
plus an independently pinned compatible LiteX source from
`toolchain.lock.yml`. The generator writes an inspectable Verilog top,
a SHA-256 manifest, and a machine-readable upstream DDR4 DFII
initialization **plan**. Those do not constitute a passing boot/init/data
simulation.

## Validated standalone milestone

- DDR4 controller, AXI frontend and DFI simulation PHY/model are generated
  from upstream LiteDRAM; no custom DDR controller or vendor RTL patches.
- Python contract tests check the memory0.ddr0 address range, NoC AXI
  widths, configured pin, generated top AXI input/output directions,
  Wishbone control pins and initialization/status signals.
- Simulation-only geometry bounds the modeled storage at 32 MiB for
  practical CI memory footprint (the architectural DDR aperture remains
  1 GiB and has **not** been wired to this model). This is not valid
  production DDR4 silicon geometry.
- The generated RTL is checked with Verilator lint against its actual
  port map. This is **not** proof of JEDEC initialization or AXI data.
- The standalone CI job runs these checks and uploads the RTL and
  provenance artifacts. The same job also executes real DDR4
  controller initialization and AXI functional traffic; it never invokes
  the CPU/DMA or shared NoC test.

Run on a machine with appropriate Python, LiteX and Verilator dependencies:

    python3 -m unittest discover -s rtl/memory/ddr4 -p 'test_*.py' -v
    python3 rtl/memory/ddr4/bringup.py check
    python3 tools/ip_fetch.py litedram
    python3 rtl/memory/ddr4/bringup.py generate
    python3 rtl/memory/ddr4/check_rtl.py --tool verilator
    # For isolated real controller/PHY functional simulation (PR #22):
    python3 -m pip install 'cocotb==1.9.2' 'cocotbext-axi==0.1.28' 'cocotb-test==0.2.6'
    python3 rtl/memory/ddr4/run_functional.py

Use the companion `.github/workflows/ddr4-foundation.yml` for a
reproducible pinned dependency installation, real generation, lint
and downloadable artifacts. All generated output stays in ignored
`.tools/ddr4/`, never the shared generator-owned `gen/` tree.

## Real DDR4 controller/DFI functional verification (PR #22)

[New functional-debug PR #22](https://github.com/r987r/xezim-hello-world/pull/22)
starts from the merged foundation; it does **not** import all of old draft
[PR #13](https://github.com/r987r/xezim-hello-world/pull/13).

In [actual GitHub Actions run #41900532310](https://github.com/r987r/xezim-hello-world/actions/runs/41900532310)
the pinned controller and DFI memory model **passed** Wishbone/DFII
initialization, a prewrite AXI read, 64-byte/32-byte/24-byte pattern
write/readback with AXI IDs 1/2/3, and a 5-byte partial update preserving
untouched neighbors. All responses were OKAY and read data matched expected.
Independent end-to-end passive coverage verification also passed over
**121,229 clock cycles** with 5 AR, 4 AW, 4 B, 19 R and 17 W handshakes.
The functional CI uploaded complete JSONL and summary trace artifacts.

The old PR #13's AXI receive timeout was **reproduced** with both
cocotbext-axi 0.1.24 and 0.1.28 while the AXI master sampled exported
`user_clk` and optional RREADY backpressure was active. The passing
PR #22 setup aligns the active AXI BFM with `dut.clk` (the source clock
of LiteDRAM's simulation CRG), removes experimental RREADY pause, and
samples Wishbone ACK in the resolved read-only simulator phase.
We have verified this **combination** fixes the test; we have **not**
individually isolated which scheduling adjustment was decisive.
The passive monitor remains continuously active from before the first
clock edge through initialization, all traffic, and teardown.

**Not yet proven:** ASIC/physical DDR PHY, JEDEC behavior beyond the
LiteDRAM simulation PHY/model, full-size DDR4 capacity, multi-controller
SoC integration, CPU/DMA boot traffic to real DDR, or Xezim functional
execution of this generated DDR controller. Those require separate gates.

Do not make significant changes to `config/`, `tools/full_chip_gen.py`,
`Bender.yml`, CPU/DMA/boot software, canonical diagrams or shared
RTL in this track. Wait until the other boot/DMA PRs stabilize and obtain
explicit approval before integrating real DDR4 into the chip.

## Monitor lifecycle policy

The small `tests/test_axi_monitor_lifecycle.py` test statically verifies
that every **report-enabled** cocotb full-chip/NoC test attaches the
existing upstream passive AXI capture **before starting its DUT clock**
and does not cancel it during the test. The regression runner also
requires capture events for successful report-enabled tests. This
does not add or replace a second AXI monitor and does not modify
tests being changed by concurrent DMA and fabric PRs.

Standalone `dma-rtl` in PR #14 is an explicitly documented exception:
it exercises a direct cocotbext-axi target without a FlooNoC monitor
catalog; the integrated `chip-dma` regression already enables the
full passive fabric report. The isolated DDR functional harness uses
its own all-simulation AXI/Wishbone monitoring on PR #22.


## DDR4 timing evidence and modeling boundaries (new isolated PR)

The isolated DDR4 model now **declares and drives the same 100 MHz
simulation clock**: input_clk_freq=sys_clk_freq=100000000, source clock
period 10 ns. It matches the currently measured 100 MHz full-chip fabric
reference, but there is **no instantiated connection** between those
two simulation scopes. It is *not* a statement of physical DDR4 speed.
The unused, physical Xilinx IODELAY reference field in the isolated
--sim profile remains 300 MHz; SDRAMPHYModel does not instantiate it.
A future 150/159 MHz controller alongside the 100 MHz fabric requires
an actual AXI CDC implementation, independent clocks, and per-domain
timestamps; do not directly wire two asynchronous AXI clocks.

After a successful cocotb DDR functional run, `latency_report.py`
correlates traffic-phase accepted AXI AR-to-final-R and AW-to-B handshakes
using the actual captured AXI ID and request order. It writes
`ddr4_latency.json` with per-transaction samples, min/avg/max cycles,
raw picosecond durations, clock period, model inventory, and explicit
unmeasured stage labels. Generation or lint alone never produces valid
timing. The code reuses the existing *continuous* DDR4 AXI/Wishbone
monitor and verifies its start/end records, full phase coverage and
handshake accounting before accepting latency results. Samples include
the real RTL controller/AXI frontend, SDRAMPHYModel, BankModel, and
response processing, but are **not** a component-level decomposition.

Model inventory, accurately labeled:
- **Real RTL:** pinned LiteDRAM AXI frontend/controller, bank machines,
  scheduler, queues, arbitration and refresh; controller events beyond
  the external AXI boundary are not yet exported as standalone probes.
- **Modeled:** LiteDRAM DFI-level `SDRAMPHYModel` and its configured
  command/data latency pipeline, DDR4 `BankModel` backed by dense
  simulation storage with a bounded 32 MiB geometry.
- **Not modeled:** an electrical/physical DDR4 PHY, IO pad timing,
  training, DDR4 analog behavior, and a physical JEDEC DDR4 device.
- **Not connected:** the shared SoC's full-chip DDR aperture still
  ends at a bounded AXI SRAM stand-in. Fabric Explorer's verified
  NoC stages and this standalone timing report are separately sourced;
  **do not sum** them until real end-to-end DDR integration passes.

Future distinct controller/DFI/bank stage timing requires exposing and
validating stable generated-RTL signals, including DFI per-phase READ/
WRITE commands, `rddata_en`, `rddata_valid`, write data, and
BankModel access. Only measured boundaries may receive numeric values.
Keep unavailable entries `unmeasured` rather than guessing a breakdown
from PHY configuration. A high-outstanding/concurrent test additionally
needs a verified mapping through bank-machine queues because DFI
commands do not retain AXI IDs.

The planned final integration PR reuses this report's schema, attaches
a real 64-bit-to-local-AXI address adapter and CSR init path, and adds
full-chip tests with the existing NoC monitors. No shared generator,
clock domain, NoC, DMA, boot, or diagrams were changed for standalone
timing instrumentation.

## Experimental internal DFI and BankModel probes (follow-up PR)

The merged 100 MHz latency report measures accepted AXI AR to last R
and AW to B against real LiteDRAM RTL and behavioral SDRAMPHYModel/BankModel.
This stage observes actual flattened DFI command and modeled-bank events
in the generated Verilog, without changing the pinned vendor RTL.

dfi_probe_contract.py validates 72 pinned generator signals and creates
a narrowly scoped Verilator public_flat_rd control file. It does NOT
expose the 32 MiB backing memory or enable global --public-flat-rw.
Four DFI phases are monitored (command, rddata_en, rddata_valid, wrdata_en),
plus all sixteen behavioral bank models (read, storage write-enable).

Evidence files: ddr4_dfi_events.jsonl, ddr4_dfi_summary.json,
ddr4_probe_contract.json, and ddr4_internal_latency.json. The merged
ddr4_latency.json remains the independent AXI boundary baseline.

Controller command scheduling and DFI outputs come from real LiteDRAM RTL.
DFI return delay and model storage are behavioral SDRAMPHYModel/BankModel.
Neither an ASIC physical PHY nor a physical DDR4 chip is present.
DFI commands do not carry AXI IDs; overlapping requests are explicitly
not attributed to particular transactions. Write B and modeled DRAM
storage commit are separate events.

Only observed stage intervals are numeric; unmatched steps are unmeasured.
Actual clock timestamps are in picoseconds, initially at one 100 MHz
simulation clock. Full-chip DDR remains a separate opt-in integration PR.
Tests and successful real-model CI evidence are required before asserting
that these internal latency checkpoints are validated.

### Existing DFI verification reuse (explicit audit)

This PR does NOT implement a new DFI protocol VIP. It uses the existing
pinned upstream LiteDRAM DFIPhaseModel, DFITimingsChecker (when enabled),
SDRAMPHYModel and BankModel as the simulation/semantic owners. The small
memory-local DFIProbe is only a read-only event/timestamp recorder; it
must never be treated as DFI compliance verification.

An open-source MIT-licensed cocotb DFIMonitor with packet queues and
scoreboard exists in sean-galloway/RTLDesignSherpa-DV:
https://github.com/sean-galloway/RTLDesignSherpa-DV/blob/main/src/CocoTBFramework/components/dfi/dfi_monitor.py

However, it expects a single prefixed mc_dfi/phy_dfi bus with clock
and DDR3-style RAS/CAS/WE decoding, whereas our pinned LiteDRAM generator
exports four flattened DFI phases and DDR4 ACT_N. Reuse requires a
validated four-phase adapter and correct DDR4 command handling, not
blindly copying or inserting the monitor. Before adding protocol-checking
features, prefer reusing this library or upstream LiteDRAM timing checks.

The read-only timestamp tap is allowed to remain small and local, but
no custom DFI driver, checker, DRAM state machine or PHY should be built.
Internal latency results are provisional until actual CI proves them.

## CI diagnostic policy (follow-up to warning audit)

The pinned `cocotb-test==0.2.6` Verilator wrapper unconditionally requested
global `--public-flat-rw`. Our DDR4-only `selective_verilator.py` adapter
checks the **actual** compiler command and removes that flag, while retaining
`--vpi` and the generated `public_flat_rd` control file for 72 DDR4
DFI/BankModel probes. Any upstream compiler-command change fails closed.
The normal DDR4 top-level control/AXI pins remain normal Cocotb ports.

Verilator compiler stderr is saved **verbatim** to
`ddr4_simulation_compiler.log`, rather than displaying thousands of
`ERROR cocotb` lines for warning explanations. Real compiler errors are
still printed; `ddr4_warning_audit.json` counts actual diagnostic messages.
The pinned generated-model warning inventory from merged #24 is
1,709 WIDTHEXPAND, 254 WIDTHTRUNC and 84 CASEINCOMPLETE. This is an exact
review-required baseline, **not a blanket warning suppression**. A changed,
missing or additional warning or any %Error causes CI failure even if
Verilator exits 0 with `-Wno-fatal`.

The current simulation changes 32768 physical rows / 1024 columns into
2048 rows / 128 columns to bound modeled storage at 32 MiB. DFI command
address remains 15 bits, while modeled row/column storage is narrower.
Review of width truncation and alias boundaries remains required before
treating the model as any form of physical DDR proof. Both raw compiler
logs and the post-run diagnostic inventory are retained in the CI artifact.
