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
  scheduler, queues, arbitration and refresh. A **selective, read-only
  72-net Verilator VPI probe** now captures DFI/BankModel events and measured
  controller-to-DFI read-side stage boundaries; it does not replace a DFI
  protocol checker or prove silicon timing.
- **Modeled:** LiteDRAM DFI-level `SDRAMPHYModel` and its configured
  command/data latency pipeline, DDR4 `BankModel` backed by dense
  simulation storage with a bounded 32 MiB geometry.
- **Not modeled:** an electrical/physical DDR4 PHY, IO pad timing,
  training, DDR4 analog behavior, and a physical JEDEC DDR4 device.
- **Not connected:** the shared SoC's full-chip DDR aperture still
  ends at a bounded AXI SRAM stand-in. Fabric Explorer's verified
  NoC stages and this standalone timing report are separately sourced;
  **do not sum** them until real end-to-end DDR integration passes.

The merged selective probe measures DFI per-phase READ/WRITE commands,
`rddata_en`, `rddata_valid`, and modeled bank accesses with
`ddr4_internal_latency.json` generated after real simulation.
Only matched, observed stage boundaries receive numeric values. The
AXI AW-to-DFI WRITE relationship remains **unmeasured**: DFI commands
have no AXI IDs and AXI B can precede model bank storage. High-outstanding
correlation additionally requires verified bank-machine queue mapping;
never guess missing timing from PHY configuration.

The planned final integration PR reuses this report's schema, attaches
a real 64-bit-to-local-AXI address adapter and CSR init path, and adds
full-chip tests with the existing NoC monitors. No shared generator,
clock domain, NoC, DMA, boot, or diagrams were changed for standalone
timing instrumentation.

