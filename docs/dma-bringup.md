# DMA bring-up foundation

**Current status:** Reusable descriptor allocation and host-side test-vector generation are implemented. Real iDMA RTL integration and AXI/IRQ simulation have **not** been completed or claimed to pass.

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

The generator writes source_sram.hex in 64-bit readmemh word order, plus case.json with chain head and every independent expected payload. Successful generation alone is NOT a hardware DMA test.

## Real hardware bring-up sequence (pending)

1. Fetch pinned iDMA; generate upstream AXI backend and descriptor register RTL through its documented generation flow. Reuse the FlooNoC-compatible upstream AXI lock; do not mix divergent AXI dependency pins.
2. Instantiate the real descriptor frontend and AXI read/write backend in each compute subsystem. Arbitrate frontend descriptor-read and backend read/write managers into the existing DMA NoC port with correctly budgeted unique AXI IDs.
3. Connect the frontend's 64-bit APB submission/status registers to the 32-bit AXI-Lite CSR network via upstream bridges and narrow atomic staging/commit logic. Connect and verify IRQ.
4. Add an isolated cocotb DMA-only test with explicit host memory preload *before* DMA reset release; require actual descriptor AXI reads, actual payload AXI transactions, final IRQ, and independent readback from both local and remote memory models.
5. Extend the existing declarative regression for single, 100-descriptor, stalls, negative/SLVERR, timeout, interrupts, unaligned and repeated jobs; use existing AXI report timeline for all events.
6. Only after those pass: add a minimal CPU-side CSR/IRQ driver and a separate cold-boot-to-DMA integration test.

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
