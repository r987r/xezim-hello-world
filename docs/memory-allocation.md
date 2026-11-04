# Unified physical-memory allocations for SoC verification

The single allocator is `sw/common/memory_pool.[ch]`. Existing
`soc_sram_pool_*` and `soc_dma_arena_*` APIs are compatibility wrappers
around the same implementation, **not independent bump allocators**.

## One test framework, two execution adapters

The test scenario, memory regions, expected contents, INIT/RUN/CHECK
lifecycle and AXI correlation are common. **CPU and BFM are modes of
execution, not independently maintained test definitions or scoreboards.**
The existing `dv/common/dma_vectors.py` BFM fixture now obtains DDR/HBM
physical target windows from the same `tools/memory_plan.py` used to
predict allocations for CPU mode; `tools/sram_layout.py` remains the
shared boot-live/dma-only SRAM placement contract.

- `cpu`: Only real boot copies firmware to cold SRAM. Compiled C must call
  the shared `soc_mem_*` allocator, build descriptors and program the
  existing DMA CSR over the real configuration NoCs. Python observes and
  checks; it must not preload or masquerade as the CPU.
- `bfm`: The same scenario's intended regions, descriptor ABI and golden
  payloads are prepared by cocotb AXI agents via actual NoC transactions
  for quicker isolated/integration debugging. The CPU is held in reset.
- Both: Use the same passive AXI monitors and report generator to validate
  accepted request/response handshakes and independent memory readback.

Keeping an isolated RTL bench and a full-chip boot bench is deliberate
verification *coverage*, not a second memory allocator or architecture.
The existing compiled C run-hook file is **not wired into a runnable SoC
regression** yet. No full-chip CPU-executed C DMA claim is made without a
cross-compiler, linked image, loaded immutable flash, execution and
observed DMA traffic. Do not merge based on hosted tests alone.

## Two coordinated contexts

| Context | Responsibility | What it must not do |
| --- | --- | --- |
| Python `tools/memory_plan.py` | Derive allocatable physical windows from `config/soc.yaml` and `tools/sram_layout.py`, reserve predicted buffers with owner/phase/token metadata, validate observed CPU allocations | Implicitly initialize cold SRAM, assume an allocation happened just because a plan exists, or use architectural capacity when model storage is smaller |
| Freestanding C `soc_mem_*` | Reserve actual physical buffers in SRAM, DDR or HBM, return a 64-bit DMA address, provide CPU pointer only for mapped SRAM, release/reuse on quiescence | Invent MMU mappings, directly dereference >4-GiB DDR/HBM from a 32-bit core, free active DMA memory |

The Python plan is an **independent prediction**. In a future CPU-executed
test, the checker must compare CPU-produced addresses against the plan and
correlate the real accepted AXI read/write handshakes. It must never
interpret an allocated Python address as a completed hardware allocation.

Configured `boot_live` SRAM regions remain separate from firmware, stack,
and live coordination mailboxes. The distinct `dma_only` profile may
reuse former boot space only with all CPUs held in reset; it is forbidden
during real CPU boot. Full-chip DDR/HBM currently use **64-KiB behavioral
AXI memory stand-ins** even though architectural apertures are larger;
the Python planner bounds allocations by model capacity and reserves the
first 256 bytes to avoid colliding with existing low-address BFM cases.
The platform-specific C initialization receives those same physical
region bounds. Neither the allocator nor the planner instantiates memory.

## Allocation and release

`soc_mem_region_init` binds kind, base, capacity, and an optional mapped
SRAM pointer. `soc_mem_alloc` validates power-of-two alignment and
capacity; it returns physical address, optional CPU pointer, generation,
and unique monotonic allocation token. `soc_mem_release` allows **LIFO
retirement** only and rejects stale, double, and out-of-order frees.
`soc_mem_reset` invalidates outstanding handles by generation.

C APIs return `false` unless the caller attests that all consumers
are quiescent. This boolean is a **precondition, not a hardware proof**:
future CPU tests must wait for DMA completion, descriptor writeback,
engine idle, AXI drains, and all CPU accessors before setting it.
Persistent firmware, stacks and mailboxes remain reserved. Cacheful CPUs
will also need explicit cache clean/invalidate; current cores are
cacheless. The current iDMA backend uses NO_ERROR_HANDLING, so APB CSR
errors do not prove downstream AXI transfer error handling.

A minimal example for a CPU which cannot map HBM:

```c
soc_mem_region_t hbm;
soc_mem_allocation_t result;
soc_mem_region_init(&hbm, "memory0.hbm0", SOC_MEM_HBM,
                    hbm_model_base + 0x100, hbm_model_bytes - 0x100, NULL);
bool ok = soc_mem_alloc(&hbm, 64, 64, &result);
/* result.cpu_ptr == NULL; result.phys can be a DMA descriptor dst */
```

The address and modeled capacity must come from the configuration-generated
platform contract, not a hardcoded value in reusable firmware. Real
CPU-driven tests must use `boot_live` and retain the existing INIT/RUN/CHECK
and passive NoC AXI monitoring. **Current tests cover the hosted C
allocator and Python virtual plan; C execution by the RTL CPUs is still
a separate required gate.**

## Regression

```sh
python3 -m unittest tests.test_dma_sw tests.test_memory_plan -v
make check-config
make dv-chip
```

The host C tests compile `memory_pool.c`, the SRAM compatibility API,
and `dma.c` in one binary. Python tests cover mapped/modeled sizes,
64-bit HBM/DDR addresses, relocation, overflow, alignment, reclaim,
and disjoint boot/DMA memory regions.
