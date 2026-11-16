# PCIe Endpoint CPU0 DBI — source ABI only

The original `csr/rdl/pcie_endpoint_prelink_ctrl.rdl` is the sole
CPU-side BAR aperture/target/COMMIT/START/status definition. Pinned
SystemRDL/PeakRDL generates **actual flattened AXI4-Lite register RTL**,
the C header and the full address map; the CI unit suite requires exact
regeneration plus hardware-driven (CPU read-only) host BAR0 and COMMAND.MSE
aliases. Existing outbound PCIe requester at `pcie0.ctrl+0x00..0x3f`
remains unchanged; endpoint registers are `pcie0.ctrl+0x1000..0x1018`.
Host PCIe Type-0 configuration offsets 0x10/0x04 are a separate domain.

This PR **does not wire generated RTL to the real CPU0 Config-NoC**. The
`soc_pcie_ep_configure()` C helper is ready to compile but does not run
in CPU firmware yet. Actual hardware policy (write freeze and validation),
Config-NoC fanout, sampled host aliases, legitimate AXI error responses,
real over-link BAR and end-to-end cold-boot verification are tracked in
issue #76 and active draft PR #232 (superseding closed #230). No synthetic
CSR writes or boot PASS.

## P0 #76 Config-NoC address-path increment — November 16, 2026

The opt-in `chip-pcie-outbound` variant now selects the endpoint pre-link
policy prototype at offsets `0x1000..0x1018` behind the **existing**
`pcie_requester_axi_regs` AXI4-to-AXI4-Lite converter. The original
requester `0x00..0x3f` window and actual DMA descriptor ownership remain
unchanged. Unsupported or illegal endpoint writes return SLVERR and the
prototype latches a violation. This is a narrow first wiring increment.

**Evidence boundary:** The generated PeakRDL AXI4-Lite register-bank RTL
is **not** attached by this change; the pre-link prototype is used. The
outbound SoC does not yet instantiate the trained OpenPCIe endpoint/PHY,
so genuine PHY, L0, host MSE and NoC readiness inputs are all held inactive
rather than fabricated. Source-level generated-RTL checks do **not** prove
the CPU0 firmware actually executed endpoint MMIO, a real link reached L0,
or any full-chip PCIe readback. Issue #76 remains open until these original
hardware gates are independently qualified. PR #232's real PCIe-to-SRAM
qualification remains an isolated, separately proven path.
