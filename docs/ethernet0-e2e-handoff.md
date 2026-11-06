# Ethernet0 end-to-end integration handoff

## Verified Ethernet IP MVP

Ethernet issue [#64](https://github.com/r987r/xezim-hello-world/issues/64) now has a **functional bidirectional opt-in RTL variant** in [draft PR #73](https://github.com/r987r/xezim-hello-world/pull/73). The dedicated [Ethernet run #42145885849](https://github.com/r987r/xezim-hello-world/actions/runs/42145885849) at RTL SHA `3dcf2c2ef2e3480f5a4abd78dea49f2ad57a5c22` passed all three jobs: connected GMII regression, upstream six-source AXI mux elaboration, and full-chip Ethernet RX/TX through the actual generated local/global Data and independent Config FlooNoCs.

The full-chip test drives real GMII frames to Ethernet SRAM and bounded modeled DDR, reads back the same 85 bytes using independent frontdoor AXI, validates 32-byte CQ records/producer positions, and sends SRAM- and modeled-DDR-sourced frames out the real MAC with valid FCS. It also checks a no-posted-buffer negative. Focused [RX](https://github.com/r987r/xezim-hello-world/actions/runs/42143412383) and [TX](https://github.com/r987r/xezim-hello-world/actions/runs/42143915021) tests independently prove stalled completion B response ordering and bad-FCS rejection.

The reusable RTL is `rtl/io/ethernet0/ethernet0_mvp.v` (one pinned MAC, one RX and one TX queue), with `ethernet0_axi_mvp.sv` using the pinned PULP AXI mux for six upstream descriptor/payload/CQ masters and `ethernet_queue_axi_regs.sv` using a real AXI4-to-AXI-Lite Config NoC bridge. No in-house replacement MAC, AXI arbitration, DMA or VIP was added.

## Important variant boundary

The *default* committed `gen/chip/soc_top.sv` and architecture diagram still reserve Ethernet packet/CSR attachments. They are **not contradictory** to the measured opt-in variant: `tools/full_chip_gen.py::emit(..., ethernet_mode=True)` generates the live Ethernet instance. Its manifest labels the live attachment but does not mark unmeasured physical DDR controller/PHY or PCIe host as observed. Two opt-in/default source-generation tests and `make check-generated` have passed. A separate exact-variant diagram/parsed-port audit remains on the final checklist.

## What still blocks final #64 closure

1. Real **CPU0 compiled C firmware** must program Ethernet queue registers through Config NoC, ring doorbells, and independently check CQ/IRQ; the current `chip-ethernet` test uses an **AXI BFM** with CPUs held reset, not CPU software.
2. One *combined* simulation must include a modeled **PCIe Root Complex** and demonstrate host-side reads of the **Ethernet-produced** packet and CQ through the real SoC or explicitly checked PCIe SRAM/iDMA staging. The independently merged PCIe path in [#60](https://github.com/r987r/xezim-hello-world/pull/60) proves PCIe/DDR transfers, but not this Ethernet/PCIe join.
3. The original `ETH_RX_SRAM`, `ETH_RX_MODELED_DDR`, `ETH_TX_SRAM_GMII`, `ETH_HOST_PCIe_VISIBILITY`, and `ETH_CPU_CQ_AUDIT` checks must use the *existing common* INIT/RUN/CHECK `StepRecorder` with actual AXI/TLP/GMII observation and no missing/incomplete steps. `trace_phase` labels in the functional test are not equivalent to these recorded gates.
4. The variant-aware source/connection audit, one diagram, actor map, flow report and monitor traffic must agree. Keep physical DDR4/PHY and PCIe PHY/outbound DMA as separate tracks.

## Known unrelated fabric failure

The broader concurrent `supernoc` positive/negative regression failed at `NoBResponseIdQueue` 227,520 ns in [CI #42145885829](https://github.com/r987r/xezim-hello-world/actions/runs/42145885829). See [#75](https://github.com/r987r/xezim-hello-world/issues/75) and proposed fix [#78](https://github.com/r987r/xezim-hello-world/pull/78). The dedicated Ethernet functional result stays valid; do not call global same-ID concurrent traffic qualified until this is resolved.

## Reproduce and hand off

- `python3 tools/regress.py chip-ethernet`: generated-chip RX/TX SRAM and modeled-DDR smoke, Config NoC CSR via CPU0 BFM, passive AXI report.
- `.github/workflows/ethernet-mvp.yml`: pinned vendor source elaboration, connected component simulation and full-chip optional variant CI.
- `docs/ethernet0-closure-gate.md`: the five original final acceptance stages and current checklist.
- `docs/multiprotocol-integration-readiness.md`: the combined CPU/PCIe/Ethernet bring-up and dependencies.

**Decision:** Ethernet is ready to serve as a functional MVP input to the combined test. Keep #64 open and #73 draft until the promised real CPU/host five-step closure gate is passed.
