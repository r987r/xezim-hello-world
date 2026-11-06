# Ethernet0 end-to-end integration handoff

## Verified Ethernet IP MVP

Ethernet issue [#64](https://github.com/r987r/xezim-hello-world/issues/64) now has a **functional bidirectional opt-in RTL variant** in [draft PR #73](https://github.com/r987r/xezim-hello-world/pull/73). The dedicated [Ethernet run #42145885849](https://github.com/r987r/xezim-hello-world/actions/runs/42145885849) at RTL SHA `3dcf2c2ef2e3480f5a4abd78dea49f2ad57a5c22` passed all three jobs: connected GMII regression, upstream six-source AXI mux elaboration, and full-chip Ethernet RX/TX through the actual generated local/global Data and independent Config FlooNoCs.

The full-chip test drives real GMII frames to Ethernet SRAM and bounded modeled DDR, reads back the same 85 bytes using independent frontdoor AXI, validates 32-byte CQ records/producer positions, and sends SRAM- and modeled-DDR-sourced frames out the real MAC with valid FCS. It also checks a no-posted-buffer negative. Focused [RX](https://github.com/r987r/xezim-hello-world/actions/runs/42143412383) and [TX](https://github.com/r987r/xezim-hello-world/actions/runs/42143915021) tests independently prove stalled completion B response ordering and bad-FCS rejection.

The reusable RTL is `rtl/io/ethernet0/ethernet0_mvp.v` (one pinned MAC, one RX and one TX queue), with `ethernet0_axi_mvp.sv` using the pinned PULP AXI mux for six upstream descriptor/payload/CQ masters and `ethernet_queue_axi_regs.sv` using a real AXI4-to-AXI-Lite Config NoC bridge. No in-house replacement MAC, AXI arbitration, DMA or VIP was added.

## Important variant boundary

The *default* committed `gen/chip/soc_top.sv` and architecture diagram still reserve Ethernet packet/CSR attachments. They are **not contradictory** to the measured opt-in variant: `tools/full_chip_gen.py::emit(..., ethernet_mode=True)` generates the live Ethernet instance. Its manifest labels the live attachment but does not mark unmeasured physical DDR controller/PHY or PCIe host as observed. Two opt-in/default source-generation tests and `make check-generated` have passed. A separate exact-variant diagram/parsed-port audit remains on the final checklist.

## The only remaining Ethernet #64 closure gate

Use the existing CPU0 cold boot/C firmware runner in the **same opt-in Ethernet RTL variant** to program queue CSR and policy through the Config NoC, post one RX and one TX descriptor through the Data NoC, then read real SRAM packet bytes, 32-byte CQ records, producer status and IRQ acknowledgment. The external GMII source/sink remains a legitimate testbench peripheral; **do not substitute CPU0 AXI BFMs for CPU0 firmware**. Reuse `sw/ethernet/eth_queue_abi.h`, shared INIT/RUN/CHECK and existing monitors. Polling IRQ status is sufficient for MVP; an OS driver or interrupt service routine is not required.

Once that *one* test passes on the source-exact head and the opt-in source/manifest/port audit is consistent, **merge PR #73 and close #64**. Keep all existing standalone and generated-chip RX/TX SRAM/model-DDR tests as regression gates. Default committed `gen/chip` intentionally remains reserved.

## Moved to #34 multiprotocol integration (not blockers for Ethernet closure)

1. Modeled PCIe Root Complex reads **Ethernet-produced** payload and CQ via real TLPs and independently checks correct host bytes and completion records. Merged PCIe #60 is a reusable foundation, not proof of this join.
2. The five original named `ETH_RX_SRAM`, `ETH_RX_MODELED_DDR`, `ETH_TX_SRAM_GMII`, `ETH_HOST_PCIe_VISIBILITY`, `ETH_CPU_CQ_AUDIT` steps must run together under the shared `StepRecorder` with passive AXI/TLP/GMII correlation and source-true topology/latencies. Do not treat `trace_phase` as complete step records.
3. Broader fabric concurrency assertions, real LiteDRAM, PCIe PHY/outbound DMA and stress/performance remain their independent tracks; they are not Ethernet first-MVP requirements.

## Known unrelated fabric failure

The broader concurrent `supernoc` positive/negative regression failed at `NoBResponseIdQueue` 227,520 ns in [CI #42145885829](https://github.com/r987r/xezim-hello-world/actions/runs/42145885829). See [#75](https://github.com/r987r/xezim-hello-world/issues/75) and proposed fix [#78](https://github.com/r987r/xezim-hello-world/pull/78). The dedicated Ethernet functional result stays valid; do not call global same-ID concurrent traffic qualified until this is resolved.

## Reproduce and hand off

- `python3 tools/regress.py chip-ethernet`: generated-chip RX/TX SRAM and modeled-DDR smoke, Config NoC CSR via CPU0 BFM, passive AXI report.
- `.github/workflows/ethernet-mvp.yml`: pinned vendor source elaboration, connected component simulation and full-chip optional variant CI.
- `docs/ethernet0-closure-gate.md`: the scoped **CPU0 C Ethernet closure** and deferred full-system five-step checklist.
- `docs/multiprotocol-integration-readiness.md`: the combined CPU/PCIe/Ethernet bring-up and dependencies.

**Decision:** Ethernet is already a functional IP-level MVP. Keep #64 open / #73 draft only until actual CPU0 C Ethernet control and CQ audit pass; PCIe host and five-step cross-protocol closure have moved to #34.
