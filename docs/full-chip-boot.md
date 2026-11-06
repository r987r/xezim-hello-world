# First chip boot configuration

`gen/chip/soc_top.sv` assembles the actual PicoRV32 coordinator, SERV
secondary CPUs, all configured local/global FlooNoCs, upstream protocol
adapters, reset registers, SRAM and memory target crossbar. The shared
`gen/supernoc/soc_noc.sv` is also instantiated by the existing BFM test;
there is one source of NoC wiring and one architecture picture.

The same configuration-driven `soc_top` now has two modes. Default
`DmaEnable=0` retains CPU cold boot without writable SRAM preload;
`DmaEnable=1` instantiates one real PULP iDMA frontend/backend per
configured compute, and replaces each `dma_regs` error target with upstream
AXI-to-Lite/register blocks and a 64-bit APB head/doorbell adapter. DMA data
traverses the local/global FlooNoCs, and control writes traverse the
configuration NoCs. The **opt-in CPU C DMA variant**, `make dv-chip-cpu-dma`, runs the
real PicoRV32 using the existing ROM-to-SRAM cold-boot INIT/RUN/CHECK
checker, with two real DMA engines enabled. C is compiled by LLVM into
the modeled read-only flash and uses the common SRAM/DDR/HBM allocator
and desc64 MMIO driver. It checks remote DDR/HBM contents by DMA-copying
them back into local SRAM. The same AXI monitors/reporting are used.
This scenario **passed** the real Verilator full-chip gate ([CI 41933332567](https://github.com/r987r/xezim-hello-world/actions/runs/41933332567), 39,150 AXI observations), and uses bounded STATUS polling rather than CPU interrupt-service firmware.
No independent CPU testbench or backdoor SRAM initialization is added.

The separate `full_chip_dma_tb` holds CPUs in reset
and uses **CPU0 AXI BFMs** (data/config, cocotb simulation-only) to initialize DMA SRAM and start transfers
via 32-bit CSRs; that is NOT a CPU firmware or cold-boot test. Hardware IRQ
pending/status are exposed to the verification framework, but CPU IRQ
service software and physical memory controllers/PHYs remain pending.

## Shared SRAM ownership policy

`tools/sram_layout.py` now supplies the same physical region contract to
the cold-boot firmware generator and DMA test vector builder. Cold boot uses
`boot_live`: executing SRAM firmware, CPU coordination mailboxes and DMA
areas do not overlap. The minimal RV32I boot firmware is still generated
and executed on the actual CPUs, **not** linked against the new C library.
`sw/common/memory_pool.[ch]` is the shared SRAM/DDR/HBM physical-region allocator; `sram_pool` and the DMA descriptor routines reuse it. CPU0's compiled RUN application actually allocates buffers and descriptors with this contract; the minimal ROM/SRAM boot coordinator remains generated RV32I. The `dma_only` profile can reuse
boot space only in a **separate** reset-and-preload regression with CPUs
stopped; no cold SRAM in this scope may be backdoor-preloaded.

## Firmware and coordination

CPU0 alone boots from immutable ROM and reads flash. Its real bus stores
copy each application into initially uninitialized SRAM, clear coordination
mailboxes, and release the secondary CPUs through the reset-control CSR.
The SRAM target is upstream `tc_sram` with `SimInit="none"`; an initialization
file on a writable SRAM instance is rejected. Only ROM and flash use files.

| Phase | Coordinator | Each secondary | Checker |
| --- | --- | --- | --- |
| init | Wait for every CPU's ready mailbox and remote configuration acknowledgement | Write ready and acknowledge through the configuration NoCs | All ready before RUN |
| run | Publish RUN; write its greeting; wait for every greeting | Wait for RUN and write its own greeting | Exactly the expected per-CPU greeting in RUN |
| check | Publish CHECK; read a peer's greeting; wait for all check acknowledgements | Wait for CHECK, read a peer's greeting and acknowledge | Every CPU executed SRAM code and checked a peer before coordinator completion |

The initial application work is a hello-world signature, decoded in the
test log as `hello world from CPU<n>`. It is **not UART output**. Phase work
can be replaced later while keeping this coordination contract. The host
never writes CPU ready, hello, check or completion values.

Mailboxes use per-CPU single-writer words. There are no AMO instructions,
hardware barriers, OS scheduler or assumed cache coherence. The selected
cores serialize their bus operations and have no instruction/data caches.
Adding caches or a less strongly ordered CPU requires a reviewed memory
ordering/barrier implementation.

`tools/chip_bootgen.py` is small, project-specific RV32I bootstrap firmware
generation using the existing instruction encoders. Its assembly listings,
32-bit expected application words, 64-bit ROM/flash files and firmware
manifest are generated together. Addresses, CPU instances, coordinator and
slot/SRAM capacities derive from `config/soc.yaml`. Barrier loops avoid
unrolled per-CPU firmware growth; the generator rejects unsupported CPU
roles or images outside their slots. Firmware generation checks 2..16 cores;
that is not a claim of RTL execution at every size.

## Reused framework and IP

[Snitch Runtime](https://pulp-platform.github.io/snitch_cluster/ug/tutorial.html)
provides startup, core identity, synchronization and examples for Snitch
clusters. [PULP Runtime](https://github.com/pulp-platform/pulp-runtime) is
another useful platform runtime. Neither is a drop-in BSP for this
PicoRV32/SERV pair: Snitch/PULP-specific CSRs, hardware barriers, ISA features
and platform services need a port. We do not claim an unmodified runtime port.

The initial host framework is upstream **cocotb**: one test observes
init/run/check completion and uses upstream **cocotbext-axi** at the explicit
verification manager port. A single SV boot checker is shared with the
Xezim bench. This keeps the bootstrap small while establishing real CPU
coordination before introducing a larger C runtime/toolchain.

| Boundary | Reused implementation | Local glue |
| --- | --- | --- |
| SERV classic Wishbone to AXI-Lite | Pinned Apache-2.0 [ZipCPU `wbm2axilite`](https://github.com/ZipCPU/wb2axip/blob/2e8d3bc2d26ddc33d1881022a2a2b9d3f0c16b9b/rtl/wbm2axilite.v) | Submit each held classic request once |
| SERV instruction/data arbitration | PULP `axi_lite_mux` | Port/type wiring |
| CPU data/config selection | PULP `axi_lite_demux` | Configuration aperture classification |
| AXI-Lite to AXI4 and 32-to-64-bit data | PULP `axi_lite_to_axi`, `axi_dw_converter` | Struct/port wiring and address extension |
| Reset CSR | PULP `axi_to_axi_lite`, `axi_lite_regs` | Reset-bit hookup |
| SRAM/ROM/flash/temporary memory targets | PULP `axi_to_detailed_mem` and `tc_sram` | Bounded address window, read-only/file policy, memory handshake wiring |
| Memory target selection | Existing pinned Verilog-AXI `axi_crossbar` | One local-NoC output to the configured targets |

The NoC currently converges to **one** `target_crossbar` endpoint, so the
chip crossbar has one input and two outputs. The older standalone memory
test remains a separate 2×2 stress scope. Both global memory ingress paths
remain connected to the memory-local NoC.

## Temporary HBM/DDR stand-ins

`verification.full_chip_boot.memory_model: axi_to_mem_tc_sram` explicitly
selects upstream AXI slave SRAM stand-ins for this scope. Each implements
the bounded capacity selected by `verification.memory.model_address_bits`
(currently 64 KiB) within its architectural window, with no address wrapping.
Out-of-range and ROM/flash write requests return errors. Physical memory
initialization, timing, refresh, controller registers and PHYs are not modeled.

After CPU coordination succeeds, the upstream AXI verification manager
writes distinct burst data into both HBM/DDR windows, applies a partial write,
then reads both back. Distinct data checks that the targets are independent.
Read and write responses must be OKAY; accesses just beyond each model's
capacity must return SLVERR rather than alias valid storage.
The default cold-boot test still uses a BFM at the inactive DMA boundary.
**During real CPU C-DMA execution no active AXI master may attach to its
mirrored iDMA probe pins**, because it would consume real iDMA responses.
The opt-in DDR-B regression adds a distinct, RTL-gated exception **only
after the real CPU/iDMA CHECK phase completes and controller requests drain**:
a verification-only AXI master exclusively takes over the compute0 DMA NoC
manager port to check routed DDR aperture DECERR and nonalias. Ordinary
CPU-DMA, Ethernet and PCIe runs do not enable this takeover.
The separate `make dv-chip-dma` test instead uses both real PULP iDMA
engines over the same NoCs with CPUs held in reset. These are distinct scopes.
The CPUs remain 32-bit and cannot directly address the windows above 4 GiB.

### Opt-in real LiteDRAM path (DDR-B)

The default `chip-boot`, `chip-cpu-dma` and PCIe tests above **retain**
AXI RAM models. The separate `chip-ddr4-real` variant dynamically
generates the pinned LiteDRAM controller and behavioral DFI/BankModel
behind Memory0's existing Data NoC crossbar, enables a 16-KiB Config NoC
Wishbone/DFII initialization path, and holds CPU0 in reset until real
DDR init completes. The same compiled CPU0 C/iDMA INIT/RUN/CHECK software
copies SRAM→DDR→SRAM and verifies byte contents. The real-controller
[CI #42217902632](https://github.com/r987r/xezim-hello-world/actions/runs/42217902632) passed with DFI/model-bank and
AXI completion evidence. This is simulation-controller integration,
**not** a physical DDR PHY or a combined Ethernet/PCIe DDR test.

## Commands and acceptance

```bash
make gen
make dv-chip
make dv-chip-dma
make dv-chip-cpu-dma  # default modeled DDR/HBM + actual CPU0 C DMA
make dv-chip-ddr4-real # opt-in pinned real LiteDRAM RTL + behavioral DFI
python3 tools/regress.py chip-boot --stage files
python3 tools/regress.py chip-boot --stage run  # requires matching built RTL
python3 tools/regress.py chip-boot-negative
```

The positive gate requires real ROM/flash reads, exact application-word
copies before release, SRAM instruction fetches from every CPU, ordered
phase/greeting/check acknowledgements and the coordinator's completion.
The host also requires HBM/DDR model readback and nonempty passing cocotb XML.
The negative case holds a secondary in reset and must fail with the exact
missing-init-acknowledgement diagnostic. A generic compile error or timeout
does not satisfy its expected-failure rule.

Verilator executes the complete test. The YAML Xezim chip gate is currently
**structural compilation**, separately logged; a compile pass is not a
multicore functional pass. Keep both simulators and retain diagnostics.
Build plans, filelists, logs, XML and result JSON are under
`.tools/regression/chip-*/` and retained by the full-chip CI workflow.

The cocotb run owns the clock and reset so upstream AXI BFMs and RTL agree
on each handshake edge. The standalone Xezim bench uses its own SV clock/reset.
Do not enable both clock drivers: an internally timed Verilator clock can
race a VPI BFM and advance a burst beat before the RTL accepts it.
