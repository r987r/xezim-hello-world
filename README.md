# Configurable SoC Fabric Verification with Xezim

[![HBM AXI4 verification](https://github.com/r987r/xezim-hello-world/actions/workflows/dv-hbm.yml/badge.svg)](https://github.com/r987r/xezim-hello-world/actions/workflows/dv-hbm.yml)

A **configuration-driven, hierarchical SoC verification platform** built around
open-source synthesizable AXI interconnects and the [Xezim](https://github.com/aionhw/xezim)
SystemVerilog simulator. The architecture defines compute subsystems, a memory
subsystem, and separate data and configuration networks. Verification is built
incrementally, from fabric and subsystem testbenches toward a full-chip regression.

## Architecture

`config/soc.yaml` is the source of truth for subsystem instances, NoC boundaries,
address windows, implementation selections, and verification parameters.

- **Compute 0 and Compute 1:** each defines one CPU, one DMA, local SRAM, a
  local AXI4 data fabric, and a separate AXI4-Lite configuration fabric.
- **HBM subsystem:** two AXI4 data ingress ports from the global data fabric,
  a local crossbar, and two controller/memory targets. Either compute subsystem
  can route accesses to either HBM target by address.
- **Global networks:** separate data and configuration planes. Their full RTL
  integration is a later scope; the configuration already describes them.

The initial implemented **HBM fabric DV** uses a genuine 2-input × 2-output
[Verilog-AXI](https://github.com/alexforencich/verilog-axi) AXI4 crossbar,
two independent AXI RAM endpoints, two AXI master stimulus modules, and a
passive route checker. The AXI RAMs are *simulation models*, not HBM PHYs.
The repo also includes a negative test that must detect corrupted expected data.
See [verification architecture and scope](docs/verification.md) for coverage
requirements and the planned compute/global/full-chip levels.

## Quick start

Prerequisites: Linux, `python3`, PyYAML, `git`, and a **prebuilt Xezim**
executable on `PATH` or specified with `XEZIM_BIN`. No Rust build is needed
for HDL tests. The first HBM run fetches pinned public Verilog-AXI RTL.

```bash
python3 -m pip install 'PyYAML==6.0.3'
make check-config
make gen
XEZIM_BIN=/path/to/xezim make dv-hbm
XEZIM_BIN=/path/to/xezim make dv-hbm-negative
```

Run `make help` for commands. To substitute configurations, edit
`config/soc.yaml`; to change the upstream AXI RTL revision, edit
`config/ip.lock.yaml` and validate the replacement.
Generated files and downloaded dependencies live under ignored directories
(`generated/`, `.tools/`). `make gen` creates `generated/hbm/hbm_tb.sv` and
`generated/hbm/manifest.json` deterministically.

## Source layout

| Path | Purpose |
| --- | --- |
| `config/soc.yaml` | Subsystems, interfaces, address maps and test dimensions |
| `config/ip.lock.yaml` | Pinned upstream AXI RTL revision and dependency list |
| `tools/socgen.py` | Schema checks, deterministic testbench generation and metadata |
| `dv/common/` | Reusable AXI master stimulus and passive route monitor |
| `dv/smoke/` | Small dependency-free simulator self-test |
| `scripts/run-dv.sh` | Fetch pinned AXI RTL, run generated SystemVerilog testbench |
| `tests/` | Configuration and generator regression |
| `docs/verification.md` | Verification levels, targets and acceptance criteria |
| `toolchains/xezim.env` | Versioned Linux Xezim release reference |

## CI and simulator provisioning

On code/config changes, [HBM fabric CI](.github/workflows/dv-hbm.yml)
validates the generator, downloads the pinned prebuilt Xezim release, verifies
SHA-256, then simulates the HBM fabric and checks that the negative test fails
for the expected reason. **This job does not install Rust or build Xezim.**

[The simulator publisher](.github/workflows/publish-xezim.yml) runs only when
its definition or simulator version changes (or when explicitly dispatched).
It first checks whether the binary release already exists and avoids building
when possible. Upstream versions and the published Linux asset are pinned in
`toolchains/xezim.env`. CPU/DMA/NoC changes do not run the publisher.

## Extension model

Verification scopes share architecture metadata and reuse AXI components;
changing one IP requires an adapter if its interface differs. The full-chip
implementation is **not** yet present. Follow `docs/verification.md` to add
local NoC, compute, global NoC, and top-level testbenches as separately tested
scopes, rather than duplicating one monolithic testbench.
