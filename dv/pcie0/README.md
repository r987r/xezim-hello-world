# PCIe0 isolated real-RTL bring-up

Issue [#36](https://github.com/r987r/xezim-hello-world/issues/36) / draft [#51](https://github.com/r987r/xezim-hello-world/pull/51).

## What this tests

**cocotbext-pcie RootComplex → PcieIfDevice (modeled Endpoint/link) → real pinned
verilog-pcie pcie_axi_master RTL → cocotbext-axi AxiRam memory model.**
Host enumeration, BAR memory writes, reads, unaligned transfers, partial AXI
byte strobes and read-completion data are compared independently. We do not
author our own PCIe TLP bridge, AXI BFM or Root Complex model.

The Root Complex and Endpoint's configuration/link semantics are modeled.
Only the TLP-to-AXI4 bridge is real RTL. AxiRam is a testbench model,
not actual FlooNoC, PULP SRAM or a physical DRAM/PHY. This regression
does not exercise PIPE, LTSSM, SerDes, outbound host DMA or MSI/MSI-X.

## Source and tool pinning

See [upstream.lock.json](upstream.lock.json) for the full immutable upstream
revision, MIT licensing, five real bridge RTL modules, upstream PcieIfDevice
test utility, and Python/Icarus test dependencies pinned to the upstream 2024
tox configuration. CI uses actions/checkout with that exact commit and rejects
revision mismatches before simulation. The checkout is ignored under .tools/.

To reproduce locally after installing Icarus Verilog and the locked Python
packages, check out upstream at the pinned revision under .tools/verilog_pcie:

    python3 -m unittest tests.test_pcie_bar_contract -v
    python3 dv/pcie0/run_rtl_smoke.py --check-pin
    SIM=icarus python3 dv/pcie0/run_rtl_smoke.py

The targeted workflow in .github/workflows/pcie0-bridge.yml does not publish
Pages. The shared config/ip.lock.yaml, Bender, soc.yaml and gen/ are left
untouched for the #38 integration owner to consolidate later.

## Follow-on acceptance gates — NOT yet tested

1. Actual PCIe0 local data FlooNoC and real PULP SRAM, with the same bridge;
   no host-only AxiRam shortcut in the eventual acceptance test.
2. Dedicated AXI-Lite bridge for BAR-controlled CSR access, separate from
   the 64-bit AXI4 packet/data window.
3. Multiple outstanding tags, timeout/error/UR, completion fragmentation,
   read/write backpressure, reset, AXI ID/route integrity, and passive
   correlation in the existing unified protocol report.
4. Full-chip PCIe0 local/global data/config NoC integration under #41;
   retained CPU/DMA regressions and legal clock/reset/CDC.
5. Outbound device-to-host TLP DMA tested against Root Complex memory;
   filling PCIe0 SRAM is not yet host-delivered packet traffic.
6. Real ASIC PCIe controller/PHY qualification remains separate.

Keep this PR draft until the real local-NoC/SRAM gate and exact-head CI pass.
