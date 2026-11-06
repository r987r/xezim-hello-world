# Minimal integrated PCIe ↔ modeled DDR ↔ Ethernet closure

Scope: first **functional** three-protocol data exchange on the **same**
generated 12-NoC SoC. This is a plan and current exact-source evidence, **not**
a declaration that the three-way RTL is already connected.

## Audit — November 5, 2026

Current `main`: `9f4b67df04274d626f7bbd572ec89ee603433ffc` (merged PCIe PR #60).

| Component | Available evidence | Not yet proven |
| --- | --- | --- |
| PCIe host to modeled DDR | [Merged PR #60](https://github.com/r987r/xezim-hello-world/pull/60), [CI 42134213227](https://github.com/r987r/xezim-hello-world/actions/runs/42134213227) passed real `chip-pcie-host`: RC TLP → PCIe SRAM → real PULP iDMA → modeled DDR → SRAM → host BAR readback; 27/27 flow steps, 47,864 complete AXI transactions and 3,741 PCIe read/completion pairs. | Direct host BAR to DDR, physical PCIe endpoint/link, endpoint-initiated host memory DMA. Initial PCIe integration is merged to `main`; advanced features remain [#76](https://github.com/r987r/xezim-hello-world/issues/76). |
| PCIe general full-NoC stress | [CI 42134213243](https://github.com/r987r/xezim-hello-world/actions/runs/42134213243) **FAILED**, tracked separately in [#75](https://github.com/r987r/xezim-hello-world/issues/75), `supernoc` and `supernoc-negative` on `u_compute0_local_data.global_out_ni...NoBResponseIdQueue` around 227.52 µs, with overlapping initiators and paused AXI channels. | Root cause and actual counterexample resolution; do not claim full broad CI green or remove the regression from the acceptance path. |
| Ethernet | [PR #73](https://github.com/r987r/xezim-hello-world/pull/73) queue CQ/AXI interface, standalone MAC/stager/RX/TX DMA/CQ modules and source-true generated Ethernet Data/Config NoCs. Descriptor/DMA IP supports a **disabled-by-default** optional region #1 for bounded modeled DDR. | Real GMII→queue→AXI mux→NoC→memory, TX descriptor read→GMII with FCS, CQ written after real B, CPU queue CSR NoC access, and all five named test steps. |
| Real DDR4 | [PR #74](https://github.com/r987r/xezim-hello-world/pull/74) RTL AXI Config→Wishbone bridge preflight; upstream LiteDRAM controller and AXI physical aperture bridge independently merged. | Real LiteDRAM attached behind `memory0` local Data/Config NoCs, observed DFII init, CPU/iDMA memory roundtrip and DFI evidence. Independent from minimal modeled-DDR Ethernet/PCIe functional gate. |

## Minimal end-to-end topology

- **Host to memory (proven in #60 opt-in test):** behavioral Root Complex → accepted real PCIe TLP → upstream `pcie_axi_master` → `pcie0_local_data` → `pcie0.sram` → CPU0/PULP iDMA → modeled `memory0.ddr0`, then reverse to PCIe SRAM and completion TLP.
- **Ethernet RX (not yet connected):** GMII → upstream FCS/CDC → whole-frame stager → policy + posted descriptor → upstream AXI packet DMA → `ethernet0_local_data` → modeled DDR (`0x140000000` / 32 MiB opt-in window) or SRAM → independent byte readback → real AXI CQ writer → CPU-visible CSR producer/IRQ.
- **Ethernet TX (not yet connected):** modeled DDR or SRAM → TX descriptor fetch + upstream AXI DMA read → MAC TX/GMII FCS/line end → CQ AXI B → CPU-visible completion.
- **Cross-protocol visibility:** CPU0 and PCIe host read **the same Ethernet-produced buffer and CQ** through their existing NoCs or through explicitly checked PCIe SRAM staging. Host success must be backed by an actual accepted completion TLP with correct bytes, not by backdoor copies.
- Global Data and global Config NoCs remain independent. A simulated controller model is **not** the real LiteDRAM/DFI controller.

## Order, ownership and gates

1. **Address & protocol safety:** #60's minimal PCIe input and modeled-DDR transfer are now merged and measured on main. Independently investigate [#75](https://github.com/r987r/xezim-hello-world/issues/75) `NoBResponseIdQueue` under concurrent paused writers; keep the failing scenario, without downgrading the successful basic route or claiming broad stress safety.
2. **Ethernet ownership (#73):** implement physically instantiated MAC/queue/CSR connections and TX descriptor fetch, reuse upstream AXI arbitration/transport. Validate RX/TX primary SRAM route, real AXI B and memory/CQ readback first, then explicitly opt in to the 32-MiB modeled DDR region.
3. **One combined opt-in test:** build on #60's shared CPU0/C INIT→RUN→CHECK and `StepRecorder`, not a new runner. Exercise `ETH_RX_SRAM`, `ETH_RX_MODELED_DDR`, `ETH_TX_SRAM_GMII`, `ETH_HOST_PCIe_VISIBILITY`, `ETH_CPU_CQ_AUDIT`. Cross-protocol smoke must prove CPU/host observed the same payload/cookie and independently correlated TLP/AXI/GMII events. Check missing/duplicate/incomplete flow steps fail closed.
4. **Current-source truth:** `make gen` + `make check-generated`, generated `soc_top` and NoC manifest, parsed required-port audit, the single diagram, bus/clock contracts and actor labels all agree with actual optional RTL variant. Never promote reserved endpoints globally for a variant that is not instantiated on default `main`.
5. **Real DDR controller track (#40):** maintain fast default `axi_ram`; introduce an explicit `litedram_sim` opt-in after observed Config NoC Wishbone init, DDR AXI AW/W/B and AR/R completion, real CPU/iDMA SRAM→DDR→SRAM data correctness, bounded aperture DECERR and DFI model events. Do not make backpressure/refresh performance a condition of the initial modeled-DDR three-protocol demo.

**Merge and closure policy:** Keep #34, #40, #64 and NoC regression #75 OPEN; #41 is closed for initial PCIe functional bring-up, and #76 owns PCIe post-MVP hardening. No cross-protocol route is called measured without simulation at one exact SHA. #35 DDR-A stress and #43 Ethernet fast path remain separate. Physical PCIe PHY/LTSSM, DDR silicon PHY, endpoint-initiated host-memory DMA, saturation and broad backpressure are outside the initial milestone; the already observed fatal NoC assertion is a real regression, not silently deferred by removing the failing test.
