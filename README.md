# Config-driven SoC RTL and verification with Xezim

[![SoC regression](https://github.com/r987r/xezim-hello-world/actions/workflows/dv-soc.yml/badge.svg)](https://github.com/r987r/xezim-hello-world/actions/workflows/dv-soc.yml)

A reusable, **configuration-driven hierarchical SoC test vehicle** built from publicly available RTL. One `config/soc.yaml` selects compute subsystems, CPU IP, reserved DMA interfaces, memory targets, data/config NoCs, addresses, and verification scopes. The same configuration generates **SystemVerilog testbench code, NoC connectivity metadata, executable test plans, 2D diagrams, and this README's architecture section**. No DMA engine is currently instantiated.

The [GitHub Pages verification hub](https://r987r.github.io/xezim-hello-world/)
publishes this README, all documentation, the canonical topology and actual CI
test results with tested commits, logs and AXI traffic reports.
See [publication and retention](docs/publication.md).

## Architecture, real RTL connectivity, and verification

<!-- BEGIN GENERATED SOC -->

<!-- Do not edit this section: regenerate with `make gen`. -->
### Whole-SoC data and configuration NoCs

The **single architecture diagram** below includes all local/global FlooNoCs, compute CPU/DMA/SRAM blocks and memory target crossbar. It is generated from the same SoC configuration and FlooGen endpoint topology as the real structural RTL. **Dashed links show pending iDMA/controller integration.** The shared NoC core is instantiated by both the BFM regression and the CPU boot configuration.

[![Complete hierarchical SoC and all data/config FlooNoCs](gen/diagrams/noc-hierarchy.svg)](gen/diagrams/noc-hierarchy.svg)

[Full-size diagram](gen/diagrams/noc-hierarchy.svg) · [Editable Mermaid](gen/diagrams/noc-hierarchy.mmd) · [Machine-readable router/NI/link graph](gen/diagrams/noc-topology.json) · [Real generated FlooNoC RTL](gen/noc/floonoc/manifest.json)

**Configured topology:** 2 compute subsystems, 8 independent FlooNoC instances, 43 total generated routers. Data: 64-bit AXI4; control: 32-bit AXI4 transport for AXI4-Lite endpoint bridges. CPU/reset adapters are attached in the boot configuration; the BFM scope uses AXI agents.

**Verification truth:** Xezim exercises separate CPU cold-boot/SRAM and Verilog-AXI memory testbenches. Both Xezim and Verilator have compiled the eight structural FlooNoCs. The unified `make dv-supernoc` regression connects all meshes to upstream AXI agents and checks destinations, data, bursts, concurrent IDs, stalls and downstream SLVERR. Xezim NoC traffic is not verified. The `make dv-chip` boot configuration runs the real CPUs through the shared NoCs with CPU0-coordinated init/run/check and AXI memory stand-ins. See [chip boot scope](docs/full-chip-boot.md).

### Generated NoC sources (no duplicate pictures)

| Network | Routers | Generated top | Config |
| --- | ---: | --- | --- |
| `compute0_local_config` | 6 | [SystemVerilog](gen/noc/floonoc/compute0/local_config/floo_xezim_compute0_local_config_noc.sv) | [FlooGen YAML](gen/noc/floonoc/compute0/local_config/floogen.yaml) |
| `compute0_local_data` | 9 | [SystemVerilog](gen/noc/floonoc/compute0/local_data/floo_xezim_compute0_local_data_noc.sv) | [FlooGen YAML](gen/noc/floonoc/compute0/local_data/floogen.yaml) |
| `compute1_local_config` | 4 | [SystemVerilog](gen/noc/floonoc/compute1/local_config/floo_xezim_compute1_local_config_noc.sv) | [FlooGen YAML](gen/noc/floonoc/compute1/local_config/floogen.yaml) |
| `compute1_local_data` | 6 | [SystemVerilog](gen/noc/floonoc/compute1/local_data/floo_xezim_compute1_local_data_noc.sv) | [FlooGen YAML](gen/noc/floonoc/compute1/local_data/floogen.yaml) |
| `global_config` | 6 | [SystemVerilog](gen/noc/floonoc/global_config/floo_xezim_global_config_noc.sv) | [FlooGen YAML](gen/noc/floonoc/global_config/floogen.yaml) |
| `global_data` | 6 | [SystemVerilog](gen/noc/floonoc/global_data/floo_xezim_global_data_noc.sv) | [FlooGen YAML](gen/noc/floonoc/global_data/floogen.yaml) |
| `memory0_local_config` | 2 | [SystemVerilog](gen/noc/floonoc/memory0/local_config/floo_xezim_memory0_local_config_noc.sv) | [FlooGen YAML](gen/noc/floonoc/memory0/local_config/floogen.yaml) |
| `memory0_local_data` | 4 | [SystemVerilog](gen/noc/floonoc/memory0/local_data/floo_xezim_memory0_local_data_noc.sv) | [FlooGen YAML](gen/noc/floonoc/memory0/local_data/floogen.yaml) |

**Validation and generated metadata:** [NoC interface budgets](config/interface_contracts.yaml) · [routing IR](gen/noc/fabric_ir.json) · [memory testbench](gen/memory/memory_tb.sv) · [verification plan](gen/verification/plan.json) · [generated tree manifest](gen/manifest.json).

<!-- END GENERATED SOC -->

## Current implementation status and agent runbook

**Working today:** Xezim executes real PicoRV32/SERV cold boot and the
open-source 2x2 Verilog-AXI memory crossbar (full and sparse routing).
**All eight local/global FlooNoC structural RTL modules are generated
and checked in**, and Verilator has independently elaborated all eight
using pinned upstream Bender dependencies. The generated `supernoc_tb`
connects all eight through eleven AXI4 links with six upstream managers
and nine mapped sparse BFM targets. `make dv-supernoc` checks routed
traffic; see [coverage and results](docs/supernoc-verification.md).
**Chip boot configuration:** `gen/chip/soc_top.sv` adds real CPU/SRAM/reset
attachments, upstream WB/AXI/width adapters, and a memory target crossbar
with AXI slave stand-ins. `make dv-chip` checks CPU0-coordinated init/run/check.
**Still pending:** real iDMA/CSR/interrupt integration and HBM/DDR controllers/PHY.
See [full-chip boot](docs/full-chip-boot.md) for the precise scope.

For source-backed maturity and outstanding work, see
[implementation status](docs/implementation-status.md); the single diagram
above is the only generated SoC architecture picture.
Future coding agents **must** follow [AGENTS.md](AGENTS.md), including pinned
Xezim binary installation, `make gen`, `make check-generated`, the full
YAML-defined regression, including both AXI routing profiles. Never hand-edit
`gen/` or silently replace a missing upstream backend.

## View real generated FlooNoC Verilog

The tracked `gen/noc/floonoc/` directory holds **eight upstream
FlooGen-generated router/chimney structural SystemVerilog tops, typed
packages, exact generated configuration profiles, and a source manifest**.
They are regenerated by `make gen` from the SoC YAML and the native
interface sizing contracts, and verified by `make check-generated`. The
[full network diagram](gen/diagrams/noc-hierarchy.svg) and
[Diagram-gen-compatible connectivity metadata](gen/diagrams/noc-topology.json)
come from the same generated FlooGen mesh configurations, not a second
hand-maintained topology.
The upstream FlooNoC/AXI/common_cells libraries are not copied into
`gen/`; they are resolved from pinned sources. **Generated != elaborated
or traffic-tested**. For AXI-Lite control networks, reuse the real PULP
AXI adapters documented in
[AXI-Lite-over-FlooNoC](docs/axi-lite-over-floonoc.md). Both
**Verilator 5.020 and pinned Xezim compile all eight generated NoCs**,
but Xezim reports width warnings in the four data meshes. The
[simulator compatibility audit](docs/simulator-compatibility.md)
records these; compilation is not routed-traffic verification.

## FlooNoC fabric policy

All **local data/config** and **global data/config** NoCs use pinned upstream
FlooNoC, with independent mesh instances. Inside memory0, the verified
Verilog-AXI target crossbar is attached downstream of the memory-local NoC
in the chip boot configuration, with AXI slave memory stand-ins. Its older
2×2 stress test and the BFM-only `supernoc_tb` remain independent scopes.
AXI4-Lite control endpoints need real upstream AXI-Lite/AXI4 adapters.
All eight local/global FlooGen outputs are generated and reviewable in
`gen/noc/floonoc/`. One [whole-chip picture](gen/diagrams/noc-hierarchy.svg)
and its router/NI JSON cover the hierarchy; there are no separate mesh images.
The connected BFM regression is distinct from real endpoint integration.

## Explicit interface sizing

[AXI interface budgets](config/interface_contracts.yaml) and the
[contract checker](tools/interface_contracts.py) now validate named local
and global subsystem fabric ports, 64-bit AXI4 data/address, configured
local AXI ID widths (4-bit input, 5-bit output), independent pending
read/write targets, and native IP parameter names. This is a validated
**design contract**. Native chimney parameters are bound in generated RTL,
and directed traffic passes; maximum capacity and every parameter combination
remain unverified. CI keeps FlooGen AXI widths and memory windows in sync.

## Subsystem-level tests and FlooNoC bring-up

Use [subsystem verification plan](docs/subsystem-verification.md) as the
authoritative scope definition (compute0, compute1, memory0, global data,
global config, full SoC). [All eight generated FlooNoC topologies](gen/noc/floonoc/manifest.json)
are committed actual upstream-generated SystemVerilog, with the connected NoC BFM regression described in
[super-NoC verification](docs/supernoc-verification.md).
No bridge- or simulator-repro TB proliferation.

## Build and regression

[`Bender.yml`](Bender.yml) defines standard ordered source sets;
[`config/regression.yaml`](config/regression.yaml) defines tests, variants
and suites shared by Make and CI. `make test-list` lists the catalog;
`make test` runs every declared simulation and compatibility probe using
both toolchains. [Setup, filelists, build/run stages and results](docs/regression.md)
replace the old per-test shell runners. Cold boot includes a relocated-map
regression driven by the generated boot configuration package.

The NoC and chip cocotb runs also produce a [per-test AXI run report](docs/axi-run-reports.md):
an offline HTML page with a filterable transaction table and completion
timeline, plus raw events/transaction JSON. Dedicated CI artifacts retain
the pages for positive and negative runs. The Pages hub collects their full CI
evidence after main workflows finish. New reports label real CPU/BFM/idle actors,
show phase markers, and distinguish explicitly expected SLVERR requests from
undeclared initiator errors. Normal CPU boot does not expect SLVERR; error-path
tests deliberately inject target faults or exceed the 64-KiB memory models.

## Reproducible generation

Everything under **[`gen/`](gen/)** is committed to Git for version-to-version diffs. The directory is exclusively generator-owned and contains a marker protecting against accidental replacement of user-owned trees.

```bash
python3 -m pip install -r requirements.txt
python3 tools/ip_fetch.py floonoc
python3 -m pip install -e .tools/floonoc
make gen                 # regenerate code, metadata, diagrams, README
make check-generated     # non-mutating drift and stale-file check
make check-config        # generator/config test suite
```

`make gen` builds all outputs in a staging directory before replacing the complete `gen/` tree. **Obsolete generated files are removed** when a block, network, subsystem, or diagram disappears from YAML. No file outside `gen/` is deleted; only the explicitly marked README section is rewritten. `make check-generated` compares both file *names* and bytes, so CI catches missing, modified, and stale files without committing or modifying anything. Generation does not depend on a GPU, web service, 3D viewer, or Graphviz: the README embeds static **2D architecture SVG**, with Mermaid source alongside for editing and review.

The generated artifacts include:

| Output | Purpose |
| --- | --- |
| [`gen/memory/memory_tb.sv`](gen/memory/memory_tb.sv) | Real synthesizable crossbar instantiated in a generated AXI memory testbench |
| [`gen/memory/manifest.json`](gen/memory/manifest.json) | Bus parameters, instance metadata, memory models, tests |
| [`gen/noc/fabric_ir.json`](gen/noc/fabric_ir.json) | Vendor-neutral NoC/interconnect intermediate representation |
| [`gen/verification/plan.json`](gen/verification/plan.json) | Verification scopes, executable vs planned boundaries, test commands |
| [`gen/verification/routes.json`](gen/verification/routes.json) | Source/target AXI reachability expectations for the executable memory test |
| [`gen/diagrams/`](gen/diagrams/) | One SVG, its Mermaid source and structured router/NI graph (`noc-topology.json`) |
| [`gen/manifest.json`](gen/manifest.json) | Deterministic SHA-256 index of every generated output |

The static SVG previews display directly in GitHub README and mobile clients, even when Mermaid rendering is unavailable. Each has a full-resolution link; the `.mmd` sources and structured graph metadata remain committed for diffs.

The 2D visualizations follow the instance/connection metadata ideas in [Sv-diagrams](https://github.com/r987r/Sv-diagrams) and [Diagram-gen](https://github.com/r987r/Diagram-gen); verification scope metadata follows the YAML testbench pattern in [Sv-test](https://github.com/r987r/Sv-test). There is **no 3D dependency** and no duplication of architecture definitions in the diagram sources.

## Running the verification checks

The regression reuses the pinned Xezim executable; it does **not** rebuild Rust or Xezim for source or configuration changes. Third-party RTL is fetched at locked commits on first use.

```bash
make gen
XEZIM_BIN=/path/to/xezim make dv-memory
XEZIM_BIN=/path/to/xezim make dv-memory-negative
XEZIM_BIN=/path/to/xezim make dv-cpu     # request-only diagnostic
XEZIM_BIN=/path/to/xezim make dv-serv    # four-word SERV image; checked signature store
XEZIM_BIN=/path/to/xezim make dv-sram    # real RTL SRAM, no power-on preload
XEZIM_BIN=/path/to/xezim make dv-boot    # real ROM->SRAM CPU execution
XEZIM_BIN=/path/to/xezim make test
make dv-supernoc                    # independent NoC BFM regression
make dv-chip                        # real CPU boot/coordination + AXI memory stand-ins
```

The memory regression instantiates the publicly available Verilog-AXI crossbar and behavioral AXI RAM. It issues four-beat reads and writes from two independent AXI masters to HBM0 and DDR0 address regions, then checks responses, IDs, data, and reachability. The negative test intentionally corrupts an expectation and confirms the checker rejects it. The CPU smoke merely observes fetch requests; **`dv-boot` executes instructions** from ROM and then from SRAM, proving actual CPU-controlled SRAM loading.

**Boot status:** The standalone boot test instantiates both real CPUs. CPU0 must copy two flash-resident programs into initially blank SRAM, release SERV through MMIO and execute SRAM code. [Boot flow and memory map](docs/boot.md) details what is and is not integrated.

**Not yet implemented:** real PULP iDMA integration, DMA CSRs and interrupts, generic PULP AXI backend emission, and physical HBM/DDR controller/PHY integration. Selected controller projects are research/integration candidates; the simulated `axi_ram` targets are **not timing-accurate HBM or DDR controllers**. The HBM candidate currently relies on vendor HBM PHY IP.

## IP replacement and implementation boundaries

- The **architecture** is specified by [`config/soc.yaml`](config/soc.yaml), including per-subsystem CPU differences and separate data/config networks.
- [`tools/socgen.py`](tools/socgen.py) emits the executable memory RTL and neutral NoC IR; [`tools/noc_backends.py`](tools/noc_backends.py) defines vendor-specific emitters. The **`verilog_axi` memory backend is executable**; PULP AXI emission remains pending. [`tools/floonoc_gen.py`](tools/floonoc_gen.py) emits all eight real FlooGen networks, and [`tools/supernoc_gen.py`](tools/supernoc_gen.py) connects their AXI4 boundaries in one BFM testbench. `tools/full_chip_gen.py` emits the CPU boot configuration using the shared core. The generic full-SoC backend remains non-executable while general iDMA/controller integration is pending.
- [`tools/noc_diagrams.py`](tools/noc_diagrams.py) builds and renders the single architecture view from the actual FlooGen profiles; [`tools/generate.py`](tools/generate.py) coordinates generation, stale cleanup, and drift verification.
- [`config/ip.lock.yaml`](config/ip.lock.yaml) pins third-party IP commits. [`rtl/adapters/`](rtl/adapters/) isolates the CPU and behavioral memory interfaces.

See [architecture contracts](docs/architecture.md) and the [hierarchical verification plan](docs/verification.md) for intended subsystem, NoC, and full-chip integration milestones.

## Development and CI

GitHub Actions first validates the configuration, then checks the committed `gen/` tree and embedded README diagrams for drift, and only then runs the RTL regressions. A change to a configuration or generator must be followed by `make gen` in the same commit. An intentionally removed subsystem must result in a **Git deletion** of its obsolete generated files; it must never leave misleading diagrams behind.

The simulator publishing workflow is independent of the SoC verification workflow, so an RTL-only change never initiates a Rust build.
