# Ethernet0 issue #64 — exact-head functional closure gate

The optional generated-chip Ethernet RX/TX packet path has **passed** through real Data/Config NoCs to SRAM and modeled DDR. The broader CPU0 C plus PCIe host test is **not complete**. Do not close #64 or claim three-protocol integration until all five final steps below pass together with independently verified bytes.

## Verified Ethernet IP MVP (November 5, 2026, Central Time)

- **Connected RTL:** One pinned 1G GMII MAC, FCS/CDC, RX/TX queues, real descriptor DMA, 32-byte B-gated completion writers. [RX standalone CI](https://github.com/r987r/xezim-hello-world/actions/runs/42143412383) and [TX standalone CI](https://github.com/r987r/xezim-hello-world/actions/runs/42143915021) passed exact bytes and completion ordering.
- **Generated-chip pass:** [CI #42145885849](https://github.com/r987r/xezim-hello-world/actions/runs/42145885849) at RTL SHA `3dcf2c2ef2e3480f5a4abd78dea49f2ad57a5c22` passed all three Ethernet jobs: GMII RX/TX, six-source pinned PULP `axi_mux` elaboration, and `chip-ethernet` in the real generated Ethernet Data/Config NoCs against SRAM and **modeled** DDR. Tested SRAM and modeled-DDR packet bytes, GMII TX FCS, CQ records and MMIO producers.
- **Test-level distinction:** `dv/ethernet0/test_chip_mvp.py` uses a CPU0 Data/Config **AXI BFM** while CPUs are held in reset. It emits `trace_phase` RUN/CHECK labels for `ETH_RX_SRAM`, `ETH_RX_MODELED_DDR`, `ETH_TX_SRAM_GMII`, `ETH_TX_DDR_GMII`, and `ETH_UNPOSTED_RX_NEGATIVE`. These are **not** the five final acceptance steps below and do not constitute real CPU0 C code or a modeled PCIe host reading Ethernet payload/CQ.
- **Source truth:** `ethernet_mode=True` generates live optional RTL and manifests; default canonical generated RTL and diagram correctly continue to say Ethernet packet/queue attachments are *reserved*. Generator variant unit tests and `make check-generated` passed. Do not relabel default topology as a measured variant.
- **Other CI blocker:** [SuperNoC regression #42145885829](https://github.com/r987r/xezim-hello-world/actions/runs/42145885829) still fails `NoBResponseIdQueue` at 227,520 ns in a separate generic concurrent-traffic test. This is tracked under [#75](https://github.com/r987r/xezim-hello-world/issues/75) / candidate fix [#78](https://github.com/r987r/xezim-hello-world/pull/78). Never suppress the assertion or claim all repository CI is green.

**Decision:** Ethernet is **functionally ready as the IP input to combined E2E development**. Keep issue #64 open and PR #73 draft under the original final five-step acceptance requirement.

## Five named RUN/CHECK steps

| Name | RUN action | CHECK evidence |
| --- | --- | --- |
| `ETH_RX_SRAM` | Host GMII frame enters real MAC/FCS/CDC/stager, queue rule matches, posted SRAM descriptor fetched through generated Ethernet0 local Data FlooNoC, and DMA writes bytes | Independent AXI SRAM readback equals FCS-stripped frame; accepted AW/W/B tracked; descriptor cookie/policy/length in CQ; CPU CSR CQ producer and IRQ only after successful packet B + CQ B |
| `ETH_RX_MODELED_DDR` | Post bounded RX descriptor targeting `memory0.ddr0` simulation AXI RAM across Ethernet0/local + global + memory-local NoCs | Read back exact bytes from second initiator, check B and CQ ordering, label physical DDR controller/PHY unmeasured |
| `ETH_TX_SRAM_GMII` | CPU/host posts TX descriptor pointing to SRAM and rings TX doorbell; upstream `axi_dma_rd` sends frame to MAC via TX FIFO | AXI AR/RLAST confirms read; physical GMII monitor verifies emitted bytes + FCS; TX CQ/IRQ only after GMII-end marker and successful CQ B, not merely FIFO admission |
| `ETH_HOST_PCIe_VISIBILITY` | Modeled PCIe host/CPU uses shared NoC to read RX buffer and CQ, then posts a TX descriptor (or exchanges via SRAM) | Host-side read data, completion record, and initiator/correlation metadata match Ethernet observed AXI traffic; do not claim physical PCIe LTSSM, PHY or host-memory outbound DMA |
| `ETH_CPU_CQ_AUDIT` | CPU0 INIT programs Config NoC queue CSRs + policy + descriptor/CQ bases; RUN includes RX/TX; CHECK reads CQ and acknowledges interrupt | Real CPU0 C MMIO reads/writes, same `sw/ethernet/eth_queue_abi.h` and host Python ABI; check producer/consumer, cookie/status/length, no early IRQ; per-step JSONL, passive AXI, GMII, and NoC diagram agree on exact SHA |

These names must be present in the shared INIT/RUN/CHECK report. Every CHECK must use actual passive channel handshakes and independent readback; do not infer success from a command/driver invocation.

## Fixed V1 constraints

- One RX queue, one TX queue, one selected policy; accept only a complete FCS-checked frame, no CPU per-frame handoff.
- RX/TX packet buffers are restricted to bounded physical memory apertures. V1 primary-region (`region_id=0`) SRAM remains the default. Optional `region_id=1` maps **only** an explicitly configured second window (for the modeled DDR test: `0x140000000`, 32 MiB), with 64-bit non-aliasing and crossing rejection. Do not expose a catch-all DDR/host-physical DMA window. RX descriptor fetch and RX/TX DMA must use identical whitelist settings.
- Reuse existing pinned `ethernet0_mac_gmii`, `ethernet_rx_frame_stager`, `ethernet_rx_queue_engine`, `ethernet_rx_desc_fetch`, `ethernet_rx_dma`, `ethernet_tx_dma`, `ethernet_cq_axi_writer`, upstream `axi_dma_rd/wr` and upstream AXI arbiter/mux.
- Source of truth `config/soc.yaml`; generated `gen/chip/soc_top.sv`, `gen/chip/manifest.json`, `gen/noc/`, `gen/diagrams/` and README must be regenerated by `make gen` and pass `make check-generated` on identical SHA.
- Do not flip `reserved_idle` / `explicit_axi_error` or change graph edges to wired until actual top-level instances/ports are connected and proven.
- Never promote `GENERATED_STRUCTURAL` to `MEASURED` without traffic at destination. List all PHY, DDR controller, physical PCIe and stress/performance as `UNMEASURED`.

## Remaining implementation and closure gates

- [x] One MAC for RX/TX; true GMII wire-end, FCS/CDC, queue-driven descriptors, upstream RX/TX DMA, packet and CQ AXI completion ordering.
- [x] RX/TX SRAM and bounded modeled-DDR source/destination readbacks through the *opt-in generated* Ethernet Data NoC.
- [x] Six descriptor/payload/CQ initiators through pinned PULP AXI mux; independent Config NoC AXI4-to-Lite queue CSR register access by CPU0 AXI BFM.
- [x] Optional generated `soc_top` and manifest instantiated without changing default reserved variants; generator contract tests and `make check-generated` pass.
- [x] Standalone bad-FCS, unposted-buffer, and stalled CQ B negatives; full-chip unposted-buffer negative.
- [ ] Real CPU0 C firmware programs Ethernet queue CSRs and reads CQ/IRQ (without a substitute AXI BFM).
- [ ] Real modeled PCIe RC sees the **Ethernet-produced** payload and CQ through shared NoC or explicitly checked PCIe SRAM/iDMA staging, with actual matched completion TLPs.
- [ ] All **five original named** steps above have `StepRecorder` INIT/RUN/CHECK events, verified completion and appropriate passive AXI/TLP/GMII correlations; `trace_phase` alone is not a completed step report.
- [ ] Variant-aware required-port audit, route diagram, reported actors and exact-head simulation correlate; default diagram remains reserved/unmeasured.
- [ ] Resolve concurrent global NoC B-response ordering [#75](https://github.com/r987r/xezim-hello-world/issues/75) / [#78](https://github.com/r987r/xezim-hello-world/issues/78) before general fabric signoff; do not make physical DDR controller a dependency of initial modeled DDR smoke.

## Integration with other tracks (not a claim of three-way completion)

- [Merged PCIe PR #60](https://github.com/r987r/xezim-hello-world/pull/60) provides initial host TLP + CPU iDMA **staging through PCIe SRAM to modeled DDR**, with verified return data and 27 complete flow steps. Its independent generic SuperNoC stress/negative CI fails `NoBResponseIdQueue` around 227.52 µs; [issue #75](https://github.com/r987r/xezim-hello-world/issues/75) owns reproduction/repair. #41 closed for PCIe MVP; [#76](https://github.com/r987r/xezim-hello-world/issues/76) covers outbound DMA/PHY/stress. Do not suppress this assertion.
- [DDR-B draft PR #74](https://github.com/r987r/xezim-hello-world/pull/74) has an independently checked AXI-to-Wishbone control target, **not** a full-chip real LiteDRAM Data/Config NoC attachment. The fast AXI RAM model is sufficient for initial Ethernet/PCIe communication; real controller qualification remains #40.
- For initial combined functional integration, use the existing `memory0.ddr0` modeled window and PCIe BAR↔PCIe SRAM↔iDMA↔modeled DDR, never advertise direct host-visible DDR BAR or a PCIe link PHY. Follow the [multiprotocol integration gate](multiprotocol-integration-readiness.md).

## Source-backed handoff

- Live one-MAC Ethernet RTL is in `rtl/io/ethernet0/ethernet0_mvp.v`; the six-source AXI mux is `ethernet0_axi_mvp.sv` and queue config bridge is `ethernet_queue_axi_regs.sv`.
- The opt-in generated-chip test is `python3 tools/regress.py chip-ethernet` with result artifacts linked above. Its 85-byte RX/TX and modeled-DDR results are **functional** evidence, not the final CPU/host E2E proof.
- Reuse existing `sw/ethernet/eth_queue_abi.h`, PCIe host participant, shared `StepRecorder`, and common report/diagram generators for final integration. No competing framework.
