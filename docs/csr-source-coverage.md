# CSR source-reference completeness and new subsystem admission

The **Address Map** and **CSR browser** share the configured SoC aperture
catalog. Register definitions are divided into intentionally different groups:

- **Selected-variant definitions:** generated SystemRDL registers for the exact
  configured build, or native LiteDRAM CSR words from a verified successful
  DDR regression artifact. These are definitions, not proof of every MMIO access.
- **Source-only references:** offsets extracted from a checked-in C ABI and
  checked against the corresponding RTL register decoder/contract. These are
  useful for software and exploratory inspection but do **not** prove active
  attachment to the Config NoC in the selected build. They are never added to
  the measured AXI event counts or silently copied into a variant's
  `registers` array.
- **Unavailable/reserved:** source maps not available/qualified are explicitly
  listed with reasons and remain without fabricated registers or fields.

## How new subsystems work

`config/soc.yaml` determines which subsystem instances and Config-NoC
apertures exist. The publisher builds its address-map catalog from that
composition and applies declarative plugins from `csr/source-registers/*.yaml`.
A plugin selects an existing subsystem **type**, optionally a specific IP
kind, and an aperture suffix (for example `compute*.dma` or Ethernet queue
`*.ctrl`). A newly configured matching instance automatically inherits
the authoritative C ABI/RTL reference without a new list of instance names.

New source imports must state the actual header, RTL source, register macro
prefix, how RTL addresses are checked, and any source-verified flag-field
groups. The importer never carries a second manually entered register offset
list, and it checks duplicate offsets, alignment, aperture bounds,
RTL/header drift, and source SHA provenance.

If a configured instance matches a source plugin but its CSR aperture is
missing, CI **fails**. If an entirely new controller/register interface has
no verified source plugin, it appears as a coverage gap and CI fails unless
its exact instance is explicitly documented in `known-gaps.json` with a
reason. Expected default gaps include the modeled DDR controller window
and PCIe management registers that are not yet implemented.

The output `data/csr-source-coverage.json` records reference counts,
exact header/RTL SHA-256 fingerprints, known gaps, and their reasons. The
Address Map links to that report. This is a *documentation/composition gate*:
a new subsystem also needs its own RTL generation and connectivity
qualification to claim functioning hardware.

## Source categories and qualification

| Interface | Source / status |
| --- | --- |
| Boot reset control | Project SystemRDL/PeakRDL generated register and fields in CI; active default RTL replacement is separately tracked |
| Compute0/1 DMA shim | Four C ABI offsets crosschecked with `soc_dma_regs.sv`; source-only unless independently qualified for exact build |
| Ethernet queue control | Existing `eth_queue_abi.h` register offsets crosschecked with `ethernet_queue_ctrl.sv` read/write CSR cases; source-only in baseline |
| Real DDR4 controller | Qualified native LiteDRAM/LiteX `csr.json` only when a real DDR CI result is available for the corresponding variant |
| PCIe management | Reserved/unimplemented register responder; no fabricated registers |
| Upstream PULP iDMA native control | Separate from SoC's DMA submission shim; internal vendor-specific CSR import not yet qualified |
| HBM | Memory aperture/model, not an active controller CSR catalog |

**Completion / release gates:** per-instance coverage from current config,
source/RDL/RTL validation, negative tests for new and missing sources,
desktop/mobile browser checks, exact-head GitHub Actions validation,
post-merge GitHub Pages deployment and public-route review. The larger CSR
program additionally includes generated C/firmware adoption (#90), actual
custom register RTL migration (#82), and frontdoor/backdoor equivalence
(#91). None of these are inferred from the presence of an HTML table.
