# PCIe0 RTL bring-up

The stand-alone tests exercise pinned real `pcie_axi_master` TLP→AXI, a modeled `cocotbext-pcie` Root Complex and either AXI RAM or generated FlooNoC→real SRAM targets. The full-chip test uses dedicated PCIe0 local Data/Config fabrics and real CPU0/PULP iDMA with **modeled** DDR. See [host phase and byte-level acceptance](../../docs/pcie0-host-phases.md). These original BAR-pull stages are not a PCIe silicon PHY test. The separately selected `chip-pcie-outbound` now proves CPU-owned endpoint DMA into **modeled** host RAM, not a physical link.

## Reproduction

```sh
python3 -m unittest tests.test_pcie_bar_contract tests.test_pcie_diagnostic_contract -v
python3 dv/pcie0/run_rtl_smoke.py --check-pin
SIM=icarus python3 dv/pcie0/run_rtl_smoke.py
python3 dv/pcie0/run_noc_smoke.py
python3 tools/regress.py chip-pcie-host
```

The isolated `pcie_noc_tb.sv` reuses Compute0 local NoC only as an isolated fixture; **the full-chip variant uses PCIe0's own fabrics**. Check the pinned upstream dependency and narrow Icarus port-tie-off guard before simulation; do not modify upstream RTL or globally hide compiler errors. Report-only Verilator/Slang warnings are not a clean-lint pass; [#32](https://github.com/r987r/xezim-hello-world/issues/32) owns baseline triage.

Physical link, generalized controller management, multi-tag/completion stress, reset and advanced outbound DMA qualification remain in [#76](https://github.com/r987r/xezim-hello-world/issues/76). The dedicated requester control CSRs are implemented in the selected outbound variant.

## Opt-in outbound host-memory DMA staging (#76)

`python3 dv/pcie0/run_outbound_smoke.py` exercises pinned `dma_if_pcie`
in isolation against a modeled Root Complex. Its earlier exact-head CI
[42451812498](https://github.com/r987r/xezim-hello-world/actions/runs/42451812498)
passed outbound Memory Write/Read TLPs, returned completions and byte checks.
It uses a modeled local segmented RAM, **not** CPU/iDMA/NoC attachment.

`python3 tools/regress.py chip-pcie-outbound` selects the additional,
**opt-in and separately gated** full-chip integration. The real PicoRV32 CPU0
runs compiled C which directs upstream PULP iDMA to move data from modeled DDR
into physically shared PCIe0 `tc_sram` through real FlooNoC. A second,
pinned `dma_if_pcie` requester reads those same physical bytes and issues
posted Memory Write TLPs into **modeled Root Complex host RAM**. The existing
host participant independently checks the 64 host bytes, adjacent guards and
accepted outbound TLPs. A reverse host-memory read produces real completion
TLPs and refills a disjoint region of the shared device SRAM. The original
BAR-pulled `chip-pcie-host` is not modified.

**CPU-owned requester path (merged PR #149, source-qualified exact-head RTL CI passed).**
The full-chip test no longer exposes or drives internal DMA descriptor pins.
The host Root Complex model publishes its 64-bit DMA IOVA through actual PCIe
BAR writes at PCIe SRAM +0x820/+0x824 and a validity word at +0x828. CPU0 C,
after waiting for real PULP iDMA descriptor retirement, writes outbound MWr
and MRd descriptors to `pcie0.ctrl` over the actual Config NoC. The new
`pcie_requester_axi_regs` drives the existing pinned `dma_if_pcie` valid/ready
interface and supplies checked status/tag/error; CPU0 polls both statuses and
checks returned SRAM bytes. The host independently verifies Root Complex RAM,
BAR-readback, guard bytes and passive TLP activity. The isolated requester
unit smoke still uses a direct descriptor BFM at its isolated boundary, which
is appropriate and does not qualify CPU-owned behavior.

**This revised CPU-owned control path passed exact-head RTL CI** ([full-chip workflow](https://github.com/r987r/xezim-hello-world/actions/runs/42499056323) at commit `6a46d2345d6ca86e04346994afa94e7ec69a6fb9`).
A prior CI PASS at commit `469d878` proved a Cocotb-submitted descriptor
datapath only; it must never be reused as qualification for CPU-owned control.
PCIe PHY/LTSSM, completion queues, stress, and general packet chaining remain
outstanding. The 16KiB shared SRAM
adapter is bounded and intentionally fails on invalid segmented-RAM address
or bank selections. It is a functional model, not a PCIe PHY or cache-coherent
DMA subsystem. Only full-chip `outbound-dma-proof.json`, actual C/iDMA AXI traces, requester handshake evidence, independent host RAM/guard readback, and final shared INIT/RUN/CHECK count as this **bounded** proof. Full outbound MWr/MRd/Cpl **passive packet-level** correlation is implemented in [PR #154](https://github.com/r987r/xezim-hello-world/pull/154) and requires source-qualified post-rebase CI before sign-off; and source-selected directed/randomized action adapters remain P0 [#152](https://github.com/r987r/xezim-hello-world/issues/152).


## Passive outbound TLP evidence (#154)

The existing `dv/pcie0/tlp_trace.py` captures accepted request/completion packets using pinned upstream `PcieIfFrame.to_tlp()`. The outbound variant additionally records `pcie0.tx_wr_req`, `pcie0.tx_rd_req`, and `pcie0.rx_cpl` with independent host/device read-tag spaces and fail-closed unmatched completions. Posted Memory Writes are **observed requests**, not completion evidence. Independent host-memory byte and guard checks and CPU SRAM readback remain mandatory. No second TLP parser, AXI driver, or report page is introduced. Complete sign-off still requires exact-head CI.

## Relocated BAR0 address-domain check using real bridge and FlooNoC

The PCIe NoC smoke now runs the unchanged fast TLP-only backend and a separate
opt-in RTL build with *host PCIe BAR0=0x80001000 (4KiB)*, distinct from local
SRAM=0x12000000. The actual pinned `pcie_axi_master` AXI AW/AR bursts go
through `pcie_bar0_noc_translate` into the real generated PCIe0 FlooNoC and
real SRAM, with independent Cocotb byte readback, including the last 16 bytes
of the BAR. Out-of-window requests fail this isolated fixture rather than
producing synthetic successes. The separate production error-response
policy and live device/host programming remain open. **This is not trained
OpenPCIe Gen1 link proof**; the original standalone cross-provider link still
needs to attach its non-config TLP ingress and completion return path.
