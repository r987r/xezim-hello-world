# PCIe BAR0 complete-span authorization (standalone)
This pure combinational RTL checks the **entire** inbound Memory Request
byte span before mapping host PCI bus BAR0 into the local SoC NoC region.
It enforces full-window alignment, 4 KiB--1 MiB power-of-two aperture,
readiness, zero-length, 32-bit overflow and rejection of straddling
operations in both address domains. A rejected request may not enter NoC.

The Icarus testbench drives valid and invalid cases and fails with `$fatal`
if any illegal transaction is authorized or its computed NoC address leaks.
`blocked_o` is a request *classification*, not a PCIe Completion or AXI B/R.
Integration must independently implement real error responses for refused
non-posted transactions; this source alone never claims a full-chip bridge.
The full-chip OpenPCIe/pcievhost integration is separately tracked in #76.

## Endpoint device prelink, independent host BAR0, PHY status

`pcie_endpoint_prelink_ctrl` owns device-local BAR0 aperture/target, freezes
geometry on COMMIT, and permits LTSSM START only after configuration.
Independently it gates BAR MMIO acceptance on actual host-MSE, link and
NoC readiness. `pcie_bar0_host_cfg` observes the independent root
complex's Type-0 AXI-Lite config handshakes; its BAR0 size-probe and
host-assigned bus address are **not** writable via CPU DBI aliases.
The request-driven behavioral `pcie_phy_status_responder` merely models
receiver detection and cannot force LTSSM/L0.

The three Icarus tests cover negative sequences, separate host/device
ownership and remote-termination absent/retry/reset. They are **not** a
CPU0 Config-NoC/PeakRDL RTL frontdoor or a real cross-provider PCIe
link training/NoC memory test. Such integration stays in PR #225/#76.
