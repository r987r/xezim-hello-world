# PCIe Endpoint CPU0 DBI and frontdoor qualification

The original `csr/rdl/pcie_endpoint_prelink_ctrl.rdl` is the sole
CPU-side BAR aperture/target/COMMIT/START/status definition. Pinned
SystemRDL/PeakRDL generates **actual flattened AXI4-Lite register RTL**,
the C header and the full address map; the CI unit suite requires exact
regeneration plus hardware-driven (CPU read-only) host BAR0 and COMMAND.MSE
aliases. Existing outbound PCIe requester at `pcie0.ctrl+0x00..0x3f`
remains unchanged; endpoint registers are `pcie0.ctrl+0x1000..0x1018`.
Host PCIe Type-0 configuration offsets 0x10/0x04 are a separate domain.

The initial source-ABI milestone in #231 generated the register bank. At that milestone the
`soc_pcie_ep_configure()` C helper was ready to compile but did not run
in CPU firmware. Actual hardware policy (write freeze and validation),
Config-NoC fanout, sampled host aliases, legitimate AXI error responses,
real over-link BAR and end-to-end cold-boot verification are tracked in
issue #76. Merged PR #232 qualified the isolated trained-link path.

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

### CPU0 real frontdoor qualification (merged #261)

The selected `chip-pcie-outbound` C firmware now uses a **freshly generated**
header from the original endpoint SystemRDL source (pinned
`csr/requirements.txt`), not duplicated register offsets.
CPU0 issues actual MMIO writes and reads for BAR0 aperture, local target,
COMMIT and START, then checks the committed status and that PHY/L0/host
memory-enable remain inactive. The original `execute_cold_boot` passive
AXI audit now requires both CPU-side and target-side accepted Config-NoC
transactions in the endpoint window, in addition to the original requester
doorbells and full data path.

[PR #261](https://github.com/r987r/xezim-hello-world/pull/261) merged with the real CPU0 frontdoor and passive Config-NoC AXI checks passing. The endpoint register **storage** is still the existing
prelink prototype, not the PeakRDL-generated AXI-Lite block; no actual
OpenPCIe PHY/L0 or host BAR state is attached to this full-chip variant.
Issue #76 remains open until the true trained link and end-to-end flow.
