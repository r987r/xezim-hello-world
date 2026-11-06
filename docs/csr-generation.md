# CSR ownership and generation contract

> **Current implementation status (2026-11-06):** The CSR foundation [#83](https://github.com/r987r/xezim-hello-world/pull/83), native LiteDRAM CSR catalog [#100](https://github.com/r987r/xezim-hello-world/pull/100), human-readable IP → register → field browser [#115](https://github.com/r987r/xezim-hello-world/pull/115), and source-backed DMA/Ethernet CSR reference discovery [#118](https://github.com/r987r/xezim-hello-world/pull/118) have all **merged**. The last merge is `38b38a152a0e25db78a9b865b15a0a0334329d9a`; its [main Pages run #42301109627](https://github.com/r987r/xezim-hello-world/actions/runs/42301109627) has a successful site build, but the deployment/public URL remained a separate verification gate at this review. These source-only references are NOT proof of live Config-NoC RTL or MMIO traffic. The default chip still uses modeled DDR RAM, upstream iDMA native internal CSRs are not imported, and PCIe management CSR responder remains reserved. Generated firmware/RTL adoption and CSR backdoor qualification remain open in [#90](https://github.com/r987r/xezim-hello-world/issues/90), [#86](https://github.com/r987r/xezim-hello-world/pull/86) and [#91](https://github.com/r987r/xezim-hello-world/issues/91). See [source coverage and new-IP gating](csr-source-coverage.md).

## Unified address-map / software adoption matrix (2026-11-06)

| IP or resource | Authoritative source | Implemented in merged main | Follow-on / qualification |
| --- | --- | --- | --- |
| SoC ROM, SRAM, flash, DDR, HBM apertures and CSR windows | `config/soc.yaml` | 64-bit physical window and backing-size map; not all windows are active controller registers | Per-variant exact instance/RTL qualification; do not confuse memory windows with CSRs |
| Project-owned boot/reset | `csr/rdl/boot_reset_ctrl.rdl` + PeakRDL | Generated trial C header, JSON, trial SV; live default register bank not replaced | #86 actual Config-NoC RTL integration, CPU/ACK/strobes/reset equivalence |
| CPU DMA shim | Existing `soc_dma_regs` RTL, software model in #93 | Existing handwritten `sw/dma/dma.h` ABI; real DMA datapath | #90/#93 generated per-IP header and real CPU migration; no duplicated offset constants |
| Upstream PULP iDMA | Pinned upstream generator/RTL | Working vendor engine and descriptor ABI | Import **actual** native CSR map and cross-check against real RTL; never replace vendor CSR RTL with project RDL |
| LiteDRAM controller | Pinned LiteDRAM/LiteX `csr.json` + Wishbone translation | Real DDR-B integration exists as opt-in; default remains fast modeled RAM with reserved control window | #100 merged: native CSR word catalog and qualified DDR-variant Pages selector; no invented bitfields/resets |
| Ethernet queue/MAC | Actual queue RTL and `sw/ethernet/eth_queue_abi.h` | Existing software ABI and protocol tests | #118 **merged**: source-verified C ABI/RTL queue reference catalog and automated new-subsystem discovery; source-only until exact-variant RTL attachment is qualified, descriptors remain separate |
| PCIe bridge | Pinned bridge RTL and any upstream management definitions | PCIe traffic/bridge integration | Source-true control/management CSR catalog only where implemented and exposed |
| HBM | `config/soc.yaml` memory aperture | Memory window/model metadata only | Do not invent HBM controller registers without a real controller and vendor map |

**One register definition per owner:** SoC composition owns *instance and absolute base*, per-IP RDL owns project custom *offsets/fields/semantics*, pinned upstream generators own third-party register layout, and runtime elaboration owns *actual hierarchy handles*. Generate/compose a **per-variant** catalog for HTML, firmware base headers, and verification; no independently maintained duplicate CSR tables. Distinguish source-defined, implemented in exact RTL, and independently observed frontdoor traffic. A successful HTML preview is not a successful production Pages deployment.

**Firmware rules:** Drivers include their own generated IP header and the relevant variant-specific instance-base header, with checked transitional aliases until migration completes. Keep descriptor/CQ structures in separate ABI headers. `#define` offsets/masks have no runtime table by themselves; unused `static inline` functions are eligible for section garbage collection only with compatible compiler/linker flags. Record actual RV32I ELF `size`/`nm` evidence, compile and execute real CPU firmware, and reject ABI/offset drift before claiming that all software is migrated.

**Human-readable Pages:** [PR #115](https://github.com/r987r/xezim-hello-world/pull/115) merged an expandable IP → register → field viewer. The default page renders actual generated boot-reset metadata, while real LiteDRAM native register words require a qualified DDR CI variant. [PR #118](https://github.com/r987r/xezim-hello-world/pull/118) introduces separately labeled C/RTL-crosschecked source references for compute DMA and Ethernet, plus explicit source gaps. The source-only references remain *not* proof that Config-NoC endpoints are active in this build. A successful main Pages deploy and public route check remain required before calling the release done. Field access/reset/side effects appear only when the actual source defines them. Controller DFI ACT/PCH/RD/WR events belong to protocol evidence, not the CSR table.

**Frontdoor/backdoor:** Register frontdoor is CPU/BFM MMIO over the real Config NoC; passive accepted AXI is evidence. Backdoor CSR read is a separate, fail-closed exact-elaboration handle binding under #91 and is **not yet qualified** for all subsystems. Side-effectful registers default frontdoor-only. Bulk SRAM/DDR/HBM backdoor INIT/CHECK providers are owned by #39, not #91. Both consume the same logical composition and must never be counted as frontdoor AXI coverage.

**Release verification:** CSR metadata, active-RTL qualification and independently observed AXI traffic are different evidence classes. [#100](https://github.com/r987r/xezim-hello-world/pull/100), [#115](https://github.com/r987r/xezim-hello-world/pull/115) and [#118](https://github.com/r987r/xezim-hello-world/pull/118) are merged. Source-import exact-head [CSR CI 42300896953](https://github.com/r987r/xezim-hello-world/actions/runs/42300896953), [Pages/browser CI 42300897124](https://github.com/r987r/xezim-hello-world/actions/runs/42300897124) and [test-flow CI 42300896991](https://github.com/r987r/xezim-hello-world/actions/runs/42300896991) all passed. The [post-merge main Pages build 42301109627](https://github.com/r987r/xezim-hello-world/actions/runs/42301109627) contains `address-map.html`, `csr-source-coverage.json` and qualified DDR `ddr-native-csr-map.json` run artifacts, but the deploy job/public route must be verified separately before claiming the latest site is live. Real DDR full-chip CSR evidence [42287564597](https://github.com/r987r/xezim-hello-world/actions/runs/42287564597) passed on its tested PR SHA; do not substitute that for new RTL verification.


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


## Unified SoC physical address space: memories + CSR subset

**Decided:** The full SoC address space includes every declared **data-plane
memory window** (ROM, flash, all configured SRAMs, DDR, HBM) and every
**configuration-plane window** (DMA, reset control, DDR controller, Ethernet,
PCIe). The CSR catalog is a *subset* of this architectural map. Unassigned
holes remain unmapped; we do not describe the whole numerical 64-bit space
as backed memory. The two planes are intentionally separate buses/NoCs even
though they can share the same software-visible physical-address notation.

The only authority for architectural base addresses and window sizes is
\`config/soc.yaml\`. Neither the RDL files nor generated C drivers may
invent, duplicate, or override a physical base. RDL owns per-block *relative*
register offsets, field semantics and configurable local block composition.
\`tools/address_map.py\` combines the full SoC aperture list with an
**optional exact-variant** generated \`csr-map.json\` and explicitly rejects a
stale configuration digest, incompatible variant, overlapping registers, or
out-of-window offsets. For multi-instance blocks, the same RDL type can
be elaborated repeatedly; composition names every instance and applies its
own base. \`tools/csr_backdoor.py\` separately binds these logical paths to
exact compiled RTL storage where the simulator supports it.

SystemRDL supports \`external mem\` with \`memwidth\`, \`mementries\`,
\`sw\` permissions and explicit physical offsets. We emit an optional
\`soc-data-memories.rdl\` view for *all* configured data-plane windows, while
the canonical JSON includes both data and configuration planes. A generated
RDL \`mem\` declaration **does not** instantiate a memory, produce DDR/DFI
protocol logic, prove a NoC route, or make behavioral backing equivalent to
a real memory controller. Existing PULP/tc_sram, AXI RAM and LiteDRAM RTL
remain unchanged. Third-party CSR maps are imported as their native
register definitions when available, not converted to fabricated RAM.

Example (default architectural configuration):
- \`compute0.sram\`: physical window \`0x10000000..0x100fffff\`,
  but default modeled SRAM is **16 KiB**.
- \`memory0.hbm0\`: architectural \`0x100000000..0x13fffffff\`,
  **1 GiB aperture** with only **64 KiB** modeled in the baseline.
- \`memory0.ddr0\`: architectural \`0x140000000..0x17fffffff\`,
  **1 GiB aperture** with only **64 KiB** modeled in the baseline.
- \`boot.reset_ctrl\`: config window \`0x40020000..0x40020fff\`,
  RDL register \`cpu_release\` at **offset zero**, absolute
  \`0x40020000\`; the field width is parameterized by the count of
  secondary CPUs. This is a register definition; trial generated RTL is
  *not* the default SoC's active bank yet.

Those are architectural apertures; changing the DDR variant to real
LiteDRAM must also change the captured backing model/size provenance.
The 32-bit CPU cannot directly dereference above-4-GiB HBM/DDR
addresses; DMA is the intended 64-bit physical address initiator.

### Commands and CI

\`\`\`sh
python3 -m pip install -r requirements.txt -r csr/requirements.txt
python3 tools/csrgen.py --out .tools/csr-verified --variant cold_boot
python3 tools/csrgen.py --out .tools/csr-verified --variant cold_boot --check
python3 tools/address_map.py \
  --csr-map .tools/csr-verified/csr-map.json \
  --variant cold_boot \
  --out .tools/soc-address-map.json \
  --rdl-out .tools/soc-data-memories.rdl
python3 -m unittest tests.test_csr_backdoor tests.test_address_map \
  tests.test_axi_report tests.test_regression -v
\`\`\`

The dedicated \`.github/workflows/csr.yml\` runs these on PRs. It verifies
the real pinned SystemRDL compiler can elaborate the external memory view,
and checks byte-for-byte deterministic CSR RTL/header/catalog generation.
Generation validation is **not** a passing full-chip CSR hardware test.

### One map panel in the existing run HTML

\`config/regression.yaml\` enables a **static architecture-only** map section
for appropriate existing full-chip/NoC AXI reports. \`tools/axi_report.py\`
embeds that map in the same \`axi-transactions.json\` JSON and offline
\`report.html\`; it separately counts accepted AXI *initiator* traffic by
plane and region. \`tools/templates/run_report.html\` shows searchable
region/CSR rows with the declared aperture, modeled-backing capacity and
observed count. Selecting a row filters the existing AXI transaction table.
The report does not create a second AXI monitor or treat map definitions
or back-door accesses as hardware bus evidence. Reports with no map remain
compatible. Register/field detail is shown only when the exact compiled
variant supplies its RDL-derived catalog; otherwise a whole CSR aperture
appears without invented register rows.

**Status boundary:** The RDL metadata, trial generated register bank and
unit/CI checks can be green before the generated register bank is wired into
the active \`soc_top\`, before real backdoor hierarchy handles exist, and
before imported native DDR/Ethernet/PCIe register maps are qualified.
Keep issue #82 and draft PR #83 open for those integration gates.
