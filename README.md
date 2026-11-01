# Xezim Hello World testbench

A minimal self-checking SystemVerilog smoke test for [Xezim](https://github.com/aionhw/xezim) 0.11.3.

The example contains an 8-bit two-input adder and a testbench that prints Hello World, checks 20 + 22 = 42, checks 255 + 1 = 256 (carry), checks unknown-value propagation, and reports **PASS**.

## Run locally

Requirements: Linux/macOS and Make. Rust/Cargo 1.92+, Git and a C compiler are needed only if Xezim must be built from source.

    git clone https://github.com/r987r/xezim-hello-world.git
    cd xezim-hello-world
    make test

The runner prefers an executable specified by `XEZIM_BIN`, then a cached local build, then an `xezim` executable found on `PATH`. Only if no executable is available does it download Xezim into the ignored `.tools` directory and build it from source with low-memory Rust release settings. CI caches the resulting executable, so later jobs normally skip the Rust build.

## Verified output (Linux, Nov 1, 2026)

    === xezim 0.11.3 ===
    git 058f2bb (2026-10-23T17:05:55-07:00)
    Hello, World! Running on Xezim.
    PASS: hello_world_tb
    Simulation finished at time 3000 ($finish called)

Xezim compilation and execution completed with exit code 0. The real run is also captured in [test-results.txt](test-results.txt).

## Files

- [rtl/hello_world.sv](rtl/hello_world.sv): combinational RTL
- [tb/hello_world_tb.sv](tb/hello_world_tb.sv): self-checking testbench
- [scripts/run.sh](scripts/run.sh): reproducible build and run
- [Makefile](Makefile): make test
- [.github/workflows/xezim-smoke.yml](.github/workflows/xezim-smoke.yml): CI on pushes/PRs or manually

You can supply `XEZIM_BIN=/path/to/xezim` to use an existing simulator binary; set `XEZIM_VERSION` to select another tag on first clone.

**Upstream releases have no precompiled release assets** as checked on 2026-11-01 ([0.11.3](https://github.com/aionhw/xezim/releases/tag/0.11.3), [0.11.4](https://github.com/aionhw/xezim/releases/tag/0.11.4)); their GitHub release archives are source-only. Build Xezim just once on each target platform, or retrieve the CI-cached binary.

The optimized upstream release build needed more than 4 GiB of RAM. This runner reduces memory use by compiling with one job, without LTO, with 16 codegen units and opt-level 1.