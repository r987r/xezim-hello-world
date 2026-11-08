# Integrated local/global FlooNoC verification

`gen/supernoc/supernoc_tb.sv` is the **single** generated connected NoC verification wrapper; do not add per-router or per-bridge copies. It instantiates the selected upstream FlooGen networks from the generated manifest (currently twelve local/global Data/Config meshes), legal endpoint maps and shared AXI types. This is structural RTL, not real CPU, real DDR PHY, or PCIe/Ethernet packet-engine integration.

## Test hardware and agents

- `tools/supernoc_gen.py` generates the source-derived wrapper and flattens AXI packed ports for Cocotb. It does **not** implement an AXI BFM or custom router.
- Upstream [cocotbext-axi](https://github.com/alexforencich/cocotbext-axi) supplies AXI masters/slaves, sparse memory regions, bursts and stalls. Every memory responder exposes only its decoded backed window; no wrapping into modeled RAM.
- The `supernoc` target is Verilator/Cocotb with upstream FlooNoC/PULP AXI pins from Bender. Xezim independently compiles selected structural NoCs and runs CPU/boot/memory scopes; Xezim compilation is **not** connected NoC traffic.
- The existing passive AXI monitor catalog covers every distinct inter-mesh AXI link and target once. Capture starts before clock, retains incomplete transactions and distinguishes original IDs from remapped downstream IDs.

```sh
make check-generated
make dv-supernoc
python3 tools/regress.py supernoc-negative
python3 tools/regress.py supernoc --stage run  # only for a source-fingerprint-verified build
```

The negative test requires its **specific named corruption detection**, not an ordinary simulator exit code. Real hardware results require accepted AW/W/B and AR/RLAST readback at the intended source/target, destination decoding, data/strobes, ordering, stalls, and explicit SLVERR on invalid routes. Actor-issued stimulus is not observed acceptance; a generated route is not a measured latency.

## AXI ID, atomic and ordering contract

For non-ATOP SoC traffic the configured NI must set native `AtopSupport=0` and `MaxAtomicTxns=0`; reserving an unused atomic slot can violate upstream `TooFewIdBits` assertions on narrow Config NIs. Do not silence native assertions or reduce supported IDs to one to make a test boot. Any future ATOP support needs actual ID-budget, source-parameter and atomic data/ordering qualification.

Target-only chimney NIs require B/R `NoRoB` when the pinned upstream manager-port configuration is disabled; manager NIs retain their configured RoB contract. For same AXI ID, local **and** global source NIs must retain destination ownership/ordering across B and R when consecutive requests target different subordinates. Cross-ID traffic may proceed independently and downstream numeric AXI IDs may be rewritten; they are not universal transaction identities.

Maintain positive and negative same-ID tests across local SRAM, remote SRAM, memory and multiple outstanding paths, including deliberate stall/reordering and error responses. Keep upstream FlooNoC source unchanged; generate native legal parameters from [interface budgets](../config/interface_contracts.yaml). Broader saturation and physical/clock-domain performance require separate qualification.

## Coverage and boundaries

The connected NoC test uses **modeled memory targets** and BFM managers. It cannot prove that opt-in CPU/iDMA/PCIe/Ethernet/real DDR is attached in the same chip build. Compare the exact generated `gen/supernoc/manifest.json`, source graph, routes, monitor catalog, selected filelist and tested commit before interpreting a report. Measured clock, route-stage latency and original transaction samples are reported by [Fabric Explorer](publication.md); unavailable stages are unmeasured.

Open feature and test work is tracked in [#34](https://github.com/r987r/xezim-hello-world/issues/34) and [#46](https://github.com/r987r/xezim-hello-world/issues/46), not in PR-by-PR progress sections in this guide.
