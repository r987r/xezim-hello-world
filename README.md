# Xezim SystemVerilog smoke test

[![SystemVerilog CI](https://github.com/r987r/xezim-hello-world/actions/workflows/xezim-smoke.yml/badge.svg)](https://github.com/r987r/xezim-hello-world/actions/workflows/xezim-smoke.yml)

A small, self-checking SystemVerilog project that demonstrates how to compile, elaborate, and run a testbench with [Xezim](https://github.com/aionhw/xezim).

The example adds two 8-bit values and checks ordinary addition, carry propagation, and unknown-value behavior. It succeeds only when the simulator prints `PASS: hello_world_tb`.

## Run locally

With an installed `xezim` on `PATH`, no Rust installation is needed:

```bash
git clone https://github.com/r987r/xezim-hello-world.git
cd xezim-hello-world
make test
```

To select a specific executable, run `XEZIM_BIN=/path/to/xezim make test`. If no simulator executable is available, the runner clones and compiles the pinned Xezim version **once**, under the ignored `.tools/` directory. This first-time local fallback requires Git, Rust/Cargo (1.92+), and a C compiler.

`make test` invokes `scripts/run.sh`, which performs HDL compilation, elaboration, simulation, and PASS-marker validation.

## Repository layout

| Path | Purpose |
| --- | --- |
| `rtl/hello_world.sv` | Combinational example design |
| `tb/hello_world_tb.sv` | Self-checking testbench |
| `scripts/run.sh` | Repeatable command-line test runner |
| `toolchains/xezim.env` | Pinned simulator version, upstream commit, and Linux release asset |
| `.github/workflows/publish-xezim.yml` | Provision the versioned Linux executable when needed |
| `.github/workflows/xezim-smoke.yml` | Run SystemVerilog tests using that executable |

## Continuous integration

**SV test workflow:** Changes to RTL, testbench, or the test runner automatically run `make test`. The job downloads the pinned Linux x86_64 executable from this repository's GitHub Releases, verifies its SHA-256 checksum, and runs the simulation. **It does not install Rust or rebuild Xezim.**

**Simulator publishing workflow:** Only a change to the simulator pin or the publisher workflow (or an intentional manual dispatch) starts provisioning. It checks for an existing release before building, validates the simulator with the smoke test, and publishes the binary alongside its checksum. A successful publication triggers the SV workflow automatically.

Releases are durable versioned assets; CI caches are only a speed-up for retrying the publisher. Ordinary SV changes never trigger the publisher.

## Upgrading Xezim

Edit the values in `toolchains/xezim.env`: version, full upstream commit, release tag, and asset name. Commit the change to `main`. The publisher will prepare the new pinned simulator if it is not already available, and then the SV smoke test will run. The prior binary remains available for existing users.

The current automated distribution targets **Linux x86_64**. Other platforms can use a locally installed Xezim binary and can be added as separately versioned release assets.

## Adding tests

Place RTL in `rtl/` and testbenches in `tb/`. Update the top module and source list passed to Xezim in `scripts/run.sh` when adding a new design or test suite. Keep each test self-checking and return a nonzero exit status on failure.
