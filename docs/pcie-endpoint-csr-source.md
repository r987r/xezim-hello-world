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
issue #76 and draft PR #230. No synthetic CSR writes or boot PASS.