## Captured internal DFI and BankModel probes (merged #26)

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
Actual timestamps are in picoseconds, for the standalone 100 MHz
simulation clock. The internal probe checkpoints were exercised in the
passing [combined real RTL CI run 42057781622](https://github.com/r987r/xezim-hello-world/actions/runs/42057781622).
Full-chip Memory0 DDR remains separately unconnected; these measured
model checkpoints are not a physical PHY/DRAM benchmark.

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
Internal event timing is accepted only when the real-model CI captures
and reconciles complete DFI/BankModel evidence. Those measured intervals
are simulation-stage observations, not DFI compliance or silicon latency.

## CI diagnostic policy (follow-up to warning audit)

The pinned `cocotb-test==0.2.6` Verilator wrapper unconditionally requested
global `--public-flat-rw`. Our DDR4-only `selective_verilator.py` adapter
checks the **actual** compiler command and removes that flag, while retaining
`--vpi` and an explicit control file. The file whitelists top-level DUT ports
as read/write for Cocotb (including `clk`) and **only** the 72 DFI/model
internal signals as read-only. No memory array is exposed. Any upstream
compiler-command change fails closed.

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

The functional regression additionally writes distinct 64-byte patterns to
the low, middle and final 64-byte locations of the 32 MiB modeled aperture,
**then rereads all three after the writes**. Any byte alias caused by reduced
row/column geometry fails the DDR4 CI; this is an explicit simulation-model
boundary check, not a claim about physical DDR4.

### DDR4 write-completion attribution correction

The full CI evidence showed all seven DFI WRITE and BankModel storage-write
events, but six physical writes happened **after their AXI B handshake**.
The old AW-to-B timestamp filter therefore missed six writes and falsely
attributed one earlier DFI WRITE to a later AXI AW. This was not real
per-AXI write scheduling evidence and is deliberately removed.

`controller_aw_to_dfi_write` now stays **unmeasured** until a verified
controller queue/physical bank correlation exists. `AXI AW->B` remains
independently measured and does NOT mean DRAM storage completed.
`dfi_write_to_bankmodel_storage` is instead paired independently by
actual DFI command and matching BankModel bank-write-enable, rejecting
multiple or absent candidate commits. The positive smoke test fails unless
all DFI WRITE events have unique modeled storage evidence and relevant
read-model stages are measured. These remain behavioral model delays, not
silicon DDR timing.

## DDR-A stress traffic and provenance (PR #50)

The real standalone `functional_tb.py` uses deterministic stress vectors from
`stress_matrix.py` **after** completing real LiteDRAM DFII/Wishbone init and
baseline controller/DFI readback. These are issued through the existing
`cocotbext-axi` master and passively observed by the same continuous AXI,
Wishbone, DFI and simulated bank monitors (not substitute memory responders).

The stress phase exercises burst lengths 1/4/8/16, IDs 0 and 15, low/mid/high
locations within the **32 MiB simulated model**, real byte strobes generated
from unaligned contiguous writes, and independent whole-burst readback with
untouched-byte checking. A sparse 0x55 strobe case is split into legal
individual byte writes because the pinned upstream `AxiMaster.write()`
does not provide a user-directed arbitrary WSTRB mask. Consequently we
**do not claim** true single-beat arbitrarily sparse WSTRB coverage.

[Exact-head CI run 42038475513](https://github.com/r987r/xezim-hello-world/actions/runs/42038475513)
passed: 99 DDR4 Python tests, 7 monitoring-policy tests, real LiteDRAM
controller/DFI model test 1/1, 121,795 sampled cycles and complete
AR=16/AW=18/B=18/R=101/W=77 observations. Existing upstream generated
warnings: CASEINCOMPLETE=84, WIDTHEXPAND=1709, WIDTHTRUNC=254, RTL
compiler errors=0. No warnings were silently waived; the exact
expected warning inventory remains a strict gate.

Outstanding in DDR-A: multi-master concurrent ID stress, long forced stalls,
bank/row conflict and forced refresh sequences, reset/reinitialization, and
expanded timing distributions. Standalone DDR model does not constitute
physical PHY or integrated SoC controller verification. DDR-B integration
is separately tracked under #40; main's DDR0 backing stays AXI RAM until
real controller is opt-in, generated, and end-to-end verified.


## DDR-A concurrent AXI traffic and reviewable evidence (PR #65)

The existing real LiteDRAM + SDRAMPHYModel/BankModel standalone test now
also starts four independent 128-byte AXI writes without waiting for each
completion, then starts four independently tagged reads (IDs 0/5/10/15).
Each returns a checked B/R response with independent golden readback. All
five AXI channels, Wishbone/DFII initialization and read-only DFI/bank probes
remain under the same continuous passive capture, with no new bus monitors.
This verifies simultaneous submission, **not a proven controller-internal
outstanding depth**, and it does not force long backpressure, a refresh/bank
collision or reset/reinit. Those gates remain open on #35.

The isolated DDR4 CI now generates
`.tools/ddr4/litedram_sim/ddr4-report.html` **only after** real RTL
simulation, passive capture and AXI/DFI latency correlation succeed.
The single HTML review report includes actual measured min/avg/max
AR→last R / AW→B cycles and DFI/BankModel stage evidence. Ambiguous
AXI AW→DFI WRITE attribution stays **UNMEASURED**, rather than being
inferred from early B responses. Reports are uploaded alongside the
controller RTL, pinned source manifest, raw AXI/DFI traces and the 2,047
audited upstream width/case diagnostic baseline in the existing
`ddr4-foundation-generated-rtl` workflow artifact. The Pages build
for unrelated branches never publishes this as full-chip fabric latency.

To inspect after the standalone CI completes: open its GitHub Actions run,
download the `ddr4-foundation-generated-rtl` artifact, and open
`litedram_sim/ddr4-report.html`. Local rerun:

~~~sh
python3 rtl/memory/ddr4/run_functional.py
python3 rtl/memory/ddr4/report_html.py --dir .tools/ddr4/litedram_sim
~~~

Full-chip DDR-B integration remains separate: memory0.ddr0 uses AXI RAM
until real controller RTL is connected via the generated Data NoC, Wishbone
initialization through the independent Config NoC, and CPU/iDMA traffic
with current-source regression evidence. See `SOC_BRIDGE.md`, #40/#38.


## DDR-A controller-output backpressure coverage

The existing pinned `cocotbext-axi==0.1.28` master `AxiRSink` and
`AxiBSink` now exercise controlled periodic sink pauses on eight 256-byte
actual LiteDRAM readbacks/writes with eight distinct AXI IDs. The existing
read-only `TrafficObserver` independently measures cycles where the DUT
asserts RVALID or BVALID while the master deasserts RREADY or BREADY.
The Cocotb test requires nonzero **observed** stalls, OKAY completions and
byte-for-byte readback, and the existing full AW/W/B/AR/R/DFI passive
capture stays on throughout. No new BFM, protocol monitor, SRAM model or
external test runner is introduced. The standalone `ddr4-report.html`
now includes these per-channel stall counts alongside measured AXI latency.

This is controller-output B/R backpressure only. It does **not** prove
refresh/bank conflicts, reset/reinitialization, sustained upstream
AW/W throttling, or a minimum controller-internal queue occupancy; those
are separate #35 acceptance gates. Measured model intervals are
simulation performance, not a physical DDR PHY or full-chip NoC result.
