# Minimal integrated PCIe ↔ modeled DDR ↔ Ethernet closure

Scope: first **functional** three-protocol data exchange on the **same**
generated 12-NoC SoC. This is a plan and current exact-source evidence, **not**
a declaration that the three-way RTL is already connected.

## Audit — November 5, 2026

**New functional Ethernet evidence:** opt-in generated-chip [CI #42145885849](https://github.com/r987r/xezim-hello-world/actions/runs/42145885849) passed GMII RX/TX into/out of Ethernet SRAM and modeled DDR, through actual Ethernet Data/Config NoCs. This is *not* yet the one combined CPU0 C + PCIe host regression.

Baseline before Ethernet merge: `main` `b91e3d3b7c4fea582fc690a7abbd55c7e32064b4`, including merged PCIe #60 and NoC same-ID fix #78.

| Component | Available evidence | Not yet proven |
| --- | --- | --- |
| PCIe host to modeled DDR | [Merged PR #60](https://github.com/r987r/xezim-hello-world/pull/60), [CI 42134213227](https://github.com/r987r/xezim-hello-world/actions/runs/42134213227) passed real `chip-pcie-host`: RC TLP → PCIe SRAM → real PULP iDMA → modeled DDR → SRAM → host BAR readback; 27/27 flow steps, 47,864 complete AXI transactions and 3,741 PCIe read/completion pairs. | Direct host BAR to DDR, physical PCIe endpoint/link, endpoint-initiated host memory DMA. Initial PCIe integration is merged to `main`; advanced features remain [#76](https://github.com/r987r/xezim-hello-world/issues/76). |
| PCIe/general full-NoC ordering | Previous failing `NoBResponseIdQueue` at 227.52 µs fixed with [merged PR #78](https://github.com/r987r/xezim-hello-world/pull/78), passing its directed local/global positive/negative same-ID regressions. | Extended stress, saturation and performance remain independent qualification; the earlier failure was not a current Ethernet regression failure. |
| Ethernet | [PR #73](https://github.com/r987r/xezim-hello-world/pull/73), [exact-head CI #42162107273](https://github.com/r987r/xezim-hello-world/actions/runs/42162107273) **4/4 PASS**: real GMII RX/TX, SRAM/model-DDR transfers, true descriptor/packet DMA and B-gated CQs, independent Config/Data NoCs, plus **compiled real CPU0 C** configuring queues/IRQ and checking SRAM/CQ through actual PicoRV32 AXI. | Ethernet MVP #64 fulfilled. **Epic #34** still owns modeled PCIe host read of the same Ethernet-produced bytes/CQ with real TLP completion and the five combined `StepRecorder` stages. Default `gen/chip` Ethernet remains reserved; live opt-in variant uses `ethernet_mode=True`. |
| Real DDR4 | [PR #74](https://github.com/r987r/xezim-hello-world/pull/74) RTL AXI Config→Wishbone bridge preflight; upstream LiteDRAM controller and AXI physical aperture bridge independently merged. | Real LiteDRAM attached behind `memory0` local Data/Config NoCs, observed DFII init, CPU/iDMA memory roundtrip and DFI evidence. Independent from minimal modeled-DDR Ethernet/PCIe functional gate. |

## Minimal end-to-end topology

- **Host to memory (proven in #60 opt-in test):** behavioral Root Complex → accepted real PCIe TLP → upstream `pcie_axi_master` → `pcie0_local_data` → `pcie0.sram` → CPU0/PULP iDMA → modeled `memory0.ddr0`, then reverse to PCIe SRAM and completion TLP.
- **Ethernet RX (proved in dedicated optional chip test):** GMII -> upstream FCS/CDC -> whole-frame stage -> queue descriptor -> AXI DMA via Ethernet local/global Data FlooNoCs -> SRAM or modeled DDR -> independent bytes and B-gated CQ readback. [CI](https://github.com/r987r/xezim-hello-world/actions/runs/42145885849). CPU0 C + PCIe host not part of this test.
- **Ethernet TX (proved in dedicated optional chip test):** SRAM or modeled DDR -> descriptor fetch and upstream AXI DMA -> same MAC -> GMII FCS/end -> CQ AXI B -> BFM-observed producer. [CI](https://github.com/r987r/xezim-hello-world/actions/runs/42145885849).
- **Cross-protocol visibility:** CPU0 and PCIe host read **the same Ethernet-produced buffer and CQ** through their existing NoCs or through explicitly checked PCIe SRAM staging. Host success must be backed by an actual accepted completion TLP with correct bytes, not by backdoor copies.
- Global Data and global Config NoCs remain independent. A simulated controller model is **not** the real LiteDRAM/DFI controller.

## Order, ownership and gates

1. **Address & protocol safety:** merged PCIe #60 proves the minimal host/TLP + modeled-DDR path. The local/global same-ID B/R NoC ordering defect #75 is corrected in merged #78 with its positive and negative tests; preserve those regressions. Extended stress remains separate.
2. **Ethernet IP MVP (#73, issue #64):** all four dedicated Ethernet jobs, including **real CPU0 compiled C** queue/descriptor/CQ/IRQ cold-boot and actual GMII/FlooNoC routing, passed [CI #42162107273](https://github.com/r987r/xezim-hello-world/actions/runs/42162107273). The agreed scoped #64 closure gate is satisfied; merge #73 and close #64 when required GitHub checks permit. The default `gen/chip` artifact still reserves Ethernet; `ethernet_mode=True` is the live tested option.
3. **Full-system epic #34 (after Ethernet #64):** build on #60's shared CPU0/C INIT→RUN→CHECK and `StepRecorder`, not a new runner. Exercise `ETH_RX_SRAM`, `ETH_RX_MODELED_DDR`, `ETH_TX_SRAM_GMII`, `ETH_HOST_PCIe_VISIBILITY`, `ETH_CPU_CQ_AUDIT`. Cross-protocol smoke must prove CPU/host observed the same payload/cookie and independently correlated TLP/AXI/GMII events. Check missing/duplicate/incomplete flow steps fail closed.
4. **Current-source truth:** `make gen` + `make check-generated`, generated `soc_top` and NoC manifest, parsed required-port audit, the single diagram, bus/clock contracts and actor labels all agree with actual optional RTL variant. Never promote reserved endpoints globally for a variant that is not instantiated on default `main`.
5. **Real DDR controller track (#40):** maintain fast default `axi_ram`; introduce an explicit `litedram_sim` opt-in after observed Config NoC Wishbone init, DDR AXI AW/W/B and AR/R completion, real CPU/iDMA SRAM→DDR→SRAM data correctness, bounded aperture DECERR and DFI model events. Do not make backpressure/refresh performance a condition of the initial modeled-DDR three-protocol demo.

**Merge and closure policy:** Ethernet #64's real CPU C+GMII+AXI acceptance is **green**, so merge #73 and close #64. Cross-protocol PCIe RC visibility, five combined `StepRecorder` stages and unified route/latency audit remain under #34. Keep #40 real DDR4 controller and #76 advanced PCIe separate; NoC fix #78 is already merged (the historical #75 issue need not block the Ethernet MVP). #41 is closed for initial PCIe functional bring-up, and #76 owns PCIe post-MVP hardening. No cross-protocol route is called measured without simulation at one exact SHA. #35 DDR-A stress and #43 Ethernet fast path remain separate. Physical PCIe PHY/LTSSM, DDR silicon PHY, endpoint-initiated host-memory DMA, saturation and broad backpressure are outside the initial milestone; the already observed fatal NoC assertion is a real regression, not silently deferred by removing the failing test.
