# Subsystem-level verification only

The only new high-level RTL scopes should be **compute0**, **compute1**,
**memory0**, **global_data NoC**, **global_config NoC**, and **full SoC**.
Reuse upstream modules within each TB; no separate testbench for every
bridge, FIFO, decoder, SRAM, router, or BFM.

## Priority: real FlooNoC, not mock NoC

The baseline Xezim `global_data` network is named `floonoc` in
`config/soc.yaml`, but **is not instantiated**. `verilog_axi` is the
only currently tested interconnect, inside memory0's scoped TB.

For the first actual FlooNoC bring-up, a pinned upstream FlooGen config
lives at [`config/floogen/global_data.yml`](../config/floogen/global_data.yml).
It selects XY routing, a 2x2 mesh and four AXI4 endpoints. Each compute
subsystem supplies one AXI4 initiator. The memory subsystem has **two
separate incoming NoC AXI4 ports** (not physical HBM/DDR controllers).

Do not mark the backend executable or diagram links solid until:
- `floogen rtl -c config/floogen/global_data.yml -o <temporary directory>`
  executes with the pinned FlooGen checkout;
- the generated upstream `floo_xezim_global_data_noc_pkg.sv` and
  `floo_xezim_global_data_noc.sv`, plus their **actual** FlooNoC,
  PULP AXI and common-cells dependencies, elaborate in a supported simulator;
- source and sink AXI4 requests really traverse multiple routers and
  return responses, with checked data, ID, arbitration and backpressure;
- upstream's address decoder maps all declared AXI output windows and
  no fake/custom router or crossbar has been substituted;
- `make check-generated` passes and diagrams distinguish planned from
  tested paths.

**Important:** Upstream FlooNoC documents Questa/VCS as its supported
simulators; Xezim compatibility is not established. The repo's existing
Xezim 0.11.4 binary should be tried with an isolated generated top,
but a failure is not proof the upstream IP is broken. Use the upstream
Bender dependency graph and its pinned source versions, not ad-hoc
handcrafted code. An alternate simulation runner is acceptable for this
scope; it must be labeled honestly and never replace the working Xezim
boot and memory regression.

Command sequence for a suitable build environment:

```bash
python3 tools/ip_fetch.py floonoc
python3 -m pip install -e .tools/floonoc
floogen rtl -c config/floogen/global_data.yml -o .tools/floogen-out --no-format
# Check actual outputs; pin/fetch Bender dependencies before elaboration.
# bender checkout && bender script ... uses the upstream Bender.yml.
make test
```

`config/floogen/global_data.yml` is **an initial generator input**,
not a proven functional NoC. If the vendor parser rejects the endpoint
mapping/width parameters, fix the schema against upstream FlooGen tests;
do not silently switch to a hand-built router. The generic NoC intermediate
representation and `config/soc.yaml` must later be the sole authoritative
source rather than separately maintained copies.

## Testbench scope definitions

| Scope | Desired substantive end-to-end behavior |
|---|---|
| `memory0_tb` | Both AXI ingress ports, real Verilog-AXI crossbar, separate HBM/DDR behavioral target windows |
| `compute0_tb` | Real PicoRV32 boots and drives local PULP AXI, local SRAM and PULP iDMA CSR/traffic |
| `compute1_tb` | Real SERV runs firmware, through its upstream protocol adapter, local PULP AXI, SRAM and iDMA |
| `global_data_tb` | FlooGen-generated *real* FlooNoC 2x2 routers and AXI interfaces between two initiators and two memory ingress ports |
| `global_config_tb` | Separate global config network with real AXI-Lite request/response destinations |
| `soc_top_tb` | Combine compute0, compute1, memory0, data and config NoCs; CPU-programmed DMA accesses to both memories |

Maintain existing standalone cold-boot and SRAM regressions as **bring-up
safety checks**, but don't add new peripheral-specific testbench proliferation.
Do not revive the Xezim 0.11.3 port-slice repro as a new unit-level hardware
requirement: that simulator bug has already been fixed in 0.11.4.

## Technical caveats

The memory region `0x100000000` (HBM) and `0x140000000` (DDR)
remain globally distinct. The current `memory0` crossbar decodes either
region from either input, while the generated FlooGen example currently
associates a disjoint destination range with each output. A future
implementation must explicitly choose *source-based target selection*
versus *memory-subsystem ingress aggregation*; do not claim both memory
targets can be reached through both global NoC outputs until tested.
The existing 64-bit bus contract also uses **64-bit addresses**, whereas
the new FlooGen input uses **64-bit addresses** matching SoC YAML;
validate the resulting AXI ID-width and upstream endpoint address-routing
contracts before compiling the integrated network.

Other outstanding areas (local PULP AXI, actual iDMA, global config
network, and HBM/DDR controller models) remain unimplemented. Do not
confuse a generated YAML config or static diagram with a running NoC.
