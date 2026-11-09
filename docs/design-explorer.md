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

## Source-attested selected hardware comparisons

After resolving both real compiler source archives, use the existing
`tools/design_explorer.py --selected-before ... --selected-after ...`
entrypoint; [the selected-build review guide](soc-scalability-review.md)
documents the full source-resolution commands. Its JSON and Markdown now
compare selected compiled tops, Bender filelist SHA, source/variant config SHA,
selected defines/include directories, target RTL, per-network NoC source
filelists, header inventory, firmware collateral, and bounded RTL text
differences. It omits per-run identity/document hashes from architectural
changes. Changed compiler contracts are separately labeled
`compiler_source_selected_not_elaborated`; no port-level/CDC/AXI protocol
success can be inferred from the comparison. Source archives are independently
SHA-verified first, and modified, missing or foreign archives fail closed.
These are comparison artifacts, not a second architecture dashboard.

## Genericity and future subsystems

The explorer does not know about compute, memory, Ethernet, PCIe or DDR
module types. It requires generated structural nodes, endpoint edges and
registered test profiles. Adding a new subsystem type to the **current SoC
generator** is separate work: present RTL emitters and validation logic
still assume compute/memory templates and a single memory subsystem.
Only after those are generalized can a new subsystem truly be created from
config alone.

The viewer now uses **hierarchical architectural 2D layouts**, not a flat
node grid. The entry view composes every generated subsystem group and the
shared global fabric; opening a subsystem presents its IP blocks and local
data/config NoCs; opening a NoC uses the **exact FlooGen router XY coordinates**
and the generator's real router-to-router and NI-to-router edges.

The 2D hierarchy is data-driven: `*_subsystem` groups and `info.plane`
network metadata, not manually listed module IDs. The current scene styles
two standard local NoCs per existing subsystem, and additional submodules
remain accessible through generated JSON; broader arbitrary-layout support
will benefit from a port-aware ELK renderer.

The signal inspector retains physical ports with bit widths, directions and
RTL source links. Test profiles distinguish substituted BFMs from actual RTL
DMA/CPU actors where the registered per-profile manifest provides that role.
It does **not** silently assert that a test profile executed.

The real chip/subsystem/NoC browser smoke tests assert all three hierarchy
levels, the generated 9-router compute0 data mesh and signal inspector;
three PNG screenshots are uploaded as PR artifacts for visual QA.
The viewer remains 2D, without old Sv-test 3D or duplicate diagrams.

Port-aware ELK layout of arbitrary nested compound modules and bit-level
slang-netlist path validation remain follow-on work; the explorer does not
claim those as delivered.

## Remaining verification boundaries

1. Pin and exercise compatible slang, slang-netlist and hdl-kgraph versions
   on resolved supernoc, chip-boot and chip-dma filelists.
2. Add elaborated module-port and netlist dependencies as separately labeled
   graph evidence, with strict failure rules and source locations.
3. Extend port-aware ELK routing to arbitrary dynamically generated
   compound subsystems, then show graph diffs and verified AXI-channel
   driver paths directly in Pages.
4. Add actual runtime verification topology export for future UVM tests
   and cocotb BFM registration checks for current test suites.

## Source-built slang-netlist and slang-report adapters

After building the pinned upstream executables and resolving the normal Bender
sources, use the project wrappers rather than reconstructing the RTL list:

~~~sh
python3 tools/regress.py chip-dma --stage files
python3 tools/design_netlist.py --profile chip-dma --mode ports --output .tools/chip-dma-ports.json
python3 tools/design_netlist.py --profile chip-dma --mode drivers --output .tools/chip-dma-drivers.json
python3 tools/design_netlist.py --profile chip-dma --mode netlist --output .tools/chip-dma-netlist.json
~~~

The wrapper writes JSON and a metadata sidecar recording the profile, source
list fingerprint, tool invocation and evidence provenance. If the executable is
missing, compilation fails or JSON is missing/invalid, there is no successful
output. No metadata sidecar can replace actual compiler success or real RTL traffic verification.

## Compiler-parsed RTL composition

The 2D architecture explorer now additionally consumes a source-hash-bound
`slang --parse-only --cst-json --cst-json-mode simple-tokens` report for
`gen/chip/soc_top.sv` and `gen/supernoc/soc_noc.sv`. It reads actual
SystemVerilog module instantiation syntax and **named port binding expressions**,
and validates that the generated FlooGen NoC modules have real
instantiations. Data and configuration NoCs are separate module instances.

The raw CST is not checked in. The normal GitHub Pages CI downloads the same
SHA-verified slang binary as the existing RTL lint workflow, runs the parser,
checks the source fingerprints, and publishes a compact
`data/rtl-architecture.json`. The expandable **Compiler-parsed RTL hierarchy**
section exposes module names, instance names and port connection expressions.

Architectural subsystem grouping/placement continues to reuse generated SoC
metadata. It is not sufficient proof of a simulated or elaborated design:
syntax-only CST includes inactive generate branches. True active instance
selection, driver tracing, and bit-level cross-hierarchy connection checks
remain follow-up work with the pinned slang elaborator/slang-netlist. The
viewer must never label a CST match as verified path reachability.

You can regenerate independently with:

~~~sh
python3 tools/rtl_instance_parser.py --slang .tools/bin/slang --output .tools/rtl-architecture.json
python3 -m unittest tests.test_rtl_instance_parser -v
~~~
