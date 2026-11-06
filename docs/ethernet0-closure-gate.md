# Ethernet0 MVP — issue #64 scoped closure

## Authoritative scope

**Ethernet0 standalone functional MVP is complete at tested RTL SHA `2ae83f279f96ced2f3393dede9e34f3d174e26f5`.** [Full exact-head Ethernet CI 42162107273](https://github.com/r987r/xezim-hello-world/actions/runs/42162107273) passed all four jobs: real PicoRV32 C program using queue Config NoC CSR and SRAM descriptors/CQ/IRQ; actual GMII RX/TX; generated Data/Config FlooNoCs to SRAM and modeled DDR; and six-source upstream PULP AXI mux elaboration. Real CPU0 owns its AXI ports in the CPU acceptance test; no CPU0 BFM is substituted.

**Closure criterion met:** the existing compiled RV32I C-hook cold-boot and shared INIT/RUN/CHECK executed with real CPU0, drove queue/policy/descriptor CSRs through Config NoC and SRAM through Data NoC, observed GMII RX and TX, checked 85-byte RX SRAM bytes and both B-gated 32-byte CQ records/producer/consumer/IRQ acknowledgment. The testbench supplies/sinks GMII only; a separate CPU0 AXI BFM is not used. Retain `chip-ethernet-cpu`, `chip-ethernet` and the focused RX/TX regressions for subsequent changes. This is ready to merge/close #64 subject to GitHub's merge gate.

**Not required to close #64:** PCIe Root Complex visibility of Ethernet data, five combined protocol StepRecorder steps, endpoint-initiated PCIe DMA, real DDR controller/PHY, arbitrary outstanding-ID stress, saturation/performance or full network-stack features. These are separately tracked under [multiprotocol epic #34](https://github.com/r987r/xezim-hello-world/issues/34) (and #40/#75/#76/#78 where appropriate).

## Existing passing RTL regression (retain as merge gate)


- **Connected RTL:** One pinned 1G GMII MAC, FCS/CDC, RX/TX queues, real descriptor DMA, 32-byte B-gated completion writers. [RX standalone CI](https://github.com/r987r/xezim-hello-world/actions/runs/42143412383) and [TX standalone CI](https://github.com/r987r/xezim-hello-world/actions/runs/42143915021) passed exact bytes and completion ordering.
- **Generated-chip pass:** [CI #42145885849](https://github.com/r987r/xezim-hello-world/actions/runs/42145885849) at RTL SHA `3dcf2c2ef2e3480f5a4abd78dea49f2ad57a5c22` passed all three Ethernet jobs: GMII RX/TX, six-source pinned PULP `axi_mux` elaboration, and `chip-ethernet` in the real generated Ethernet Data/Config NoCs against SRAM and **modeled** DDR. Tested SRAM and modeled-DDR packet bytes, GMII TX FCS, CQ records and MMIO producers.
- **Test-level distinction:** `dv/ethernet0/test_chip_mvp.py` uses a CPU0 Data/Config **AXI BFM** while CPUs are held in reset. It emits `trace_phase` RUN/CHECK labels for `ETH_RX_SRAM`, `ETH_RX_MODELED_DDR`, `ETH_TX_SRAM_GMII`, `ETH_TX_DDR_GMII`, and `ETH_UNPOSTED_RX_NEGATIVE`. These are **not** the five final acceptance steps below and do not constitute real CPU0 C code or a modeled PCIe host reading Ethernet payload/CQ.
- **Source truth:** `ethernet_mode=True` generates live optional RTL and manifests; default canonical generated RTL and diagram correctly continue to say Ethernet packet/queue attachments are *reserved*. Generator variant unit tests and `make check-generated` passed. Do not relabel default topology as a measured variant.
- **NoC bug resolved on this base:** [PR #78](https://github.com/r987r/xezim-hello-world/pull/78) merged into `main` as `b91e3d3` and into #73 as `ec236eb`. Its positive/corruption-negative SuperNoC regressions passed. Historical [#75](https://github.com/r987r/xezim-hello-world/issues/75) is tracked separately; its older failure logs must not be mistaken for a current Ethernet failure. [Exact-head Ethernet CI](https://github.com/r987r/xezim-hello-world/actions/runs/42162107273) is green; physical PHY and stress/performance remain unqualified.

**Decision:** standalone Ethernet MVP passes its agreed acceptance gate. Merge #73 and close #64, then launch the PCIe-host/DDR/CPU/iDMA combined five-stage test owned by #34; do not impose that combined test on #64.


## Ethernet #64 remaining acceptance checklist

- [x] Real one-MAC RX/TX and FCS/CDC, descriptor DMA, true memory AW/W/B and AR/R, B-gated 32-byte CQ, no-buffer and bad-FCS negatives.
- [x] Generated opt-in Data NoC packets to SRAM and modeled DDR, Config NoC CSR via BFM, source/manifest check and independent readback; dedicated 3/3 Ethernet jobs passed.
- [x] Compiled **CPU0 C** owns its Data/Config NoC AXI ports (no CPU BFM), with queue ABI CSRs, policy, SRAM RX/TX descriptors and doorbells; `chip-ethernet-cpu` passed.
- [x] External GMII source/sink proves RX 85-byte SRAM readback and TX exact bytes/FCS; real CPU C checks RX/TX CQ cookie, length, status, producers/consumers and IRQ ack after accepted AXI writes.
- [x] Shared INIT/RUN/CHECK plus passive AXI evidence passes at exact RTL SHA `2ae83f2`, retaining source-true opt-in RTL, manifest and port contract. Default generated Ethernet remains reserved and must not be presented as the live optional variant.
- [x] All 4 dedicated Ethernet CI jobs and other applicable PR checks passed at `2ae83f2`. Any subsequent documentation-only commit requires its own GitHub merge-check evaluation; do not suppress RTL assertions.

## Deferred to #34: full Ethernet–DDR–CPU/iDMA–PCIe integration

The original five named stages are **not prerequisites for closing Ethernet #64**. They must still run before declaring the complete combined system functional:

| Shared final step | Full-system proof |
| --- | --- |
| `ETH_RX_SRAM` | Real GMII to Ethernet SRAM, readback and B-gated CQ |
| `ETH_RX_MODELED_DDR` | Real GMII to modeled DDR through the actual generated Data NoCs |
| `ETH_TX_SRAM_GMII` | Descriptor-driven SRAM to physical GMII TX/FCS and CQ |
| `ETH_HOST_PCIe_VISIBILITY` | Modeled Root Complex receives actual TLP completions with *Ethernet-produced* data/CQ via existing PCIe SRAM + iDMA staging |
| `ETH_CPU_CQ_AUDIT` | Real CPU0 C config/control and CQ audit integrated with host test |

Under #34 the five stages must use the existing shared `StepRecorder`, passive AXI/TLP/GMII evidence and exact variant source/diagram reporting; current `trace_phase` labels are insufficient for the cross-protocol signoff. Original stage names retained for compatibility. A failing concurrent same-ID `NoBResponseIdQueue` regression (#75/#78) is tracked independently and must not be hidden or waived for broader fabric qualification.

## Bounds and source of truth

- One RX queue, one TX queue, one policy for MVP. Use pinned upstream MAC, AXI mux and DMA.
- Primary SRAM region and explicitly bounded modeled-DDR alternate aperture only; reject high-bit aliases, invalid regions, and boundary crossings.
- `ethernet_mode=True` physically instantiates the six-source AXI mux and queue Config NoC. Default canonical `gen/chip` + topology diagram intentionally show reserved Ethernet endpoints. Compare variant source, AXI reports and actual net connections before merging; do not hand-edit generated artifacts.
- Keep real DDR4 controller/PHY, outbound host DMA, physical PCIe link and stress/performance out of the first Ethernet MVP acceptance gate.
