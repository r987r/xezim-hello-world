# DMA bring-up foundation

**Current status:** Reusable descriptor allocation and host-side test-vector generation are implemented. Real iDMA RTL integration and AXI/IRQ simulation have **not** been completed or claimed to pass.

## Existing libraries and software

- Reuse pinned PULP iDMA with its descriptor frontend and generated AXI backend. Do not write another DMA engine.
- Reuse existing cocotb + cocotbext-axi drivers, AXI trace collection, and declarative regression framework.
- sw/dma/dma.h and dma.c provide a portable freestanding SRAM arena, 32-byte upstream descriptor construction, bounds checks and a release fence; no heap is required.
- dv/common/dma_vectors.py generates host-side deterministic descriptor chains, SRAM contents and independent AXI expected-data checks. tools/dma_vectors.py provides CLI generation.

## Local SRAM layout for DMA-only simulation

Each compute SRAM currently models only 16 KiB; the full architectural window is larger.

| SRAM offset | Purpose | Capacity |
| --- | --- | --- |
| 0x0000..0x0fff | Reserved CPU code/stack/mailboxes | 4 KiB |
| 0x1000..0x1fff | Contiguous 32-byte DMA descriptors | 128 entries |
| 0x2000..0x3fff | Source payload | 8 KiB |

100 descriptors x 64 bytes require 3,200 bytes of descriptors and 6,400 bytes of payload. Source and destination addresses derive from config/soc.yaml; bounds are checked against modeled capacities.

## Host validation commands

    python3 -m unittest discover -s tests -p 'test_dma_*.py' -v
    python3 tools/dma_vectors.py --count 100 --length 64 --out .tools/dma-vectors
    cc -std=c11 -Wall -Wextra -Werror -pedantic sw/dma/dma.c sw/dma/tests/test_dma.c -o /tmp/dma-sw-test
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
