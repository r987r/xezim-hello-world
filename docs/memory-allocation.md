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
The opt-in `make dv-chip-cpu-dma` regression is now wired into the
shared real-CPU boot. `tools/cpu_dma_firmware.py` compiles a freestanding
RV32I C app, places it in the modeled immutable flash and calls it from
CPU0 RUN. The same passive monitors validate DDR/HBM roundtrip traffic.
**This is implemented, not yet CI-verified**; do not merge based on
hosted C allocator tests alone.

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
and passive NoC AXI monitoring. **Hosted allocator, Python plan and independent BFM tests are distinct
from the opt-in real-CPU C DMA RTL gate; its completion must be verified
from CI before claiming a pass.**

## Regression

```sh
python3 -m unittest tests.test_dma_sw tests.test_memory_plan -v
make check-config
make dv-chip-cpu-dma    # real CPU C firmware, real DMA RTL, shared AXI monitors
make dv-chip            # includes CPU DMA and all original chip gates
```

The host C tests compile `memory_pool.c`, the SRAM compatibility API,
and `dma.c` in one binary. Python tests cover mapped/modeled sizes,
64-bit HBM/DDR addresses, relocation, overflow, alignment, reclaim,
and disjoint boot/DMA memory regions.

## Memory initialization/check backends and benchmarks (next increment)

**Same scenario and allocation handles, no separate test frameworks.**
Initialization/verification is a distinct operation from allocation. Record
a compact pattern recipe instead of creating a full DDR/HBM binary image:

- \`init(region, offset, bytes, pattern, seed, policy)\` and
  \`check(region, offset, bytes, pattern, seed, policy)\` are scenario-level
  operations; C/CPU and Python BFMs consume the same recipe bytes.
- \`strict\`: CPU/DMA or AXI frontdoor initializes/checks actual hardware.
  A mandatory small strict smoke catches missing routing/CPU behavior.
- \`fast\`: validated direct host sparse-memory or simulator backdoor
  initialize/check; **does not count as AXI traffic**.
- \`hybrid\`: large payload via validated backdoor, CPU builds descriptors
  and submits real DMA; sampled frontdoor reads plus independent full
  backdoor compare. Prefer this for large routine regressions.
- CPU mode may request acceleration through a simulation-service mailbox,
  but must wait for a simulator acknowledgement before consuming the data.
  In no-CPU mode Python calls the same provider directly.
- Backdoor adapters are explicitly per backing type: cocotbext-axi
  SparseMemoryRegion; PULP \`tc_sram\` RTL; DDR4 controller/DFI bank model;
  and future HBM. Do not patch pinned IP or invent generic DPI paths.
  Validate every provider against frontdoor writes/readback first.
- Cold boot ROM/flash initialization remains intentional, and writable
  SRAM never receives an implicit preload. An unwritten region has no
  implicit expected-zero contents; checks must specify initialization.
- Descriptors require explicit ABI serialization from allocated addresses;
  payload may use small deterministic patterns or a reproducible seed.

Keep benchmarks even after the fast path is default. For **identical
scenario/seed/size/RTL and simulator**, report separate INIT and CHECK
wall-clock seconds, cycles, transferred bytes, host peak RSS and speedup
vs strict. Do not attribute faster backdoor writes to AXI bandwidth or
latency. Report the access method and backing model in every run artifact.
Minimum reference sweep: 64 B, 4 KiB, 64 KiB and the largest supported
modeled size, with \`strict\`, \`hybrid\`, \`fast\`. Mark unsupported method/
backing combinations explicitly instead of silently falling back.

## Common memory INIT/CHECK service (incremental)

The new tools/memory_service.py reuses physical-region allocations from tools/memory_plan.py.
Allocation NEVER implicitly initializes memory. Explicit initialize() and check() accept
a deterministic Pattern and bounded chunk size. An initialized-range tracker rejects
checks of untouched bytes. Events separately record INIT/CHECK wall time, method,
bytes and optional simulator cycles.

| Policy | INIT | CHECK | Requirements |
| --- | --- | --- | --- |
| strict | CPU / AXI frontdoor | CPU / AXI frontdoor | Explicit authorized initiator |
| fast | Verified backdoor | Verified backdoor | Cross-checked backing mapping |
| hybrid | Verified backdoor | Full backdoor and sampled frontdoor | Both paths |
| auto | Fastest validated method | Same | Fails if no validated access |

HostSparseMemory reuses cocotbext-axi sparse storage without custom RTL;
AxiFrontdoor wraps an EXISTING authorized BFM without attaching one.
CombinedMemoryProvider must pass quiescent two-way frontdoor/backdoor
consistency and scratch-restoration checks before enabling fast/hybrid.
Do not attach an active AXI BFM to CPU-DMA mirrored response signals.
These Python providers do not yet implement a PULP tc_sram DPI backdoor,
the LiteDRAM/DFI bank mapping, or a live CPU simulation-service mailbox.
Those require separately reviewed adapters and RTL tests.

The matching sw/common/memory_pattern.[ch] and Python Pattern use byte-identical
counter8, constant and address_xor recipes with a 32-bit seed and 64-bit physical
addresses. C fills/checks only CPU-visible bytes; it never dereferences HBM/DDR.

### Benchmarks

Run python3 tools/memory_benchmark.py --out .tools/benchmarks/memory.json
for the current synthetic interface baseline at 64 B, 4 KiB and 64 KiB.
The JSON source is synthetic_bytes_not_rtl. Do NOT call these values measured
RTL/DPI/AXI speedups. Real provider benchmarks will collect equal-case INIT
and CHECK wall time, simulator cycles, host RSS, access method and AXI traffic.
Strict frontdoor tests remain mandatory even when fast/hybrid becomes default.
