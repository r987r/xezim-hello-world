# DDR4 verified foundation (independent of SoC boot)

This directory contains the independent LiteDRAM controller/DFI simulation
configuration, contracts, and standalone functional verification. The
**foundation merged to main in PR #21**; the real AXI read/write functional
test is being validated on **PR #22**, without wiring DDR into the chip.
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
  provenance artifacts. On PR #22, the same job also executes real DDR4
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
