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
   (connected NoC RTL has a separate routed-traffic regression).
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
  `axi_xbar` remains optional; FlooGen emits the twelve configured local/global networks; discover new meshes from the generated manifest, not a fixed count.
- Bridge shims: only minimal protocol/width/reset adapters needed at the
  boundary; never custom arbitration or routing RTL unless no reusable
  implementation meets an explicitly documented requirement.

The reference example is **not** a new default and cannot be treated as
proof of a full SoC or NoC integration. Run CI and inspect upstream RTL
simulation before merging.

## Exact-case cross-scope latency comparison (#155)

The existing fabric collector keeps the original source-selected
benchmark plan, independently validated accepted AXI cases and reference
clock alongside measured stages. It exposes `latency_scope_comparisons` only
when both scopes have complete original case IDs, matching source actor,
operation, address, simulator, benchmark phase, counts and measured clock.
A missing, historical or incompatible scope remains `unmeasured` or
`incompatible`, never an estimated speedup.

End-to-end comparisons are valid across *different* mesh inventories when
the executed benchmark cases genuinely match. Per-stage deltas compare only
the same physical passive AXI boundary (including monitor identities);
scope-only stages are explicitly left unmeasured, not assigned fake
latencies. Source-equivalence is still independently attested against the
site commit by the trusted collection path.

This **does not yet close #155**: the isolated local-subsystem FlooNoC RTL
benchmark and its independent passive AXI/DMA target test are still missing.
No local results are synthesized from full-chip or SuperNoC timings. Once
a local top and matching exact-head test are qualified, this schema will
publish a defensible comparison using the existing Explorer and original
run links, not a second visualization.
