# PCIe0 RTL bring-up

The stand-alone tests exercise pinned real `pcie_axi_master` TLP→AXI, a modeled `cocotbext-pcie` Root Complex and either AXI RAM or generated FlooNoC→real SRAM targets. The full-chip test uses dedicated PCIe0 local Data/Config fabrics and real CPU0/PULP iDMA with **modeled** DDR. See [host phase and byte-level acceptance](../../docs/pcie0-host-phases.md). These stages are not a PCIe silicon PHY test and do not prove outbound device-initiated DMA into host RAM.

## Reproduction

```sh
python3 -m unittest tests.test_pcie_bar_contract tests.test_pcie_diagnostic_contract -v
python3 dv/pcie0/run_rtl_smoke.py --check-pin
SIM=icarus python3 dv/pcie0/run_rtl_smoke.py
python3 dv/pcie0/run_noc_smoke.py
python3 tools/regress.py chip-pcie-host
```

The isolated `pcie_noc_tb.sv` reuses Compute0 local NoC only as an isolated fixture; **the full-chip variant uses PCIe0's own fabrics**. Check the pinned upstream dependency and narrow Icarus port-tie-off guard before simulation; do not modify upstream RTL or globally hide compiler errors. Report-only Verilator/Slang warnings are not a clean-lint pass; [#32](https://github.com/r987r/xezim-hello-world/issues/32) owns baseline triage.

Physical link, endpoint management CSRs, multi-tag/completion stress, reset and outbound host-memory DMA belong to [#76](https://github.com/r987r/xezim-hello-world/issues/76).

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

**Do not call this complete until its exact selected RTL build and simulation
pass.** The intermediate full-chip test still lets Cocotb submit requester
descriptors directly on DUT pins; CPU/Config-NoC requester CSRs, completion
queues, and general packet chaining remain outstanding. The 16KiB shared SRAM
adapter is bounded and intentionally fails on invalid segmented-RAM address
or bank selections. It is a functional model, not a PCIe PHY or cache-coherent
DMA subsystem. Only full-chip `outbound-dma-proof.json`, actual C/iDMA AXI
traces, matched PCIe TLPs, and final shared INIT/RUN/CHECK count as proof.
