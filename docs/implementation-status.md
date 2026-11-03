# SoC and Xezim implementation status

This is a **scope-aware** inventory, not a declaration that the complete
SoC is integrated. The authoritative config is
[`config/soc.yaml`](../config/soc.yaml), the backend registry is
[`noc_backends.py`](../tools/noc_backends.py), and the generated
verification plan is [`plan.json`](../gen/verification/plan.json).
Check the latest [GitHub Actions runs](https://github.com/r987r/xezim-hello-world/actions/workflows/dv-soc.yml)
for the exact SHA before reporting regression results.

## What runs, versus what is only configured

| Part | Actual executable RTL scope | Limit |
| --- | --- | --- |
| Real `verilog-axi` AXI4 crossbar | `make dv-memory` with two master BFMs, HBM/DDR **behavioral AXI RAM** targets | No CPU/DMA or global NoC in this scope |
| Full/sparse native crossbar settings | `AXI_CONFIG=config/examples/memory-fabric-connectivity.yaml make dv-memory; AXI_CONFIG=config/examples/memory-fabric-sparse.yaml make dv-memory` | Examples are separate opt-in workloads, not the default full-chip topology |
| Negative memory checker | `make dv-memory-negative` | Demonstrates data corruption is caught |
| Local two-port SRAM model | `make dv-sram` | Custom test model, not a silicon SRAM macro |
| Real SERV instruction test | `make dv-serv` | Small standalone core+RAM test |
| Dual-CPU cold boot | `make dv-boot`: real PicoRV32 ROM fetch, flash reads, SRAM writes, SERV MMIO release, two signatures | Standalone bootstrap memory/bus model, not the generated full-chip NoC |
| PULP iDMA | **No executable subsystem** | Source commit only; frontend, CSR and data connections pending |
| Local FlooNoC | **Generated structural Verilog for all local data/config meshes** | Upstream RTL elaborates in Verilator and Xezim; CPU/DMA/CSR endpoint wiring and routed traffic remain pending |
| Global FlooNoC mesh | **Upstream-generated structural Verilog tracked in gen/noc/floonoc/global_data** | Upstream dependencies and all eight meshes compile in Verilator and Xezim; AXI transactions remain pending |
| Global config FlooNoC | **Generated structural AXI4 transport RTL** | Real PULP AXI-Lite boundary adapters and CSR transfers NOT yet connected |
| LiteDRAM / HiSA HBM | **No executable physical controller/PHY path** | Verification models are generic AXI RAM, not DDR/HBM controllers |
| End-to-end SOC `soc_top` | **No executable RTL** | CPU to DMA to NoC to memory not proven |

### Distinct executable regression scopes (no extra diagrams)

The dual-CPU cold-boot test runs PicoRV32 ROM/flash fetch and bus
stores into initially uninitialized SRAM, then MMIO-releases SERV.
Separately, `memory_tb` drives the real Verilog-AXI 2×2 crossbar into
behavioral AXI RAM targets. Neither scope pretends the CPU/DMA/
global-NoC-to-memory path is integrated. The one canonical image below
covers the entire configured hierarchy.

## One generated full-chip SoC/NoC diagram

Exactly **one** architecture diagram is generated and embedded in
[README](../README.md): [whole-SoC FlooNoC network hierarchy](../gen/diagrams/noc-hierarchy.svg).
Its [Mermaid source](../gen/diagrams/noc-hierarchy.mmd) and
[router/endpoint connectivity graph](../gen/diagrams/noc-topology.json)
remain reviewable. The source of physical router/NI placement is each
checked-in `gen/noc/floonoc/*/floogen.yaml`, not duplicate hand-maintained
mesh drawings. `make gen` removes previous redundant images.

CPU and memory test details belong in test logs, generated SystemVerilog,
and the verification plan, **not** additional architecture images.

## What would justify saying "FlooNoC works"?

At minimum: pinned FlooNoC and FlooGen sources, real generated router/
network-interface/link RTL compiled in the pinned Xezim simulator (already achieved); connected
AXI endpoints with address and ID translation; traffic across *multiple
routers* to both memory targets; end-to-end data, ordering and reachability
checks plus negative/error cases and backpressure; and committed
`soc_top` source lists and the single corresponding *executable* full-SoC topology diagram.
None of this is established by just `backend: floonoc` or by the existing
Verilog-AXI crossbar test.

## No regressions hidden by the boot model

The Xezim 0.11.3 part-select workaround is removed. Pinned Xezim 0.11.4,
upstream SERV and the real CPU boot regression must continue\npassing. See [boot-debug](boot-debug.md) for timing and VCD details.
\n## Generated structural NoC RTL\n\nAll eight structural NoC SystemVerilog modules and packages are in [`gen/noc/floonoc`](../gen/noc/floonoc/), indexed by [manifest](../gen/noc/floonoc/manifest.json). These are upstream FlooGen output, **not** vendor RTL copied into the repository. Config FlooNoCs use AXI4 as the wire transport with planned upstream PULP AXI-Lite adapters (see [protocol reuse guide](axi-lite-over-floonoc.md)). The system currently has no integrated NoC traffic test.\n