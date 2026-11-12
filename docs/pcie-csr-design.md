# PCIe CSR/DBI architecture — RDL source, generated artifacts, and real attachment gates

Tracks [PCIe #76](https://github.com/r987r/xezim-hello-world/issues/76),
[CSR firmware #90](https://github.com/r987r/xezim-hello-world/issues/90),
and [draft PR #225](https://github.com/r987r/xezim-hello-world/pull/225).

The original link-training proof must not be confused with SoC-owned
register-bank integration. **CPU0 does not program the pinned endpoint
through the real Config NoC yet.** An isolated testbench prototype currently
configures BAR0 aperture/target/start before enabling the endpoint LTSSM.

## Four deliberately different address domains

| Domain | Source of truth | Addresses / semantics | Current hardware |
| --- | --- | --- | --- |
| CPU0 / Config FlooNoC PCIe management | `config/soc.yaml` + `csr/rdl/pcie_endpoint_prelink_ctrl.rdl` + existing PCIe requester ABI | `pcie0.ctrl = 0x40040000`; outbound requester `+0x0000..0x003f`; endpoint pre-link `+0x1000..0x100c` | Requester already live in opt-in PCIe outbound SoC; endpoint prelink **RDL source and generated RTL only**, no selected Config-NoC attachment yet |
| Root Complex → endpoint Type-0 PCIe configuration | Pinned upstream `src/pcie_cfg/pcie_config.rdl` + generated `pcie_config_reg` | Host ConfigRd0/CfgWr0: COMMAND `0x04`, BAR0 `0x10`; **not** CPU0 MMIO | Real PHY/DLL/config-TLP path passes; current BAR0 and MSE override in `pcie_bar0_host_cfg.sv` because upstream BAR0 is generated read-only |
| Host PCIe memory address | Original host enumeration TLPs | Host assigned BAR0 `0x80001000` (dynamic, relocatable) | Genuine host config Cpl/CplD and bus-base readback passed; memory TLP path remains separate |
| SoC SRAM / data FlooNoC | `config/soc.yaml` | `pcie0.sram = 0x12000000` | Existing TLP-only bridge/no-link flows pass; real endpoint nonconfig TLP ingress to this bridge is **not yet connected** |

**Do not allocate an independent second `pcie0.ctrl` window** and do not
overwrite the existing outbound-requester firmware ABI. The 0x1000 endpoint
pre-link subwindow is within the existing 64 KiB configured region. A real
Config-NoC implementation must decode it separately from outbound
`pcie_requester_axi_regs`, which currently owns offsets `0..0x3f`.
Keep the qualified original requester mode as the regression baseline.

## What SystemRDL and PeakRDL generate

- `csr/rdl/pcie_endpoint_prelink_ctrl.rdl`: single source for 4×32-bit
  CPU-visible registers, fields, reset/access policy and one-shot
  COMMIT/START commands, explicitly `frontdoor_only`
- `tools/pcie_csrgen.py`: pins the **same** compiler/regblock/C-header
  versions as `tools/csrgen.py`; generates actual synthesizable flattened
  AXI4-Lite PeakRDL `soc_pcie_ep_prelink_regblock` RTL, namespaced
  `soc_pcie_ep_prelink_regs.h` and `csr-map.json` for the exact SoC
  `pcie0.ctrl` base and register layout
- `tests/test_pcie_csrgen.py`: source-compiled ABI/overlap/field/reset/access
  negative tests, deterministic `--check`, and generated RTL/catalog checks
- `tests/fixtures/pcie_csr_headers_smoke.c`: regular C/firmware ABI
  compilation against the generated header
- `.github/workflows/pcie-digital-link.yml` `pcie-csr-generation` job:
  real compiler invocation and artifact with source-qualified generated
  output, separate from the link-training and BAR0 runs

The **generator is added, but its outputs and source compiler gate are not
considered qualified until the exact-head CI job passes**. Emitting files
under `.tools/pcie-csr` is temporary staging for that CI gate.
The production checked-in `gen/` path must remain owned by the repository
atomic generator: do not manually add stale files under `gen/` or bypass
`make check-generated` (see `AGENTS.md`). Before substituting the
live endpoint prelink RTL, explicitly integrate its output emission into
that ownership/build process.

## What truly needs small custom *hardware policy* glue

PeakRDL handles field storage, reset, access policy, byte strobes and
AXI-Lite bus sequencing. The PCIe endpoint still needs an adapter for:

1. Validate BAR aperture as power of two, within configured SRAM window,
   and BAR target alignment/range. **Only** commit a valid pair.
2. Freeze device aperture/target after COMMIT and refuse conflicting
   writes and illegal START; expose sticky error/STATUS fields and
   actual AXI response failure (do not merely set a flag if spec requires
   `SLVERR`).
3. Gate LTSSM startup on device-owned commit/PHY readiness without
   sharing that state directly with the independent root complex.
4. Decode the *host-owned* assigned BAR base into the device SRAM
   address domain; suppress memory traffic until link L0, NoC ready
   and host COMMAND.MSE. Host configuration remains exclusively through
   PCIe TLPs.
5. Preserve standard PCIe BAR all-ones mask-probe and dynamically
   assigned host base, independent of SoC firmware configuration.

The current `dv/pcie_link/endpoint_prelink_ctrl.sv` duplicates storage and
uses a **testbench-only single-cycle cfg interface**. Its behavior is a
prototype for the policy adapter; it is not already a generated AXI4-Lite
bank. The current `dv/pcie_link/pcie_bar0_host_cfg.sv` overlays
host-visible BAR0/COMMAND on the original generated OpenPCIe config
regblock; this is a transitional integration—not another source of
register definitions we should maintain indefinitely.

The upstream `src/pcie_cfg/pcie_config.rdl` defines BAR0 with `sw=r`
and a hardcoded base. This is genuinely incompatible with host BAR0
probe/write/readback semantics. The final selected endpoint must have
**one source-controlled, pin-qualified adjusted upstream RDL** and
regenerated compatible RTL for normal fields. Keep only the specialized
BAR probe/latching/masking and policy glue outside the generator, and
prove that `B/RRESP` and Cpl/CplD statuses are correct for legal and
illegal writes. Do not silently patch generated SV or mask
`SLVERR` with a post-hoc read mux.

## Required migration / acceptance sequence

1. **Source/ABI:** qualify the RDL and generated RTL/C header/map; reject
   overlap with original outbound requester; keep exact source/package
   digests. This source milestone does not check real CPU MMIO.
2. **Local real RTL:** instantiate the generated bank with the existing
   PULP AXI4 ↔ AXI4-Lite adapters; implement minimal policy glue using
   generated `hwif_in/hwif_out`, side-effect fields, and actual error
   responses. Test reset, legal/illegal COMMIT/START, byte strobes,
   immutable post-commit fields, and BAR target range in Verilator.
3. **CPU0 Config-NoC integration:** source-select the genuine endpoint
   alongside existing outbound requester, use the same `pcie0.ctrl`
   response mux/address map; CPU0 RV32I firmware uses **only** generated
   offsets/masks and selected `soc_variant_csr_bases.h`. Capture
   accepted Config-NoC AXI transactions and readbacks in the existing
   canonical Test Runs/CSR report.
4. **Host visible PCI config:** regenerate/qualify the pinned upstream
   SystemRDL register block rather than silently overlay a read-only BAR.
   Keep the independent host model (no backchannel). Validate all-ones
   probe, changing host BAR base, COMMAND.MSE/BME, partial byte enables,
   rejection/error cases and matching TLP completions.
5. **Full memory path:** connect original non-config PCIe TLP RX/TX to
   pinned verilog-pcie bridge → PCIe0 FlooNoC → SRAM, with genuine
   independent bytes/latency/ordering and reset tests. Preserve the old
   fast `chip-pcie-host`/`chip-pcie-outbound` coverage permanently.

Do not close issue #76 or merge PR #225 until selected hardware/firmware
tests and reporting gates are satisfied on the exact tested head.
