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
