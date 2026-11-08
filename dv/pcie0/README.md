# PCIe0 RTL bring-up

The stand-alone tests exercise pinned real `pcie_axi_master` TLP→AXI, a modeled `cocotbext-pcie` Root Complex and either AXI RAM or generated FlooNoC→real SRAM targets. The full-chip test uses dedicated PCIe0 local Data/Config fabrics and real CPU0/PULP iDMA with **modeled** DDR. See [host phase and byte-level acceptance](../../docs/pcie0-host-phases.md). The original host-pulled BAR stage is not a PCIe silicon PHY test. The separate `chip-pcie-outbound` regression now proves CPU-initiated device Memory Write/Read into modeled host RAM, but not physical-link/PCIe PHY behavior.

## Reproduction

```sh
python3 -m unittest tests.test_pcie_bar_contract tests.test_pcie_diagnostic_contract -v
python3 dv/pcie0/run_rtl_smoke.py --check-pin
SIM=icarus python3 dv/pcie0/run_rtl_smoke.py
python3 dv/pcie0/run_noc_smoke.py
python3 tools/regress.py chip-pcie-host
```

The isolated `pcie_noc_tb.sv` reuses Compute0 local NoC only as an isolated fixture; **the full-chip variant uses PCIe0's own fabrics**. Check the pinned upstream dependency and narrow Icarus port-tie-off guard before simulation; do not modify upstream RTL or globally hide compiler errors. Report-only Verilator/Slang warnings are not a clean-lint pass; [#32](https://github.com/r987r/xezim-hello-world/issues/32) owns baseline triage.

Physical link, broader endpoint configuration, multi-tag/completion stress and reset/recovery belong to [#76](https://github.com/r987r/xezim-hello-world/issues/76).

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

**CPU-owned requester transition (merged PR #149, exact-head RTL CI passed).**
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

**The CPU-owned control path passed [exact-head full-chip CI 42504527788](https://github.com/r987r/xezim-hello-world/actions/runs/42504527788) at merge-parent `d695dd8` and was merged as [`45b0427`](https://github.com/r987r/xezim-hello-world/commit/45b0427a06364e551673fb2f04587c666ad96f47).** A prior CI PASS at commit `469d878` proved Cocotb-injected descriptors only, not CPU-owned control. The outbound packet-level passive source capture is added in PR #154; it must pass its own exact-head CI before claiming complete TLP trace correlation.
PCIe PHY/LTSSM, completion queues, stress, and general packet chaining remain
outstanding. The 16KiB shared SRAM
adapter is bounded and intentionally fails on invalid segmented-RAM address
or bank selections. It is a functional model, not a PCIe PHY or cache-coherent
DMA subsystem. Only full-chip `outbound-dma-proof.json`, actual C/iDMA AXI
traces, matched PCIe TLPs, and final shared INIT/RUN/CHECK count as proof.

## Passive outbound TLP evidence (#154)

The existing `dv/pcie0/tlp_trace.py` captures accepted request/completion packets using pinned upstream `PcieIfFrame.to_tlp()`. In `chip-pcie-outbound` it now also records the three physical requester streams: `pcie0.tx_wr_req`, `pcie0.tx_rd_req`, and `pcie0.rx_cpl`. Host→device and device→host read-tag spaces are kept independent, matching completions to actual requests. Missing/unmatched or dangling completions fail the run; a posted MWr is an observed request, **not** a completion TLP.

The host model does not drive internal requester descriptors or implement an independent PCIe packet parser/counter. Exact Root Complex host-memory bytes/guard bands and CPU SRAM readback remain separate checker obligations; the same original `ProtocolTrace` emits per-run packet evidence to the existing report site. Non-outbound and #34 combined tests retain their original source catalog and shared capture lifecycle.
