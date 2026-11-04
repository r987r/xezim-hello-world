# DDR4 verified foundation (independent of SoC boot)

This directory contains **only the independently generated controller/DFI
simulation configuration, contracts and static tests** for pinned LiteDRAM.
It does **not** instantiate a DDR controller in the chip, replace the existing
AXI SRAM DDR stand-in, or claim that DDR4 data transfers work.

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
  provenance artifacts. It never invokes the CPU/DMA or shared NoC test.

Run on a machine with appropriate Python, LiteX and Verilator dependencies:

    python3 -m unittest discover -s rtl/memory/ddr4 -p 'test_*.py' -v
    python3 rtl/memory/ddr4/bringup.py check
    python3 tools/ip_fetch.py litedram
    python3 rtl/memory/ddr4/bringup.py generate
    python3 rtl/memory/ddr4/check_rtl.py --tool verilator

Use the companion `.github/workflows/ddr4-foundation.yml` for a
reproducible pinned dependency installation, real generation, lint
and downloadable artifacts. All generated output stays in ignored
`.tools/ddr4/`, never the shared generator-owned `gen/` tree.

## Separate, still unfinished DDR functional track

[DDR4 bring-up PR #13](https://github.com/r987r/xezim-hello-world/pull/13)
continues with Wishbone-driven initialization, actual controller/DFI
AXI read/write transactions, byte strobes and passive monitoring.
That functional test **still fails** to complete AXI readback as of this
foundation split. This foundation is safe to share without making
the unfinished functional test an obligatory red gate on `main`.

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
its own monitoring while being debugged in PR #13.
