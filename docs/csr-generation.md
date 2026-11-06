# CSR ownership and generation contract

Tracking: [#82](https://github.com/r987r/xezim-hello-world/issues/82). This is an **implementation contract only**; generated RTL and firmware changes require dedicated follow-up commits with real RTL/CI evidence. This document does not claim new hardware behavior or test passes.

## Scope boundaries

- `config/soc.yaml` owns subsystem instances and global CSR base/window addresses.
- Per-IP SystemRDL 2.0 (`csr/rdl/<ip>.rdl` once introduced) owns offsets, fields, register widths, reset values, SW/HW access policy, and descriptions for **project-owned** register blocks. A future pinned PeakRDL generation tool combines relative CSR addresses with generated SoC instance bases.
- PULP/FlooNoC AXI4-to-AXI-Lite bridge paths remain the bus transport. Generated register modules are *subordinates* to those existing adapters; never introduce an alternative NoC or MMIO protocol.
- PULP iDMA already generates its native register RTL through MARIO/PeakRDL; preserve that process and import its map for software/reporting. Likewise, LiteDRAM and third-party PCIe register RTL remain vendor-owned.
- Keep packet/DMA descriptors, completion records and runtime memory allocations outside the register map; validate their separate ABIs.
- The current default checked-in generated chip may differ from the opt-in Ethernet/DDR/PCIe RTL. A CSR catalog is selected by the **tested variant**, never inferred from aspirational config alone.

## Generator interface (first implementation slice)

Inputs: per-IP `.rdl`; validated absolute addresses, aperture sizes and enabled-instance records from `config/soc.yaml`; pinned PeakRDL toolchain.

Versioned deterministic outputs (generated, never edited by hand):
- Per-IP `soc_<ip>_regs.h` with offsets/fields/masks/shifts, for C/firmware.
- Per-variant instance-base header `soc_csr_bases.h`, containing only configured SoC instances.
- Per-IP generated SystemVerilog register bank plus a narrow HW interface for external state/side effects, where appropriate.
- `csr-map.json` with variant, source hash, IP/instance, base, size, register, field, access, reset, semantic metadata, and **implemented/reserved/external** status.

Prefer `peakrdl regblock` and `peakrdl cheader`; verify exporter options, licenses, generated naming and RTL integration on the **pinned** version before selecting exact command syntax. For HTML/JSON, use a SystemRDL compiler walk if no suitable pinned exporter provides the required stable schema. Put generated trees under existing generator ownership only when the integration owner approves, honoring `make gen` / `make check-generated` and avoiding parallel shared-tree edits.

Hard errors: duplicate register address, field overlap, register outside its SoC aperture, unaligned register, conflicting absolute/relative addresses, stale schema, missing required RTL attachment, invalid access/reset width, incompatible variant fingerprint. An unavailable third-party register map is **external/unmapped**, not silently fabricated.

## C code generation and footprint

- Convert drivers to include only their own generated IP header; SoC firmware includes only the base-address definitions it requires. Keep a checked transitional alias for existing `ETHQ_REG_*` and `SOC_DMA_REG_*` users until the last migration.
- Prefer compile-time `#define` offsets and `static inline` accessors rather than dynamically allocated register-description tables or a giant always-linked register utility.
- Compiler/linker flags `-ffunction-sections -fdata-sections` + `--gc-sections` should be used when supported; include actual RV32I `size` and `nm` comparisons because unused-data elimination depends on the build/link environment. Header text alone generates no machine code.
- Use volatile 32-bit MMIO, correct access/byte-enable masks, sticky/W1C/RC semantics and explicit fences; preserve ABI and compilation of host plus CPU code. The 64-bit DMA head must still be committed through the existing two 32-bit writes plus doorbell.

## Existing run report: CSR map panel

Add `sections.csr` to the existing `tools/axi_report.py` payload, and one searchable collapsible panel in `tools/templates/run_report.html`. Keep `report.html` self-contained, consistent with the current embedded JSON pattern and mobile scrolling. The map is generated for the current regression variant and included with its SHA/CI fingerprint; no external assets or separately hosted CSR site.

Columns: subsystem/instance, absolute address, register/field, access and side effects, width, reset, implemented/reserved/external, module/source revision. Search by address/name; link a register to existing AXI transactions whose accepted addresses actually overlap its byte range. Reuse **existing** passive `axi-transactions.json` rows for timestamps, monitor, B/R status, observed data and byte strobes. Never recreate an AXI correlator, equate driver intent/backdoor memory writes to an AXI handshake, count a no-traffic register as covered, or assign a latency from static metadata.

Observation status: `not_accessed`, `observed_complete`, `incomplete_or_error`, `unmeasured` (missing/incomplete capture), and `reserved`. Static register metadata is *not* proof of hardware implementation. On older report schemas omit the CSR panel cleanly.

## Ordered independent work

1. **CSR-1** pin PeakRDL stack, author one small project-owned SystemRDL bank (candidate: boot.reset_ctrl), generate namespaced headers + JSON and trial RTL; test deterministic generations, old ABI offsets, negative address/field overlap and missing-map behavior. Avoid editing generated chip NoC/RTL and Ethernet/DDR integration branches.
2. **CSR-2** wire custom register bank into existing AXI-to-Lite subordinate; preserve side-effect logic. Run real CPU/Config-NoC read/write/reset/strobe/error tests and independent AXI observations; compile all firmware variants with section-GC/footprint evidence.
3. **CSR-3** embed and filter the per-variant CSR catalog in the existing HTML, correlating only observed AXI transactions; test stale variants, empty capture, mobile and report correctness.
4. **CSR-4** migrate remaining custom Ethernet and PCIe banks after owners' integration PRs merge; import native iDMA/DDR maps without rewriting vendor RTL.

Coordination: #82 is exclusive owner of CSR data structures, generated C register naming and CSR-specific report panel. #34 owns generic report/event ABI, #79 scenario execution, #39 memory backing/fast-vs-strict providers. Resolve edits of common report/generator files with those owners before making them.
