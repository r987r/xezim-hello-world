# Physical-memory allocation and INIT/CHECK

One allocator implementation, `sw/common/memory_pool.[ch]`, backs the compatibility SRAM/DMA wrappers. `tools/memory_plan.py` predicts physical allocations independently; `tools/sram_layout.py` reserves firmware, mailbox, descriptor and data ranges. The **two SCN-2 CPU/BFM scenarios** share one typed source and memory plan; other legacy drivers are tracked under [#119](https://github.com/r987r/xezim-hello-world/issues/119) and are not assumed to execute the common action DAG.

## Execution and allocation rules

| Mode | Actual owner | Restrictions |
| --- | --- | --- |
| CPU | Real PicoRV32 firmware calls `soc_mem_*`, builds descriptors and programs DMA MMIO | No Python preload of boot SRAM, no CPU pointer to DDR/HBM above 4 GiB |
| BFM | Authorized Cocotb AXI initiator prepares SRAM and descriptors while CPUs are held in reset | BFM actions are **not** CPU C execution |
| Strict INIT/CHECK | CPU/DMA or AXI frontdoor transfer | Accepted protocol responses and actual bytes needed |
| Fast INIT/CHECK | Validated sparse-memory/backdoor access | **Not** AXI traffic and not usable for unknown RTL backing |
| Hybrid INIT/CHECK | Validated backdoor plus independently sampled frontdoor | Both paths and quiescence must be proven |

The default full-chip DDR/HBM stand-ins model bounded sparse AXI RAM, not their 1 GiB architectural windows. Modeled capacity and reserved low bytes come from the selected configuration. The real LiteDRAM variant has a separately bounded 32 MiB behavioral backing; no implicit RAM initialization is permitted.

Use `boot_live` with real executing CPUs. The distinct `dma_only` profile can reuse boot memory **only** in a separate reset run. Never release active descriptors, executable code or live mailbox storage. `soc_mem_alloc` validates power-of-two alignment/capacity and returns physical address, optional directly mapped SRAM pointer, generation and allocation token. `soc_mem_release` enforces LIFO retirement and rejects stale/double/free-order errors; a caller's quiescent flag is a precondition, **not** independent proof that DMA/CPU/AXI have drained. Cacheful systems also require cache maintenance.

```c
soc_mem_region_t hbm;
soc_mem_allocation_t allocation;
soc_mem_region_init(&hbm, "memory0.hbm0", SOC_MEM_HBM,
                    hbm_model_base + 0x100, hbm_model_bytes - 0x100, NULL);
bool ok = soc_mem_alloc(&hbm, 64, 64, &allocation);
/* allocation.cpu_ptr == NULL; allocation.phys can be a DMA destination */
```

## One pattern and memory service contract

`tools/memory_service.py` supplies explicit `initialize()`/`check()` operations with bounded chunks and seeded pattern recipes; allocation itself never initializes data. Matching `sw/common/memory_pattern.[ch]` and Python patterns implement counter8, constant and address_xor byte recipes against 64-bit physical addresses. Checkers reject uninitialized ranges rather than assuming zero.

`HostSparseMemory` supports the independently qualified host sparse storage used in NoC BFM tests; `AxiFrontdoor` wraps an **existing** authorized master. The host-sparse provider has a reciprocal frontdoor-write/backdoor-read and inverse/restoration test in the connected NoC flow. **Real tc_sram DPI, LiteDRAM DFI bank mapping, HBM hardware and a live CPU request/ack service are not equivalent providers** and remain under [#39](https://github.com/r987r/xezim-hello-world/issues/39). Never silently fall back to a different access method or reinterpret backdoor speed as hardware AXI throughput.

Pattern benchmarks must label source, bytes, seed, selected simulator, wall seconds, sim cycles, peak memory and method; `tools/memory_benchmark.py` produces a **synthetic** baseline, not an RTL/DPI speedup. Each actual protocol claim requires matching passive accepted AXI and independent bytes/descriptor checking.

## Reproduction

```sh
python3 -m unittest tests.test_dma_sw tests.test_memory_plan -v
make dv-memory-service
python3 tools/memory_benchmark.py --out .tools/benchmarks/memory.json
make dv-chip-cpu-dma
```

The CPU C/iDMA regression executes independently from the modeled-memory service and is not a claim of implemented CPU mailbox or hardware backdoor. See [DMA integration](dma-bringup.md) and [scenario evidence](scenario-memory-lifetimes.md).
