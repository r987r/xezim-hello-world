# Address map, fabric timing and per-test evidence boundaries

The static [Address Map](../tools/templates/site_address-map.html) documents configured
Data/Config apertures, source-defined CSRs and virtual DRAM mode-register
definitions. It never displays a run's measured read/write counts, programmed
MR values, pass/fail status or DFI scoreboard. Those observations belong
to the selected test's [Test Runs](../tools/templates/site_runs.html) traffic
viewer and per-test AXI/protocol report.

## Address spaces

| Item | Base | Source | Qualification |
| --- | --- | --- | --- |
| DDR data aperture `memory0.ddr0` | `0x140000000` | `config/soc.yaml` | Baseline is 64 KiB behavioral AXI RAM in a 1 GiB architectural window |
| DDR native controller `memory0.ctrl` | `0x40030000` | Pinned LiteDRAM `csr.json` | Verified real-DDR test variant: 16 KiB config window, 32 MiB DFI BankModel |
| PCIe endpoint/requester `pcie0.ctrl` | `0x40040000` | `sw/pcie/pcie_requester.h`, requester RTL, `csr/rdl/pcie_endpoint_prelink_ctrl.rdl` | Source-only definition, not proof of CPU0 Config-NoC or trained-link connectivity |
| PCIe host Type-0 BAR0, COMMAND | PCIe config offsets `0x10`, `0x04` | Real host Config TLPs | Separate PCIe configuration space, **not** SoC MMIO |
| Ethernet queue `ethernet0.ctrl` | `0x40050000` | Checked C/RTL ABI | Source-only until selected RTL/config attachment is qualified |

Within `pcie0.ctrl`, outbound-requester register offsets are
`0x00..0x3c`; endpoint management is `0x1000..0x1018`.
The endpoint's `host_bar0` and `host_command` fields are CPU read-only
hardware aliases of host-owned Type-0 configuration state. These source
definitions do **not** create a second PCIe config bank.

DDR4 MR0–MR6 are DRAM device registers programmed through DFI MRS commands.
Their SystemRDL offsets are **virtual decoding identifiers**, not routable
CPU physical addresses. The static page publishes field definitions only.

## Fabric Explorer timing semantics

The route table enumerates generated initiators and reachable targets,
including PCIe host and Ethernet packet-DMA initiation. A route is not proof
that the corresponding PCIe link was trained or an Ethernet packet traversed
GMII, and it is not evidence that both IPs and the real DDR4 variant were
running simultaneously. The sources and targets must be checked in the
**same test** for such a claim.

Serial one-beat measured stages are AXI handshakes. The terminal AXI
acceptance-to-response delta includes downstream crossbar and model, so a
fast `memory0.ddr0` target result in the default baseline means fast
behavioral AXI RAM—not an activated DRAM row.

A legitimate DDR4 device latency report requires independently captured,
cycle-synchronized DFI commands (ACT, READ/WRITE, PRE, REF), correlated
AXI/DFI transactions, bank/row/page-hit/miss state and explicit timing
parameters (`tRCD`, `tRP`, `tRAS`, `tRFC` and read/write turnaround).
The current standalone DDR latency reporter explicitly leaves controller
scheduling, simulated PHY pipeline and BankModel internal latency
**unmeasured**. Real DFI MRS evidence checks programming, not DDR timing
enforcement or physical PHY behavior. Never label AXI target turnaround
as DDR activate+read latency.

To qualify host→DDR or Ethernet→DDR, record a single full-chip test with
actual ingress protocol observation, correlated NoC AXI, controller
commands, AXI completions, a memory readback/check and provenance under
the same tested SHA. Historical passing tests in separate build variants
cannot be combined into one passing integration flow.
