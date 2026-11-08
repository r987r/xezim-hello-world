# Combined Ethernet → real DDR → CPU/iDMA → PCIe host verification

**Acceptance contract, not a completed test.** Independent Ethernet, LiteDRAM and PCIe regressions do **not** establish a connected, same-source multi-protocol result. The default generated SoC retains reserved packet endpoints and modeled DDR/HBM targets; the combined test needs its own opt-in RTL variant and elaborated interface check. Work and progress: [epic #34](https://github.com/r987r/xezim-hello-world/issues/34).

## Required configuration and evidence

One source-selected configuration must instantiate the Ethernet GMII/queue/DMA, real LiteDRAM controller and behavioral DFI SDRAM model, PicoRV32/iDMA, PCIe TLP-to-AXI bridge and modeled host Root Complex over the generated local/global data and independent config FlooNoCs. Use `config/regression.yaml`, `config/soc.yaml` and their generator manifests—not hand-edited RTL or a second NoC diagram.

Before a combined run, require actual selected variant elaboration and source-matched bit/port/clock/reset/AXI-ID checks ([#46](https://github.com/r987r/xezim-hello-world/issues/46)), a selected seedable executable INIT/RUN/CHECK action plan ([P0 #152](https://github.com/r987r/xezim-hello-world/issues/152), extending foundations from closed #119), and independent Ethernet, PCIe and real-DDR baselines at the same final source revision. Authored YAML descriptions alone do not execute stimulus.

## Directed first-smoke path

| Boundary | Required independent proof |
| --- | --- |
| GMII ingress | Received frame length, bytes, FCS and selected RX queue/descriptor |
| Ethernet DMA and CQ | Actual AXI AR/R descriptor fetch and AW/W/B payload write; B-gated completion record/cookie/status |
| LiteDRAM | Config-NoC/Wishbone initialization, accepted controller AXI reads/writes, continuously captured DFI/BankModel events and byte-exact frontdoor result |
| CPU0 and PULP iDMA | Real CPU firmware programs descriptors/CSR, polls completion, copies/checks data with independent AXI traffic |
| PCIe host | Host BAR reads from qualified PCIe SRAM staging; actual request/completion TLP pair and byte-identical payload/CQ |

All phases must execute **in one simulation**, with one source SHA, selected action plan, simulator/config/test/run identity, and a single independent scoreboard. Check absent/duplicate/timed-out completions, wrong IDs/tags, bad bytes and unsupported routes as failures. Do not splice individual passing artifacts into a combined PASS.

**Not implied:** the PCIe host **pulling** data over BAR is not endpoint-initiated outbound PCIe DMA into host RAM ([#76](https://github.com/r987r/xezim-hello-world/issues/76)); modeled DFI is not an electrical PHY; HBM remains modeled; CPU IRQ delivery and the direct Ethernet→Compute1→PCIe bypass are separate ([#47](https://github.com/r987r/xezim-hello-world/issues/47), [#43](https://github.com/r987r/xezim-hello-world/issues/43)).

## Reproduction and failure localization

Start with the existing, **independent** baselines:

```sh
make check-generated
python3 tools/regress.py chip-ethernet-cpu
python3 tools/regress.py chip-pcie-host
python3 tools/regress.py chip-ddr4-real
```

These commands are not the combined test. For the new source-selected variant, inspect its `plan.json`, `identity.json`, `result.json`, `test-flow.json`, `axi-transactions.json`, `protocol-transactions.json`, DFI summaries and `simulation.log` under one canonical run. The existing [Test Runs viewer](publication.md) must show exact selected action IDs, actors, dependencies, seed and expected checks alongside *separate* observed protocol handshakes.

On failure, locate the **first unverified boundary** in the table above. Report actual address/ID/tag, actor, expected and observed bytes, first/last captured timestamp and NoC hop when available. Report unobserved timing as **unmeasured**, never estimated. Source-selected logical routes, compiled RTL and accepted traffic are distinct evidence types.

Final epic completion additionally requires the direct fast path and broader stress gates tracked in #34; the first global-route functional smoke alone cannot close the epic.
