# Signal explorer and protocol grouping

The SoC's existing [2D explorer](../tools/templates/site_explorer.html)
can now expand *actual generated SystemVerilog port declarations* into
signal-level lists, with names, widths, directions, source line links,
and protocol channel groups. No extra architecture diagram is created.

## Reuse existing interface metadata, do not guess wiring

The best model for logical bus grouping is the IP-XACT approach: a logical
bus interface maps to physical RTL ports. Our initial implementation
reads real flattened RTL signals and infers **display grouping only**.
It does not invent links from matching signal names.

Inputs:
- `gen/supernoc/soc_noc.sv` — real ANSI port declarations for the
  generated SoC NoC boundary. No IP-specific name list is maintained.
- `gen/diagrams/noc-topology.json` — existing generator-declared
  instance and connection records (includes planned wires).
- `slang-report --ports --format json` — optional alternative source for
  real elaborated ports, allowing arbitrary hierarchy and IP naming.
- `slang-netlist --save-netlist` — optional actual static data-dependency
  graph for on-demand source-to-sink port tracing.

Protocol categories: AXI4's AW/W/B/AR/R, AXI stream, DFI read/write/
training/command, PCIe PIPE and TLP request/completion, Ethernet PHY
interfaces, clocks, resets, generic request/response and ready/valid
handshakes, plus unclassified discrete ports. New protocols can extend
the classifier without modifying the renderer. Unknown names remain
visible as discrete signals, **not** discarded.

The grouping is deliberately conservative: a port named `txdata`
without surrounding evidence is not automatically called PCIe or Ethernet.
The current generator has AXI4 transport for config NoCs as well as data
NoCs; logical AXI4-Lite adapters need their actual RTL, rather than
their protocol being guessed from an AXI signal name.

## Reproduce and inspect generated physical ports

~~~sh
python3 tools/signal_inventory.py --output .tools/signal-inventory.json
python3 -m unittest tests.test_signal_inventory tests.test_signal_paths -v
~~~

The explorer embeds the inventory into a self-contained HTML document
for mobile/offline viewing, provides endpoint and bus/channel filters,
and links back to the source location of each declared signal.
The view is regenerated from checked-in RTL and needs no manually edited
per-subsystem signal list.

**Evidence labels are important:**
1. `generated_rtl_port_declaration`: a physical RTL signal exists,
   with its width and direction.
2. `name_inference`: AXI/DFI/PCIe/etc. classification of that signal,
   not a proven connection.
3. `generator_declared_not_slang_traced`: an intended or generated
   edge in architecture metadata, not a validated bit-level path.
4. `elaborated_static_data_dependency`: actual path through
   `slang-netlist`'s serialized graph. This still does not prove
   AXI transaction routing or temporal correctness.

## Validate physical connectivity through slang-netlist

After building a compatible source-pinned slang-netlist CLI and
resolving a test profile filelist, export the real netlist:

~~~sh
python3 tools/regress.py chip-dma --stage files
python3 tools/design_netlist.py --profile chip-dma --mode netlist \
  --output .tools/chip-dma-netlist.json

# Discover full elaborated hierarchical signal/port names:
python3 tools/signal_paths.py .tools/chip-dma-netlist.json \
  --list-ports --prefix full_chip_dma_tb

# A requested path must actually exist in the saved dependency graph:
python3 tools/signal_paths.py .tools/chip-dma-netlist.json \
  --from-port <full_source_port_path> \
  --to-port <full_target_port_path>
~~~

The last command returns exact intermediate nodes and bit ranges and
source locations where the upstream graph records them. A missing
path *under the selected depth and visit bound* is inconclusive,
not automatically an electrically disconnected wire.

The source build of slang-netlist and its exact version compatibility
with slang v12.1 are **not yet validated** in this stacked PR. That
compatibility gate belongs to the next implementation stream; it must
not be represented as a completed whole-SoC signal audit.

## Future protocol integration

Use optional IP-XACT (IEEE 1685-2022) bus/abstraction definitions
when an IP already provides authoritative port maps. Kactus2 and
pyEDAA.IPXACT are established tools for reading or editing this type
of metadata; we should not implement our own IP-XACT XML parser.
Fallback to RTL/name grouping only when a bus definition is absent.
For compound SV structs, do not blindly invent AW/W fields from a
single `axi_req` port; show the struct as is until a real parser
provides elaborated member-level information.

This stream is stacked on PR #28's generic 2D explorer and is separate
from the independent slang lint/cleanup stream in PR #30.
