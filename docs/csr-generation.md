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


## Register-model composition and simulator back-door binding

**Decision:** keep *logical* CSR names, field semantics, and optional back-door
**access policy** in SystemRDL, but do **not** put absolute DUT hierarchy paths
(`tb.dut.gen_compute0...`) into portable `.rdl` definitions. The same block
can be instantiated many times, and generated SV paths change with a
parameterized SoC, simulator optimization and implementation variant.

The full-chip composition process combines:
1. **Per-IP RDL** declarations (relative offsets/fields, reset and SW/HW
   access, side effects and `backdoor_policy` metadata where necessary).
2. **SoC composition** from `config/soc.yaml` / generated endpoint manifests:
   repeated instance names, parent instance relationships, base addresses,
   implementation type (real RTL, behavioral model, reserved), and clock/reset
   domain. It must build a stable *logical* path such as
   `compute1.dma.status.irq_pending`, never duplicate hand-maintained maps.
3. **Elaboration inventory** for the exact full-chip HDL build: only real,
   accessible hierarchical paths discovered or confirmed against that
   simulator's compiled instance/net/array inventory. A simulator adapter may
   resolve a path template from generated RTL metadata, but must compare
   existence, width, direction and storage type with the elaborated design.
   Record the tested source/config/topology hashes and simulator version.
4. **Bound back-door map** (`csr-backdoor-map.json`) with logical path,
   elaborated instance, object kind, field bit range, read/write capabilities,
   side-effect safety, clock domain, backing model and provenance. Validate
   `reg/field -> RTL storage` uniqueness unless intentional aliasing is
   explicit. Missing/optimized-out paths remain `unavailable`, not silently
   redirected to a similar instance or treated as coverage.

Do **not** assume a generated PeakRDL field always has a directly writable
SV variable. Its hardware interface and flop storage may be split; an
interface signal can represent a combinational value, not the authoritative
state. Generated RTL integration must expose a stable, selectively visible
adapter hook only when necessary, without editing upstream IP.

**Policy classes:** `frontdoor_only`, `backdoor_read_only`,
`quiescent_raw_storage_rw`, `behavioral_hook_required`, `unavailable`.
Default to frontdoor-only (or unavailable for external IP). Raw back-door writes
must never pretend to execute MMIO strobes, W1C/RC clearing, doorbells, IRQ
acknowledgement, FIFO pops, or other side effects. For these use real AXI
front-door transactions or a separately verified semantic injection hook.
Register write side effects are *not* reproduced by depositing a value into a
hierarchical signal.

The verification API should address `logical_instance.register.field`
using the generated catalog, not hardcoded simulator paths. It chooses a
policy and simulator binding, gates direct access on quiescence, and
corroborates using real independent frontdoor readback where supported.
SystemRDL metadata describes intent; actual bound paths describe physical
implementation, not register coverage or successful bus transactions.
Read-only backdoor comparisons can accelerate CHECK but never prove routing,
AXI response correctness or CPU firmware accesses.

**Backends:** Verilator cocotb/VPI with selective exposure; Xezim VPI/DPI
using documented array and signal APIs; future UVM RAL backdoor path binding.
Do not enable broad global public-VPI visibility merely for convenience:
protect compilation speed, footprint and intended scope. If an RTL field
cannot be exposed by the compiled simulator, explicitly mark it unavailable
and retain frontdoor access. DDR/HBM **bulk memory backdoor** stays owned
by #39; CSR hierarchy binding is owned by #82. #79 consumes the *logical*
register APIs and may label accesses; it does not own low-level path
resolution. #34 handles visualization/correlation.

**Completion tests:** generate one and two compute-instance variants from
the identical IP RDL and verify distinct logical/physical names, offsets and
base addresses. Use exact elaborated RTL metadata to ensure no dangling,
ambiguous, stale or cross-variant paths. Test reset, W1C, IRQ, doorbell,
write-strobe, read-only register behavior and missing-net cases in both
simulators where supported. Backdoor-to-frontdoor equivalence must be
bidirectional only for *safe ordinary storage*, not for side-effectful fields.
