# PCIe host participant: RTL and verification contract

The `chip-pcie-host` regression runs a **modeled** Cocotb PCIe Root Complex with the pinned real `pcie_axi_master` TLP-to-AXI bridge, dedicated PCIe0 Data/Config NoCs, real CPU0/PULP iDMA and PCIe SRAM. The DDR destination in **this test is behavioral AXI RAM**, not the opt-in LiteDRAM RTL controller. PCIe controller-management CSR remains reserved.

**Two supported PCIe modes:** See the [PCIe verification and report architecture](pcie-verification-modes.md)
for a source-backed diagram and side-by-side evidence matrix. This file's
`chip-pcie-host` flow is the **original fast TLP-only mode**; it remains
the normal regression because it has real CPU/FlooNoC/TLP/AXI/byte reporting.
The new opt-in digital-link test separately proves independent host↔device
LTSSM to L0 using real PIPE, and archives a source-qualified **isolated**
JSON/HTML event timeline. It is not yet a full-chip AXI/NoC reporter
and must not borrow this flow's PASS.

## Execution ownership

- `dv/full_chip/test_boot.py::execute_cold_boot` owns the shared CPU INIT/RUN/CHECK phases; `dv/pcie0/host_adapter.py` is the host enumeration/BAR participant. The PCIe test does **not** add a second coordinator or test runner.
- INIT: CPU0/CPU1 cold-boot and real CPU-visible PCIe SRAM handshake; modeled host enumerates BAR0, reads ready and acknowledges through actual bridge transactions.
- RUN: real CPU0 C/iDMA transfers host BAR-provided 64-byte data via PCIe SRAM to modeled DDR and back, then returns a separate result to PCIe SRAM; host pulls the result with BAR0 reads.
- CHECK: host and CPU acknowledgments plus independent payload, actual AXI/TLP completion and step-report checks must succeed. A source-declared action alone is not an observed transaction.

Host mailbox and offsets are sourced from the selected variant firmware/manifest, not a separate hand-maintained host map. PCIe bridge and SRAM traffic are distinct from DDR PHY timing.

## Reproduce and inspect

```sh
python3 -m unittest tests.test_test_flow tests.test_test_flow_cross_source -v
python3 tools/regress.py chip-pcie-host
python3 tools/regress.py chip-cpu-dma
```

The exact selected run retains `result.json`, `test-flow.json`, `axi-transactions.json`, `protocol-transactions.json`, latency metadata and offline reports. The existing shared Test Runs viewer correlates actual accepted TLP requests/completions and AXI handshakes. Missing, duplicate, failed or timed-out required steps are failures; unrelated NoC ordering/stress has its own gate.

**Limits of `chip-pcie-host`:** Root Complex/link is modeled (no PIPE/SerDes/LTSSM silicon); this **specific** regression uses host BAR pulls, not endpoint-initiated DMA; DDR is modeled and Ethernet is absent. The **separate** `chip-pcie-outbound` regression CPU-programs real Config-NoC requester CSRs and transfers to modeled host RAM ([merged #149](https://github.com/r987r/xezim-hello-world/pull/149)). Broader PCIe stress/trace coverage remains [#76](https://github.com/r987r/xezim-hello-world/issues/76); combined chaining remains [#158](https://github.com/r987r/xezim-hello-world/issues/158).
