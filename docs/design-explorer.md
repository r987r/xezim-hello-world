# 2D design and verification explorer

The interactive 2D viewer is a single view over existing generated topology.
GitHub Pages builds the JSON and page alongside the canonical architecture
diagram. It supports whole-chip overview, per-group drilldown and testbench
actor overlays. It contains no 3D view.

## Evidence levels

| Source | Role | Limit |
| --- | --- | --- |
| SoC YAML and FlooGen manifests | Intended architecture and endpoint contracts | Declarative |
| Generated NoC topology JSON | Routers, boundary nodes, links and groups | Generator-owned, includes planned integration |
| Regression YAML | Top modules, selected profiles, test modules and AXI report configuration | Test registration, not test execution |
| Generated actor/monitor JSON | Real RTL, BFM, SRAM model and CSR roles per profile | Declared scope, not runtime proof |
| slang-hier probe | Exact elaborated hierarchy for a resolved filelist | Only authoritative after a successful run |
| slang-netlist | Bit-level driver and path tracing | Planned next integration; not yet executed against SoC |
| hdl-kgraph | UVM class inheritance, role classification, cocotb direct DUT access | Static inference, not dynamically constructed TB topology |

The diagram must never present generated/declared connectivity as verified
slang/netlist connectivity. AXI monitor captures and actual simulations remain
authoritative for functional behavior. Structural elaboration alone cannot
prove that a read or write reaches the right destination.

## Generate and compare a graph

~~~sh
python3 tools/design_explorer.py --output .tools/design-graph.json
python3 tools/design_explorer.py --diff old-design-graph.json --output .tools/design-graph-diff.json
python3 -m unittest tests.test_design_explorer -v
~~~

New modules and connections in the generated topology are discovered
automatically, including unknown subsystem names. Link IDs are stable across
reordering. Unknown endpoints, actor references and duplicate links are
reported as errors instead of silently ignored.

## Optional verification parser: hdl-kgraph

The MIT-licensed hdl-kgraph project extracts SystemVerilog class hierarchy,
UVM roles, constraints, covergroups, assertions, and some cocotb test-to-DUT
relationships. This is substantially more useful than porting the older
Sv-test static parser. Direct signal accesses in cocotb are inferred, and
dynamic constructs may be missed: preserve those confidence limitations.

~~~sh
hdl-kgraph build -f .tools/regression/chip-dma/sources.f
hdl-kgraph query uvm --json > .tools/uvm-static.json
python3 tools/design_explorer.py \
  --verification-report chip-dma=.tools/uvm-static.json \
  --output .tools/design-graph-with-uvm.json
~~~

Importing a JSON parser result explicitly marks it as static inference, not
runtime topology. These commands are a documented optional integration; the
external package is not pinned or installed automatically by this PR.

For runtime UVM topology use the upstream UVM end-of-elaboration component
tree report (uvm_top.print_topology) or an equivalent JSON export. Factory
overrides and config-db-driven instantiation are runtime behavior. For cocotb
use the actual BFM/monitor binding catalog captured during each test.

## slang-hier real-source elaboration probe

The wrapper uses source ordering, includes and defines emitted by the existing
Bender regression resolver. It fails closed when the binary is missing,
the compilation fails, or no hierarchy is emitted.

~~~sh
python3 tools/regress.py supernoc --stage files
python3 tools/design_elaborate.py --profile supernoc --output .tools/supernoc-hierarchy.json

python3 tools/regress.py chip-boot --stage files
python3 tools/design_elaborate.py --profile chip-boot --output .tools/chip-boot-hierarchy.json

python3 tools/regress.py chip-dma --stage files
python3 tools/design_elaborate.py --profile chip-dma --output .tools/chip-dma-hierarchy.json
~~~

These profiles intentionally differ: supernoc BFMs substitute functional
masters; chip boot has real CPUs and disabled DMAs; chip DMA has active PULP
iDMA engines and host BFMs at CPU0 boundaries. The same configured block
should not be misrepresented as having identical actors in every test.

This PR does not yet pin/build slang or slang-netlist, or certify the full
generated RTL through them. Those integration checks belong in a dedicated
toolchain validation step with reproducible version pins.

## Genericity and future subsystems

The explorer does not know about compute, memory, Ethernet, PCIe or DDR
module types. It requires generated structural nodes, endpoint edges and
registered test profiles. Adding a new subsystem type to the **current SoC
generator** is separate work: present RTL emitters and validation logic
still assume compute/memory templates and a single memory subsystem.
Only after those are generalized can a new subsystem truly be created from
config alone.

The current viewer uses deterministic grid-based 2D layout. Port-aware ELK
layout and bit-level, protocol-aware drilldown are follow-on work when real
slang-netlist integration is validated. Do not create duplicate whole-chip
architecture drawings or any 3D diagram infrastructure.

## Follow-on work

1. Pin and exercise compatible slang, slang-netlist and hdl-kgraph versions
   on resolved supernoc, chip-boot and chip-dma filelists.
2. Add elaborated module-port and netlist dependencies as separately labeled
   graph evidence, with strict failure rules and source locations.
3. Replace simple grid layout with port-aware ELK routing and AXI channel
   expansion; render graph diffs directly in Pages.
4. Add actual runtime verification topology export for future UVM tests
   and cocotb BFM registration checks for current test suites.
