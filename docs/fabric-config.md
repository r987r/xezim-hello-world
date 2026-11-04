# Configuration-driven AXI fabric (native IP, no new crossbar RTL)

The reusable reference profile is `config/examples/memory-fabric-connectivity.yaml`.
Copy its `fabrics.memory_data.parameters` and `connectivity` into
`config/soc.yaml`, then run `make gen && make test` before committing
the regenerated `gen/` tree. Default config remains unchanged so the
existing verified cold-boot and memory outputs are not invalidated.

## What is implemented

- Native upstream `alexforencich/verilog-axi/axi_crossbar` tuning:
  `S_THREADS`, `S_ACCEPT`, `M_ISSUE`, and AXI channel register settings.
  Configure as a scalar, ordered list, or a complete map keyed by port name.
- Read/write reachability keyed by `networks.global_data.outputs[].name`
  and `memory_targets[].name`; translated to `M_CONNECT_READ` and
  `M_CONNECT_WRITE` in the upstream crossbar.
- Corresponding allowed-target masks feed the existing memory BFM and
  passive route monitor; unreachable source/target pairs are not considered
  required DV coverage.
- Unknown knobs, port names, asymmetric routing, and unavailable emitters
  fail during configuration validation rather than being silently ignored.

## Boundaries of this standalone memory configuration

- These memory-fabric knobs apply to the independent 2×2 memory scope.
  The separate [chip boot configuration](full-chip-boot.md) already wires
  real CPUs, NoCs, SRAM, reset and a 1×2 memory crossbar; real DMA and CSRs are generated in optional `DmaEnable=1` mode
   (full-NoC verification pending CI).
  The standalone 2×2 tuning/connectivity overrides are not automatically
  applied to that 1×2 chip crossbar.
- Generic full-SoC PULP AXI/FlooNoC backend emission. Scoped FlooGen
  network emission and the connected `supernoc_tb` do exist; see
  [super-NoC verification](supernoc-verification.md).
- The original custom memory BFM and boot/SRAM models remain in their
  independent scopes. The NoC scope uses upstream cocotbext-axi, and the
  chip uses upstream bridges/SRAM; cold-boot compatibility remains required.
- Independent read-only and write-only permissions in the BFM.
- Per-CPU/DMAs, SRAM latency or data width overrides with real RTL bindings.

## Source-of-truth and long-term design

Use an explicit graph of named **module instances, typed interfaces, and
connections** as a normalized intermediate representation. Resolve parameter
defaults at module type, subsystem type and instance level, with instance
overrides highest precedence. Check port existence, protocol, width/ID
compatibility, direction, address mapping and boot reachability. Feed that same
graph to a backend emitter, DV agent generation, diagrams and documentation.

The existing Sv-test `cfg/rtl_connections`, `cfg/uvc_connections`,
`cfg/<tb>/tb.yml` and providers/knobs patterns are the recommended design
inspiration, not an instruction to duplicate its custom RTL/UVC modules.

Reuse choices and remaining alternatives:
- AXI BFMs: the NoC scope already uses pinned cocotbext-axi under Verilator.
  PULP `axi_test` and UVM VIP remain candidates for other supported flows;
  Xezim NoC traffic compatibility has not been established.
- SRAM: the chip boot scope already uses upstream
  `tech_cells_generic/tc_sram` with `SimInit=none` and registered reads.
  Replacing the legacy boot SRAM separately still requires matching its
  asynchronous Port A read contract.
- Fabric: upstream Verilog-AXI `axi_crossbar` already used; PULP AXI
  `axi_xbar` remains optional; FlooGen already emits all eight local/global networks.
- Bridge shims: only minimal protocol/width/reset adapters needed at the
  boundary; never custom arbitration or routing RTL unless no reusable
  implementation meets an explicitly documented requirement.

The reference example is **not** a new default and cannot be treated as
proof of a full SoC or NoC integration. Run CI and inspect upstream RTL
simulation before merging.
