# DMA bring-up foundation

**Current status (2026-11-04):** The reusable descriptor allocator and CPU0 AXI BFM preload vectors are implemented. The **real pinned PULP iDMA frontend + generated rw_axi backend now compile and pass isolated Verilator/cocotb RTL traffic verification**: a 100-descriptor chain to the DDR model and a separate descriptor to the HBM model. The checker verifies actual payload memory, descriptor writeback, final IRQ and idle before SRAM reuse. [Successful DMA CI run](https://github.com/r987r/xezim-hello-world/actions/runs/41860245485), commit `a2c12133b2a57c49ae90b638384335fc6584f331`. Both engine and CSR wiring now *is generated* for the full-chip FlooNoCs, and their end-to-end DMA traffic **passed** [full-chip CI run 41885417960](https://github.com/r987r/xezim-hello-world/actions/runs/41885417960), while CPU-initiated DMA/ISR software and physical DDR/HBM controllers remain unintegrated.

## Existing libraries and software

- Reuse pinned PULP iDMA with its descriptor frontend and generated AXI backend. Do not write another DMA engine.
- Reuse existing cocotb + cocotbext-axi drivers, AXI trace collection, and declarative regression framework.
- sw/dma/dma.h and dma.c provide a portable freestanding SRAM arena, 32-byte upstream descriptor construction, bounds checks and a release fence; no heap is required.
- dv/common/dma_vectors.py generates host-side deterministic descriptor chains, SRAM contents and independent AXI expected-data checks. tools/dma_vectors.py provides CLI generation.

## Boot-live-compatible SRAM allocation

For combined boot + DMA tests, each compute SRAM currently models only 16 KiB; the full architectural window is larger.

| SRAM offset | Purpose | Capacity |
| --- | --- | --- |
| 0x0000..0x0fff | Reserved CPU code/stack/mailboxes | 4 KiB |
| 0x1000..0x1fff | Contiguous 32-byte DMA descriptors | 128 entries |
| 0x2000..0x3fff | Source payload | 8 KiB |

100 descriptors x 64 bytes require 3,200 bytes of descriptors and 6,400 bytes of payload. Source and destination addresses derive from config/soc.yaml; bounds are checked against modeled capacities.

## Host validation commands

    python3 -m unittest discover -s tests -p 'test_dma_*.py' -v
    python3 tools/dma_vectors.py --count 100 --length 64 --out .tools/dma-vectors
    cc -std=c11 -Wall -Wextra -Werror -pedantic sw/common/sram_pool.c sw/dma/dma.c sw/dma/tests/test_dma.c -o /tmp/dma-sw-test
    /tmp/dma-sw-test

The generator writes source_sram.hex in 64-bit readmemh word order, plus case.json with chain head and every independent expected payload. Successful generation alone is NOT a hardware DMA test. For the actual independent RTL test run `make dv-dma`; it uses upstream Cocotb AXI RAM targets and checks real transactions and completion. The host preload is never enabled in the CPU cold-boot regression.

## Hardware bring-up gates: isolated and full-chip RTL traffic passed

1. **PASS, isolated:** Fetch pinned iDMA; generate upstream AXI backend and descriptor register RTL with MARIO and PeakRDL. Use the PULP AXI/APB versions locked by FlooNoC; no local DMA datapath copies.
2. **PASS, isolated:** Instantiate real desc64 frontend + backend, combine descriptor/payload AXI through upstream `axi_rw_join`/`axi_mux` with 3-bit internal / 4-bit shared external AXI IDs.
3. **PASS, isolated:** Exercise a real upstream 64-bit APB head submission, hardware-prefetched linked descriptors, 100 copies to the DDR stand-in, another copy to the HBM stand-in, descriptor writebacks, and one sampled final IRQ per chain, with DMA idle before descriptor-pool reuse. `make dv-dma` executes this gate in Verilator.
4. **PASS, full-chip RTL:** The same pinned engine is generated into both compute DMA ports, including 32-bit CSR writes through the config FlooNoCs. The [chip-dma regression](https://github.com/r987r/xezim-hello-world/actions/runs/41885417960) verified one DDR descriptor, four HBM descriptors, and a 100-descriptor DDR chain, independent AXI readback, descriptor writeback and IRQ handling. Maintain source-ID/outstanding budgets within `config/interface_contracts.yaml`.
5. **PASS, CSR hardware; CPU software pending:** The generated AXI4-to-Lite/register adapter stages a 64-bit APB descriptor head as two 32-bit writes and commits via a doorbell. The test verifies 32-bit configuration writes, sticky IRQ/status and acknowledgments; CPU-written submission and interrupt-service firmware are not yet implemented.
6. **PENDING, stronger regressions:** The basic remote DDR/HBM NoC transfers have passed. Still add stalls/negative SLVERR, deliberate corruption, unaligned payloads, additional queued-job and backpressure tests, and performance sweeps. Maintain cold boot's no-preload invariant and make a separate CPU-started DMA test.

**Do not preload writable SRAM in existing cold-boot tests.** They prove CPU0 copies code through its bus and must remain unmodified. DMA preload must be an explicit DMA-only verification mode. The stock desc64 frontend overwrites the first 8 bytes of completed descriptors with a completion marker; the arena cannot be reused before retirement and descriptors must be reinitialized. Linked descriptors are not automatically a data-dependency barrier. A release fence does not replace cache maintenance on cacheful CPUs.

## Shared cold-boot and DMA SRAM ownership

tools/sram_layout.py is now used by BOTH tools/chip_bootgen.py and
dv/common/dma_vectors.py. The primary SRAM reserves actual firmware
and coordinator mailbox ranges; secondary SRAM reserves its own live
firmware. DMA descriptor and payload pools start at 0x1000 and 0x2000.
Shared layout validation rejects overlaps and undersized windows.

sw/common/sram_pool.h/.c implements a shared freestanding region allocator
used by sw/dma/dma.c. Reclaiming boot-only scratch requires the explicit
CHECK-complete and quiesced-consumers handoff. Executable firmware is never
reclaimed while CPUs execute from it; live mailboxes remain reserved.
The existing firmware is generated RV32I assembly rather than compiled C,
so this change unifies its memory ownership policy, not its ISA bootstrap.
A future C BSP can instantiate the same SRAM pool.

Run make check-config for ownership/descriptor tests or make dv-dma-vectors
to generate the host-only 100-descriptor fixture. This does not preload
writable SRAM during the cold-boot regression.

## Split-run SRAM reuse: explicit profiles

The same allocator policy now supports two contexts, chosen explicitly:

- `boot_live`: preserve live firmware, mailbox and descriptor separation.
  CPU cold boot uses this layout and continues to execute real ROM/flash
  copies. Descriptor pool begins at SRAM + 0x1000; payload at +0x2000.
- `dma_only`: in a separate reset/verification run, no CPUs are executing.
  The first 4 KiB can be reused for 128 descriptors from SRAM + 0x0000,
  and 12 KiB of payload starts at SRAM + 0x1000. The host vector tool
  defaults to this profile; the Python API retains `boot_live` by default.

Use `python3 tools/dma_vectors.py --profile dma_only` for the isolated
test or `--profile boot_live` for a future combined CPU + DMA test.
The selected profile and all named physical regions are in case.json.
Never use `dma_only` with a live/booting CPU; do not backdoor-preload the
cold-boot target.

Within a running chip, only boot_scratch can currently be reclaimed after
CHECK completion and user quiescence. Executing SRAM firmware and observed
mailboxes remain reserved. Reusing those requires a verified CPU handoff,
relocation/parking outside reclaimed SRAM, and retired AXI accesses; that
runtime handoff is future work.

## Split-run SRAM reuse: explicit profiles

The shared SRAM allocation policy supports two contexts:

- `boot_live`: preserves executing firmware and coordination mailboxes.
  Descriptor pool begins at SRAM + 0x1000; payload at +0x2000.
  CPU0 still copies firmware through the real buses, never via preload.
- `dma_only`: separate simulation, starting at reset with CPUs stopped.
  Reuses the boot area: descriptors begin at SRAM + 0x0000 and the
  12 KiB payload pool starts at +0x1000 (for the current 16 KiB SRAM).

Use `python3 tools/dma_vectors.py --profile dma_only` for an isolated
DMA run, or `--profile boot_live` for a future combined CPU + DMA run.
The host CLI defaults to dma_only. The Python API defaults to boot_live
to preserve existing integration-test address expectations. case.json
records the profile and all physical regions.

The original cold-boot regression must never use dma_only. For a running
chip, only a distinct boot_scratch region is presently releasable after
CHECK and quiescence; executing SRAM firmware and live mailboxes cannot be
reclaimed until a verified relocation/parking and access-drain handoff.

## Automated SS0/SS1 DMA and NoC integration

The reusable synthesizable `rtl/adapters/soc_idma_engine.sv` is the exact
pinned upstream implementation used by the previously green isolated
`dv/dma/dma_tb.sv`. No second DMA engine implementation was created.
`tools/full_chip_gen.py` iterates configured compute subsystems and the
generated NoC endpoint manifest, attaches the engine to each
`m_<compute>_local_data_dma` and the CSR shim to
`s_<compute>_local_config_dma_regs`. No individual interface hookup is
required for each new compute instance.

`soc_dma_regs.sv` uses PULP `axi_to_axi_lite` and `axi_lite_regs`.
Only the 32-to-64-bit pointer staging, APB submission sequencer and
sticky interrupt status are locally implemented:

| Offset | Access | Meaning |
| --- | --- | --- |
| `0x00` | RW32 | Descriptor head bits [31:0] |
| `0x04` | RW32 | Descriptor head bits [63:32] |
| `0x08` | RW32 | COMMAND bit0: atomic submit; bit1: acknowledge IRQ |
| `0x0c` | RO32 | STATUS bit0: APB submission busy; bit1: IRQ pending; bit2: APB error; bit3: raw IRQ |

The `busy` status only tracks submission to upstream APB, **not full
descriptor-chain retirement**. Consumers must still wait for completion,
descriptor writeback and DMA idle before reclaiming shared SRAM.

`DmaEnable=0` is the default boot mode; `DmaEnable=1` instantiates real
DMA engines and CSRs. `DmaTestMode=1` is an explicit CPU0 AXI BFM simulation-only test mode
with CPUs held in reset. `make dv-chip-dma` writes DMA descriptor/payload
memory through CPU0's real AXI data NoC port, then programs each engine's
registers over the local/global configuration NoCs and verifies payload
through all local/global data NoCs and memory models. The CPU cold-boot
regression remains unpreloaded. **The integrated regression passed at [commit d2868045](https://github.com/r987r/xezim-hello-world/commit/d2868045b7d8ba3b6a687f9639efea1d5c87af9a)**, regardless of whether
`make gen` produces structurally connected RTL.

## AXI test-mode isolation and regression diagnostics

When `DmaTestMode=1`, the **CPU0 AXI BFMs (data/config)** temporarily drive CPU0's AXI
data/config NoC ports **only** after all CPU cores are held in reset. The
generator muxes the BFM requests onto those ports and explicitly returns
zero AXI responses to the inactive CPU adapters. This is required because
feeding CPU0 AXI BFM-issued B/R responses into a CPU-side width converter with no
matching requests violates the upstream `cc_rr_arb_tree` request invariant.

The first full-chip hardware run ([failed diagnostic run
41867680450](https://github.com/r987r/xezim-hello-world/actions/runs/41867680450))
reported exactly that upstream assertion after a successful 128-byte
SRAM write. The fix is real request/response ownership isolation, **not**
disabling assertions or changing third-party FlooNoC or AXI RTL. The
generator now has a regression assertion guarding this behavior. The subsequent [full-chip CI run 41885417960](https://github.com/r987r/xezim-hello-world/actions/runs/41885417960)
passed both engines, DMA chains, SRAM writebacks and IRQs using legal
minimum backend concurrency (two outstanding AXI transfers, no speculative
prefetch). The earlier failure is retained here as regression history.

The CSR command word is one-shot. While a submitted descriptor head waits
for APB acceptance, the hardware-loaded COMMAND byte stalls colliding
AXI-Lite submissions, rather than silently dropping a second head. This is
only front-end submission ordering; descriptor memory itself must still
remain allocated until transfer retirement.

## iDMA outstanding-depth legality regression (November 4, 2026)

The first conservative full-chip test tried `num_ax_in_flight: 1` and
immediately hit upstream `cc_stream_fifo_optimal_wrap.sv`'s mandatory
minimum depth of two. This is **not** a memory-model or NoC timeout;
it was an illegal parameter caught at time zero by upstream RTL in
[run 41881553547](https://github.com/r987r/xezim-hello-world/actions/runs/41881553547).
The generator now rejects any per-compute `num_ax_in_flight < 2` before
RTL build, the iDMA wrapper independently checks the same condition, and
the diagnostic profile uses `num_ax_in_flight: 2`,
`descriptor_prefetch: 0`, `buffer_depth: 3`. Retain the standalone
4-in-flight/4-prefetch reference. Passing at two outstanding transfers
will be a *smoke test*, not proof that higher-concurrency NoC behavior
is correct. Do not blame the independent LiteDRAM PR #13; this chip scope
still drives the bounded behavioral AXI RAM memory target.

## Regeneration and hardware CI provenance

The full-chip pipeline validates committed generated RTL before simulation.
Development history included a now-removed branch-push generator job
which could race its generated-file checks. The merged workflow follows
the project's PR-to-main/manual-dispatch policy: regenerate `gen/chip/`
from YAML in the same change as the source edits and require
`make check-config check-generated` in CI. Treat any stale generated file
as a failed source contract, not a DMA simulation result.
The corrected legal minimum of two outstanding transactions is checked
in three places: `config/soc.yaml`, `tools/full_chip_gen.py` and
`rtl/adapters/soc_idma_engine.sv`. The generated manifest and instantiated
RTL must agree with all three before any DMA traffic verdict is accepted.

The first source-only run following the fix, [41885042155](https://github.com/r987r/xezim-hello-world/actions/runs/41885042155),
failed the consistency contract against its older generated manifest.
The regeneration commit `4e4ed3b551454a73cacf63ad7ec1f0dadf3f82a7`
contains the updated two-entry parameter values. Hardware evidence must
come from a subsequent CI checkout of this or a descendant commit.

## Full-chip RTL acceptance (November 4, 2026)

**PASS:** [Full-chip CI run 41885417960](https://github.com/r987r/xezim-hello-world/actions/runs/41885417960)
on commit `d2868045b7d8ba3b6a687f9639efea1d5c87af9a`.
The `chip-dma` suite completed the smoke/stress sequence with **105 DMA
descriptors** (SS0 one DDR, SS1 four HBM, SS0 one hundred DDR) through the
generated local/global data and configuration FlooNoCs, checked payload
readback and descriptor writebacks, and acknowledged completion interrupts.
The CI report retained **1,902 accepted AXI observations**, plus transaction
reports and test artifacts. The default unpreloaded CPU cold boot, negative
boot and Xezim compile also passed in that run.

This *only* proves two DMA RTL engines in a host-assisted, CPU-reset
simulation against bounded AXI memory targets. The CPU0 AXI BFMs are not PCIe.
**Not yet verified:** CPU-executed DMA driver, CPU interrupt-service routines,
hardware SS0-to-SS1 doorbells, integrated LiteDRAM/physical DDR4 or HBM,
error-injection cases, or high-outstanding/prefetch performance. The integration is eligible to merge only after conflict resolution and the\ncombined-tree verification gates pass.
