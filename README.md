# Configurable SoC verification with Xezim

[![SoC AXI verification](https://github.com/r987r/xezim-hello-world/actions/workflows/dv-soc.yml/badge.svg)](https://github.com/r987r/xezim-hello-world/actions/workflows/dv-soc.yml)

A **vendor-neutral SoC architecture and verification starter** using public CPU, DMA, AXI fabric, and memory-controller IP. The project generates scoped testbenches and an abstract NoC topology from one configuration, then simulates real RTL with [Xezim](https://github.com/aionhw/xezim).

## Architecture

`config/soc.yaml` is the source of truth. It defines **two different compute subsystems** and **one heterogeneous memory subsystem** connected by logically independent AXI4 data and AXI4-Lite configuration networks.

| Subsystem | IP selection | Interface |
| --- | --- | --- |
| `compute0` | [PicoRV32](https://github.com/YosysHQ/picorv32) + PULP iDMA | CPU AXI4-Lite, DMA AXI4 |
| `compute1` | [SERV](https://github.com/olofk/serv) + PULP iDMA | CPU Wishbone (adapter needed), DMA AXI4 |
| `memory0` | One HBM profile and one DDR profile | Two AXI4 ingress ports, 2×2 local AXI fabric |
| Global data network | FlooNoC architecture selection | AXI4, two outputs into memory subsystem |
| Global config network | PULP AXI selection | AXI4-Lite, separate control addressing |

Either compute subsystem's CPU or DMA should ultimately be able to reach both memory windows by address. **Only the scoped memory fabric and CPU interface smoke tests are wired into running RTL today**; the full-chip interconnect, actual DMA RTL, and end-to-end firmware are later integration work.

The memory targets are deliberately heterogeneous:

| Address | Target | Controller candidate | Currently simulated backend |
| --- | --- | --- | --- |
| `0x1_0000_0000` | HBM0 | [HiSA HBMController](https://github.com/HiSA-Team/HBMController) | Open-source `axi_ram`, unpipelined |
| `0x1_4000_0000` | DDR0 | [LiteDRAM](https://github.com/enjoy-digital/litedram) | Open-source `axi_ram`, pipelined |

The controller projects are **selected, pinned integration candidates—not yet instantiated in the running Xezim testbench**. The HBM controller requires AMD/Xilinx PHY IP in its documented flow. LiteDRAM has a separately generated Verilog controller and open DDR simulation PHY/model. Our initial AXI memory models verify **fabric correctness**, not JEDEC commands, PHY calibration, memory timing, or controller performance.

## Run

Requires Linux, Git, Python 3, PyYAML and an existing Xezim executable. Source RTL is downloaded at locked revisions on first use; HDL tests never compile Rust or rebuild Xezim.

```bash
python3 -m pip install 'PyYAML==6.0.3'
make check-config
make gen
XEZIM_BIN=/path/to/xezim make dv-memory
XEZIM_BIN=/path/to/xezim make dv-memory-negative
XEZIM_BIN=/path/to/xezim make dv-cpu
```

`make test` runs all checks. The memory regression exercises two independent AXI masters against **HBM0 and DDR0**, verifies read/write data, transaction IDs, address decoding, and all four source-to-target combinations. The negative test must fail for an intentional readback mismatch. The CPU smoke test instantiates genuine PicoRV32 and SERV cores and checks for instruction fetch requests; it does not execute real software.

## IP and NoC substitution

- **`config/soc.yaml`** describes topology, subsystem templates, instances, CPU choices, controller profiles, and addresses without committing to vendor-specific RTL module names.
- **`generated/noc/fabric_ir.json`** is the normalized topology artifact: endpoints, logical networks, addresses, backend selections, and which emitters are implemented.
- **`tools/noc_backends.py`** is the backend contract. The executable `verilog_axi` crossbar backend serves the memory test. `pulp_axi` and `floonoc` are registered as **future emitters**, not silently replaced by a toy NoC.
- **`config/ip.lock.yaml`** pins immutable upstream revisions and records controller integration constraints.
- **`rtl/adapters/`** contains explicit IP boundary wrappers; these are not arbitrary protocol adapters, nor do they currently make SERV's Wishbone bus AXI-compatible.

To change a NoC vendor, update its backend selection and implement an emitter consuming the same normalized topology. Unsupported backends must produce a clear error in executable scopes. The architecture and test plans remain independent of the backend. [Architecture and integration contracts](docs/architecture.md) describe this in more detail.

## Tests and CI

| Command | Scope |
| --- | --- |
| `make check-config` | Validate heterogeneous instances, addresses, NoC plugin availability, and determinism |
| `make gen` | Regenerate memory testbench and vendor-neutral NoC topology |
| `make dv-memory` | Exercise a real 2×2 AXI crossbar and two behavioral memory models |
| `make dv-memory-negative` | Confirm checker catches intentionally wrong read data |
| `make dv-cpu` | Elaborate two different public RISC-V CPU cores and observe fetch requests |
| `make smoke` | Minimal simulator self-test |

[GitHub Actions](.github/workflows/dv-soc.yml) reuses the pinned Xezim binary from a versioned release, checks its SHA-256, and **only recompiles/elaborates HDL**. The separate [publisher](.github/workflows/publish-xezim.yml) provisions a new simulator binary only when intentionally needed. No RTL edit triggers a Rust build.

## Layout

```text
config/                 SoC definition and locked public IP revisions
tools/                  Configuration generator, NoC backend interface, IP fetcher
rtl/adapters/           Memory model and distinct CPU boundary modules
dv/common/              AXI master BFMs and passive route checker
dv/cpu/                 Real PicoRV32/SERV elaboration and fetch smoke test
dv/smoke/               Simulator-only smoke test
scripts/                Reproducible Xezim test runners
tests/                  Generator and invalid-configuration regression
generated/              Ignored, deterministic RTL, metadata, NoC topology
docs/                   Stable architecture and verification contracts
```

Future work is organized by verified scopes: local compute NoCs, controller RTL integration, PULP iDMA, global data/config networks, and then full-chip tests. See [verification plan](docs/verification.md).
