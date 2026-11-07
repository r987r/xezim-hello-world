# Config-driven SoC RTL and verification

[![SoC regression](https://github.com/r987r/xezim-hello-world/actions/workflows/dv-soc.yml/badge.svg)](https://github.com/r987r/xezim-hello-world/actions/workflows/dv-soc.yml)

A hierarchical SoC verification vehicle using pinned open-source CPUs, PULP iDMA, FlooNoC, PCIe and Ethernet IP. The architecture and addresses come from [`config/soc.yaml`](config/soc.yaml); [`config/regression.yaml`](config/regression.yaml) selects executable tests; [interface contracts](config/interface_contracts.yaml) and [IP locks](config/ip.lock.yaml) define integration boundaries. Tracked `gen/` outputs are generated, **not** hand-maintained.

## Start here

```sh
python3 -m pip install -r requirements.txt
python3 tools/ip_fetch.py floonoc
python3 -m pip install -e .tools/floonoc
make gen
make check-generated
make check-config
make test-list
```

Run a focused regression before the expensive full suite:

```sh
make dv-boot             # actual CPU cold boot
make dv-supernoc         # Verilator local/global AXI routing
make dv-chip-cpu-dma     # real CPU0 C, PULP iDMA; modeled DDR/HBM
make dv-chip-ddr4-real   # opt-in real LiteDRAM RTL, behavioral DFI/PHY
```

See [setup and regression options](docs/regression.md), [simulator limits](docs/simulator-compatibility.md), and [agent instructions](AGENTS.md). Avoid running the full suite just to inspect a test.

## Hardware versus models

| Scope | What the selected test exercises | Boundary |
| --- | --- | --- |
| Boot | PicoRV32 and SERV, ROM/flash-to-SRAM cold boot, reset MMIO | No writable SRAM preload in cold-boot tests |
| NoC/iDMA | Twelve generated FlooNoC meshes, real PULP iDMA RTL and AXI/CSR paths | BFM-driven tests are not CPU firmware; route checks are not all-path bit proof |
| Ethernet | Opt-in real GMII MAC, RX/TX queues, descriptor DMA, SRAM/CQ and CPU0 C tests | Default generated packet/management ports remain reserved |
| PCIe | Opt-in real TLP-to-AXI bridge, modeled host RC and host BAR readback | No physical PCIe PHY or autonomous endpoint DMA to host RAM |
| DDR | Opt-in pinned LiteDRAM RTL and AXI/DFI command evidence | Model SDRAM PHY/banks, not silicon DDR4 PHY; default DDR is AXI RAM |
| HBM | Configured aperture and bounded AXI RAM stand-in | No integrated real HBM controller/PHY |

**A passing isolated test is not proof of the combined Ethernet → real DDR → CPU/iDMA → PCIe path.** See the [combined acceptance contract](docs/multiprotocol-integration-readiness.md) and [open epic #34](https://github.com/r987r/xezim-hello-world/issues/34). Physical link, stress, IRQ and fast-route work remain separately tracked.

**DMA mode:** `DmaEnable=1` instantiates actual PULP iDMA engines and Config-NoC CSRs; `make dv-chip-dma` tests CPU-reset BFM-controlled RTL transfers separately from real CPU0 C. CPU interrupt service is not implemented; polling-based C DMA is supported.

**Inspect each test's stimulus:** [authored YAML](config/stimulus/tests.yaml), [selection and execution mapping](config/stimulus/README.md), and [the regression build specs](config/regression.yaml). Use `python3 tools/stimulus_catalog.py --list` or `--show chip-ethernet-cpu`. These descriptions do **not** imply every C/Python/SV driver has migrated to source-selected typed dispatch.

## Architecture and generated sources

<!-- BEGIN GENERATED SOC -->

<!-- Do not edit this section: regenerate with `make gen`. -->
### Whole-SoC data and configuration NoCs

The diagram is generated from the configured FlooGen networks and SoC endpoints. Solid links show source-declared connections; dashed links indicate reserved/optional attachments. It is a structural view, **not** proof of elaborated ports or observed traffic.

[![Complete hierarchical SoC and all data/config FlooNoCs](gen/diagrams/noc-hierarchy.svg)](gen/diagrams/noc-hierarchy.svg)

[Full-size diagram](gen/diagrams/noc-hierarchy.svg) · [Editable Mermaid](gen/diagrams/noc-hierarchy.mmd) · [Machine-readable router/NI/link graph](gen/diagrams/noc-topology.json) · [Real generated FlooNoC RTL](gen/noc/floonoc/manifest.json)

**Configured topology:** 2 compute subsystems, 12 independent FlooNoC instances, 68 total generated routers. Data: 64-bit AXI4; control: 32-bit AXI4 transport for AXI4-Lite endpoint bridges. CPU/reset adapters are attached in the boot configuration; the BFM scope uses AXI agents.

**Verification boundary:** Verilator runs connected local/global NoC RTL traffic and negative-route tests; Xezim runs independent CPU boot, SRAM and AXI memory tests and has structural NoC compilation checks. A compile is not routed-traffic coverage. CPU/iDMA, Ethernet, PCIe and real LiteDRAM require their separately selected opt-in regressions; no single default generated chip proves their combined behavior. See [verification scopes](docs/verification.md).

### Generated NoC sources (no duplicate pictures)

| Network | Routers | Generated top | Config |
| --- | ---: | --- | --- |
| `compute0_local_config` | 6 | [SystemVerilog](gen/noc/floonoc/compute0/local_config/floo_xezim_compute0_local_config_noc.sv) | [FlooGen YAML](gen/noc/floonoc/compute0/local_config/floogen.yaml) |
| `compute0_local_data` | 9 | [SystemVerilog](gen/noc/floonoc/compute0/local_data/floo_xezim_compute0_local_data_noc.sv) | [FlooGen YAML](gen/noc/floonoc/compute0/local_data/floogen.yaml) |
| `compute1_local_config` | 4 | [SystemVerilog](gen/noc/floonoc/compute1/local_config/floo_xezim_compute1_local_config_noc.sv) | [FlooGen YAML](gen/noc/floonoc/compute1/local_config/floogen.yaml) |
| `compute1_local_data` | 6 | [SystemVerilog](gen/noc/floonoc/compute1/local_data/floo_xezim_compute1_local_data_noc.sv) | [FlooGen YAML](gen/noc/floonoc/compute1/local_data/floogen.yaml) |
| `ethernet0_local_config` | 4 | [SystemVerilog](gen/noc/floonoc/ethernet0/local_config/floo_xezim_ethernet0_local_config_noc.sv) | [FlooGen YAML](gen/noc/floonoc/ethernet0/local_config/floogen.yaml) |
| `ethernet0_local_data` | 4 | [SystemVerilog](gen/noc/floonoc/ethernet0/local_data/floo_xezim_ethernet0_local_data_noc.sv) | [FlooGen YAML](gen/noc/floonoc/ethernet0/local_data/floogen.yaml) |
| `global_config` | 9 | [SystemVerilog](gen/noc/floonoc/global_config/floo_xezim_global_config_noc.sv) | [FlooGen YAML](gen/noc/floonoc/global_config/floogen.yaml) |
| `global_data` | 12 | [SystemVerilog](gen/noc/floonoc/global_data/floo_xezim_global_data_noc.sv) | [FlooGen YAML](gen/noc/floonoc/global_data/floogen.yaml) |
| `memory0_local_config` | 2 | [SystemVerilog](gen/noc/floonoc/memory0/local_config/floo_xezim_memory0_local_config_noc.sv) | [FlooGen YAML](gen/noc/floonoc/memory0/local_config/floogen.yaml) |
| `memory0_local_data` | 4 | [SystemVerilog](gen/noc/floonoc/memory0/local_data/floo_xezim_memory0_local_data_noc.sv) | [FlooGen YAML](gen/noc/floonoc/memory0/local_data/floogen.yaml) |
| `pcie0_local_config` | 4 | [SystemVerilog](gen/noc/floonoc/pcie0/local_config/floo_xezim_pcie0_local_config_noc.sv) | [FlooGen YAML](gen/noc/floonoc/pcie0/local_config/floogen.yaml) |
| `pcie0_local_data` | 4 | [SystemVerilog](gen/noc/floonoc/pcie0/local_data/floo_xezim_pcie0_local_data_noc.sv) | [FlooGen YAML](gen/noc/floonoc/pcie0/local_data/floogen.yaml) |

**Validation and generated metadata:** [NoC interface budgets](config/interface_contracts.yaml) · [routing IR](gen/noc/fabric_ir.json) · [memory testbench](gen/memory/memory_tb.sv) · [verification plan](gen/verification/plan.json) · [generated tree manifest](gen/manifest.json).

<!-- END GENERATED SOC -->

## Test selection, evidence and ownership

- [Regression catalog](config/regression.yaml) defines simulator, source, firmware, and test selection; [scenario source](config/scenarios/cpu-bfm-ddr-roundtrip.json) describes existing executable CPU/BFM DMA actions. A planned action does not itself establish a DUT handshake or PASS.
- The [Test Runs and Fabric Explorer](https://r987r.github.io/xezim-hello-world/) show separately labeled source-declared routes, simulator evidence, actual accepted AXI/TLP/GMII/DFI observations and unavailable measurements. Use [publication rules](docs/publication.md) to interpret source compatibility and history.
- New published run identity uses `simulator/config_target/testname/run_id`. [Naming and retention](docs/test-identity.md) distinguish new reports from old comparison archives; [#139](https://github.com/r987r/xezim-hello-world/issues/139) tracks remaining internal legacy output paths.
- [Full-chip boot](docs/full-chip-boot.md), [DMA](docs/dma-bringup.md), [Ethernet](docs/ethernet0-closure-gate.md), [PCIe](docs/pcie0-host-phases.md), [DDR](rtl/memory/ddr4/README.md) and [IP portability](docs/ip-portability.md) contain stable technical contracts. [Documentation index](docs/README.md) groups the rest.

## Development rules

```sh
make gen                 # replace generator-owned gen/ and README section
make check-generated     # non-mutating byte/file-drift check
python3 tools/regress.py <target> --stage files
python3 tools/regress.py <target>
```

Never edit `gen/` or the generated section below by hand. Generated topology is not an elaborated circuit; report current-source results only from the matching tested commit. Keep changing PR/CI status, remaining work and decision history in [GitHub issues](https://github.com/r987r/xezim-hello-world/issues), not dated README paragraphs.
