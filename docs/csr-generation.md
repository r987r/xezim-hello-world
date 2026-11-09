# CSR ownership, generation and evidence

CSR definitions are **not** an independent SoC address map. Use `config/soc.yaml` for architectural bases/apertures, project SystemRDL for project-owned *relative* register layout, and pinned upstream RTL/generators for vendor register definitions. Per-variant composition must identify which blocks exist in the *actual selected RTL*. A generated map is not proof of an attached frontdoor port, a completed transaction, or backdoor access.

## Source-of-truth boundaries

| Area | Authority | Qualification |
| --- | --- | --- |
| Data and Config NoC windows | `config/soc.yaml`, `tools/address_map.py` | No inferred storage behind reserved addresses |
| Project boot/reset register bank | `csr/rdl/boot_reset_ctrl.rdl` and pinned PeakRDL | Trial generated outputs plus separately selected opt-in live Config-NoC reset variant; default replacement is not implied |
| SoC DMA CSR shim | `rtl/adapters/soc_dma_regs.sv`, firmware ABI | Distinct from upstream PULP iDMA native CSR layout |
| DDR controller CSR | Pinned LiteDRAM/LiteX `csr.json` and Wishbone/DFII | Qualified **only** for a selected real-DDR variant; default `memory0.ctrl` is reserved |
| Ethernet queue CSR | `sw/ethernet/eth_queue_abi.h` and actual queue RTL | Real in selected Ethernet variant; source catalog alone is not attachment |
| PCIe management/HBM CSR | Actual vendor/controller sources when available | Reserved/unavailable until real responder exists |

For the catalog and source-coverage rules see [CSR source coverage](csr-source-coverage.md), [DDR CSR](csr-ddr.md) and [firmware ABI](csr-firmware.md). [#90](https://github.com/r987r/xezim-hello-world/issues/90) owns broader generated-header adoption; [#91](https://github.com/r987r/xezim-hello-world/issues/91) owns full elaborated runtime CSR backdoor binding.

## Generator and firmware contract

Per-IP .rdl supplies offsets, fields, widths, resets, SW/HW access and side effects **for project-owned blocks only**. The composed variant provides absolute instance bases and source/implementation status. Generated C headers, SV banks, JSON and the HTML Address Map must come from the same definitions, never from copied offset lists. Preserve native DMA/DDR register generators and descriptor/CQ ABIs.

Hard errors: duplicate/overlapping fields, misaligned/out-of-window registers, inconsistent base/offset, invalid access/reset width, stale variant fingerprint and missing required real RTL attachment. An unknown upstream CSR should remain **external/unavailable**, not be fabricated. Headers use namespaced compile-time offsets and per-variant base addresses; qualified transitional aliases preserve existing software ABI until tested migration. Check actual RV32I build/ELF and firmware MMIO responses before claiming generated-header adoption. Use volatile 32-bit accesses, legal byte strobes and correct W1C/RC/IRQ/doorbell semantics. A 64-bit DMA descriptor head is submitted via two 32-bit writes and a one-shot doorbell.

## Frontdoor versus backdoor

Frontdoor = actual CPU/BFM MMIO over Config NoC with independently accepted AXI/Wishbone transactions. Logical register metadata does not count as covered until matching traffic is observed. Backdoor = read-only or specifically safe quiescent simulator storage access; it never invokes MMIO side effects and **cannot** count as AXI coverage.

To bind a backdoor, combine logical IP register/field names with an exact-variant elaborated instance inventory; reject optimized-out, ambiguous, mismatched-width and stale paths. Default unknown/side-effectful fields to `frontdoor_only` or `unavailable`. Never use raw writes to simulate W1C, FIFO pops, IRQ acknowledgements or doorbells. Backend-specific Verilator/Cocotb or Xezim VPI/DPI support must be independently qualified; no global public-VPI waiver. Bulk SRAM/DDR/HBM memory injection is a distinct [#39](https://github.com/r987r/xezim-hello-world/issues/39) service.

## Quiescent live-HDL snapshot (scoped #91 milestone)

The existing `ReadOnlyCsrRuntime.snapshot(quiescent=True)` can export
`csr-backdoor-map.json` **only** from validated, exact build/variant
simulator-visible handles. It preserves `build_sha256`, elaboration inventory
and CSR catalog digests, individual logical names, RTL paths, and explicit
per-field read availability. It samples only `backdoor_read_only` fields.
Side-effectful and unbound fields are recorded as unavailable, not read.
Unresolved X/Z or non-quiescent snapshots fail closed; no API writes RTL.

The dedicated Verilator/Cocotb CSR runtime workflow captures the actual
probe's read value and uploads this source-bound JSON. Its
`frontdoor_equivalence_proven=false` and `protocol_traffic_observed=false`
fields are deliberate: this is a **real HDL read**, not yet the full-chip
PeakRDL reset CSR/Config-NoC equality test, Xezim VPI, or public Pages
field-level integration. Those original #91 acceptance gates stay open.

## Run reports and validation

The existing [Address Map](publication.md) displays every configured data/config aperture and, when source-qualified, the actual selected register catalog. The [AXI report](axi-run-reports.md) may filter genuine accepted transactions by register range; no duplicate AXI reporter or invented timing. Label source-defined, elaborated RTL, observed frontdoor, safe backdoor and unavailable separately. DFI ACT/PRE/RD/WR commands are **DDR protocol evidence**, not CSRs.

```sh
python3 tools/address_map.py --output .tools/soc-address-map.json \
  --rdl-out .tools/soc-data-memories.rdl
python3 -m unittest tests.test_csr_backdoor tests.test_address_map \
  tests.test_axi_report tests.test_regression -v
```

The dedicated `.github/workflows/csr.yml` checks pinned SystemRDL compilation and deterministic catalog/header generation. Its metadata PASS is **not** a successful full-chip MMIO/CSR transaction. For active physical-path qualification, correlate original firmware/RTL/checker and passive Config-NoC records from the exact tested run.
