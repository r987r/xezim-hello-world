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
