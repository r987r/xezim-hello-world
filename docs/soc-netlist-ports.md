# Selected full-chip direct port verification foundation (#46)

The repository already has a real slang-netlist AXI checker for the
\`memory_tb\` subsystem, including **original enabled Port edges** and
high-bit, direction, disabled and replica negatives. The new generic SoC
adapter \`tools/soc_netlist_ports.py\` reuses that SAME bit checker with an
explicit, source-selected direct-port contract.

For an **actual selected full-chip** netlist, resolve exact sources with
\`regress.py <profile> --stage files\`, export the **real** slang netlist
with \`tools/design_netlist.py --profile <profile> --mode netlist\`, then
provide a schema-v1 contract containing its exact \`profile\`,
\`compiled_top\`, \`filelist_sha256\` and named \`links\` with distinct
\`source\`/\`destination\` Port paths, width and protocol.

The adapter verifies actual selected netlist output SHA, original compiler
filelist/plan/source hashes, exact top/profile binding, original directed
Port nodes, all expected bit positions and edge enablement. A route label
or a source-parsed instance name cannot satisfy the checker.

**Qualification boundary:** CI tests currently exercise source-attested
synthetic port fixtures plus the existing *real memory* checker. A real
full-chip slang netlist and a contract generated from authoritative SoC IR
still need to be produced and qualified on representative default/combined
variants. Neither a fixture nor a direct Port witness establishes
internal NoC routing, CDC safety, accepted AXI/TLP/GMII traffic, or byte
integrity. Keep #46 open until the actual SoC port contract and original
negative tests pass on the same source-selected RTL/CI head.
