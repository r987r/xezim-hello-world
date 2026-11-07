# PULP iDMA integration and memory ownership

The SoC uses the pinned PULP **desc64 iDMA frontend and generated AXI backend** with existing upstream AXI mux/join blocks. No custom DMA datapath or replacement AXI BFM is permitted. The standalone `dma-rtl`, dual-engine `chip-dma`, and real-CPU `chip-cpu-dma` regressions are **separate**.

## Selected execution modes

| Test | Actual initiator | Memory/verification scope |
| --- | --- | --- |
| `make dv-dma` | Cocotb writes real PULP descriptor frontend | Isolated AXI RAM targets, chain writeback and final IRQ |
| `make dv-chip-dma` | CPU-reset AXI BFMs initialize memory and program real iDMA CSRs | Both real DMA engines, Data/Config FlooNoCs, modeled DDR/HBM, passive AXI reports |
| `make dv-chip-cpu-dma` | PicoRV32 executes freestanding compiled C with bounded DMA-status polling | Actual CPU MMIO, iDMA, SRAM↔modeled DDR/HBM, independent AXI/checker evidence |
| `make dv-chip-ddr4-real` | Real CPU0 C and iDMA, separately selected | Pinned LiteDRAM RTL with behavioral DFI/BankModel, **not** physical PHY |

A BFM-initiated transfer is **not** CPU-originated. CPU interrupt service is not implemented; the CPU path polls STATUS. Dual concurrent CPU-directed DMA remains [#47](https://github.com/r987r/xezim-hello-world/issues/47).

## SRAM, descriptors and quiescence

`tools/sram_layout.py` defines allocation for both boot and DMA generators, and `sw/common/memory_pool.[ch]` and `tools/memory_plan.py` implement corresponding C/Python physical-memory bounds. In the CPU `boot_live` context, a 16 KiB SRAM reserves:

| Offset | Use |
| --- | --- |
| `0x0000–0x0fff` | Live firmware, CPU stack and mailbox |
| `0x1000–0x1fff` | Up to 128 32-byte DMA descriptors |
| `0x2000–0x3fff` | Payload storage |

`dma_only` is legal only in a *separate reset test* with all CPUs stopped; it can reuse the first 4 KiB for descriptors. Never preload writable SRAM in a cold-boot regression. Do not reuse descriptor storage or executable code until all outstanding transfers, descriptor writebacks, queues and CPU consumers are quiescent. Stock desc64 may overwrite descriptor header bytes with completion markers. Linked descriptors are **not** data-dependency barriers; release fences do not replace cache maintenance for a cacheful CPU.

The architectural DDR/HBM windows may exceed 4 GiB, but 32-bit CPUs cannot directly dereference them. DMA descriptors carry 64-bit physical addresses. Shared source/allocator YAML and C APIs must agree; do not copy target address math into each driver. See [memory allocation](memory-allocation.md).

## Generated RTL/CSR contract

`tools/full_chip_gen.py` attaches one real iDMA at each selected compute `m_<compute>_local_data_dma` endpoint and a register shim on the corresponding Config NoC. The `rtl/adapters/soc_dma_regs.sv` shim uses upstream PULP AXI4-to-AXI-Lite and register hardware:

| Offset | Access | Meaning |
| --- | --- | --- |
| `0x00` | RW32 | Descriptor head [31:0] |
| `0x04` | RW32 | Descriptor head [63:32] |
| `0x08` | RW32 | COMMAND submit bit 0; IRQ ACK bit 1 |
| `0x0c` | RO32 | STATUS APB busy/IRQ pending/APB error/raw IRQ |

HEAD is written as two 32-bit halves, followed by a release fence and one-shot COMMAND doorbell. STATUS busy means **APB submission**, not completed DMA chain; wait for writebacks and true DMA idle before reusing memory. The backend's `NO_ERROR_HANDLING` means APB STATUS error is not proof of downstream AXI fault handling.

`DmaEnable=0` is the cold-boot default, `DmaEnable=1` enables real engines, and `DmaTestMode=1` is a CPU-reset simulation mode with isolated CPU response paths. Never inject B/R responses into an inactive CPU width adapter. Conservative full-chip `num_ax_in_flight >= 2` satisfies upstream FIFO legality; passing at that budget does **not** establish high-outstanding performance.

## Reproduction and reporting

```sh
python3 -m unittest discover -s tests -p 'test_dma_*.py' -v
python3 tools/dma_vectors.py --count 100 --length 64 --out .tools/dma-vectors
make dv-dma
make dv-chip-dma
make dv-chip-cpu-dma
```

Vector generation and hosted tests validate address/data expectations, not real bus traffic. Only the tested RTL run's `result.json`, `test-flow.json`, passive `axi-transactions.json`, logs and independent data/descriptor checks can establish PASS. Full 100-descriptor performance, long backpressure, ISR and stress coverage require their own source-selected tests; see the [verification epic](https://github.com/r987r/xezim-hello-world/issues/34).
