# Ethernet0 MVP — issue #64 scoped closure

## Authoritative scope

The opt-in generated-chip GMII RX/TX through actual Ethernet Data/Config FlooNoCs to SRAM and modeled DDR **already passes** [CI 42145885849](https://github.com/r987r/xezim-hello-world/actions/runs/42145885849). Ethernet #64 is now *the CPU0 C control milestone*, not the entire four-protocol integration project.

**Close #64 and merge Ethernet PR #73 after one additional integration gate:** real PicoRV32 CPU0 compiled C must configure the Ethernet queue through its real Config NoC CSR, publish at least one RX and one TX descriptor using the documented shared queue ABI, observe GMII RX/TX, independently validate SRAM payload bytes and both real B-gated CQ records, read/ack producer and IRQ status, and complete INIT/RUN/CHECK without a CPU0-port AXI BFM replacing the CPU. Use existing firmware bootstrap and test-flow infrastructure. Polling is acceptable for this first MVP; no new interrupt-driven service framework is required.

**Not required to close #64:** PCIe Root Complex visibility of Ethernet data, five combined protocol StepRecorder steps, endpoint-initiated PCIe DMA, real DDR controller/PHY, arbitrary outstanding-ID stress, saturation/performance or full network-stack features. These are separately tracked under [multiprotocol epic #34](https://github.com/r987r/xezim-hello-world/issues/34) (and #40/#75/#76/#78 where appropriate).

## Existing passing RTL regression (retain as merge gate)


- **Connected RTL:** One pinned 1G GMII MAC, FCS/CDC, RX/TX queues, real descriptor DMA, 32-byte B-gated completion writers. [RX standalone CI](https://github.com/r987r/xezim-hello-world/actions/runs/42143412383) and [TX standalone CI](https://github.com/r987r/xezim-hello-world/actions/runs/42143915021) passed exact bytes and completion ordering.
- **Generated-chip pass:** [CI #42145885849](https://github.com/r987r/xezim-hello-world/actions/runs/42145885849) at RTL SHA `3dcf2c2ef2e3480f5a4abd78dea49f2ad57a5c22` passed all three Ethernet jobs: GMII RX/TX, six-source pinned PULP `axi_mux` elaboration, and `chip-ethernet` in the real generated Ethernet Data/Config NoCs against SRAM and **modeled** DDR. Tested SRAM and modeled-DDR packet bytes, GMII TX FCS, CQ records and MMIO producers.
- **Test-level distinction:** `dv/ethernet0/test_chip_mvp.py` uses a CPU0 Data/Config **AXI BFM** while CPUs are held in reset. It emits `trace_phase` RUN/CHECK labels for `ETH_RX_SRAM`, `ETH_RX_MODELED_DDR`, `ETH_TX_SRAM_GMII`, `ETH_TX_DDR_GMII`, and `ETH_UNPOSTED_RX_NEGATIVE`. These are **not** the five final acceptance steps below and do not constitute real CPU0 C code or a modeled PCIe host reading Ethernet payload/CQ.
- **Source truth:** `ethernet_mode=True` generates live optional RTL and manifests; default canonical generated RTL and diagram correctly continue to say Ethernet packet/queue attachments are *reserved*. Generator variant unit tests and `make check-generated` passed. Do not relabel default topology as a measured variant.
- **Other CI blocker:** [SuperNoC regression #42145885829](https://github.com/r987r/xezim-hello-world/actions/runs/42145885829) still fails `NoBResponseIdQueue` at 227,520 ns in a separate generic concurrent-traffic test. This is tracked under [#75](https://github.com/r987r/xezim-hello-world/issues/75) / candidate fix [#78](https://github.com/r987r/xezim-hello-world/pull/78). Never suppress the assertion or claim all repository CI is green.

**Decision:** Ethernet is **functionally ready as the IP input to combined E2E development**. Keep issue #64 open and PR #73 draft under the original final five-step acceptance requirement.


## Ethernet #64 remaining acceptance checklist

- [x] Real one-MAC RX/TX and FCS/CDC, descriptor DMA, true memory AW/W/B and AR/R, B-gated 32-byte CQ, no-buffer and bad-FCS negatives.
- [x] Generated opt-in Data NoC packets to SRAM and modeled DDR, Config NoC CSR via BFM, source/manifest check and independent readback; dedicated 3/3 Ethernet jobs passed.
- [ ] Compiled **CPU0 C** owns its data/config ports, not the test BFM, and uses `sw/ethernet/eth_queue_abi.h` and shared C APIs to program at least one RX and one TX queue (descriptor, policy, ring bases, doorbell).
- [ ] External GMII simulation sends one RX frame and observes one TX frame. C/verification reports check payload bytes in SRAM, valid GMII TX FCS, 32-byte RX/TX CQ cookie/length/status, producer/consumer, IRQ assertion and acknowledgment **only after real AXI completion**.
- [ ] Pass same exact-head Ethernet RTL/CPU test using existing INIT/RUN/CHECK and independent B/R channel data, not injected success pulses or memory backdoors. Keep default generated Ethernet reserved; audit actual opt-in top ports/manifest/reported actor, and report only measured paths.
- [ ] Required merge CI passes on head, or any unrelated global stress regression is explicitly documented in #75/#78 and handled under repository merge protections; no silent assertion suppression.

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
