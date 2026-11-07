# Full-chip CPU and NoC boot contract

`gen/chip/soc_top.sv` composes PicoRV32 CPU0, SERV CPU1, local/global FlooNoC Data/Config fabrics, upstream Wishbone/AXI adapters, reset CSR, SRAM and memory target crossbar. `gen/supernoc/soc_noc.sv` is the shared generated NoC source; the standalone BFM and full-chip CPU scopes must not maintain duplicate routes.

**Default hardware:** `DmaEnable=0` proves real CPU cold boot with behavioral HBM/DDR memory targets. Opt-in `DmaEnable=1` generates actual PULP iDMA frontends/backends and Config-NoC submission CSRs. `DmaTestMode=1` holds CPUs in reset for legal host AXI-BFM preparation; **CPU0 C DMA** instead runs real compiled RV32I firmware with no active BFM on its response mirror. [Real DDR](../rtl/memory/ddr4/SOC_BRIDGE.md), [Ethernet](ethernet0-closure-gate.md) and [PCIe](pcie0-host-phases.md) are distinct opt-in variants, not already one combined test.

## Boot and CPU INIT/RUN/CHECK

CPU0 fetches immutable ROM, copies application words from **read-only flash** into initially uninitialized real SRAM model across its bus, releases CPU1 over MMIO reset control, and both execute from SRAM. Firmware comes from the generator's selected image/manifest, never writable-SRAM `$readmemh`. `tools/chip_bootgen.py` derives both firmware images, slot sizes, role binding and shared phase mailboxes from `config/soc.yaml`, rejecting unsupported addresses/roles.

| Phase | CPU0 coordinator | CPU1 | Independent requirement |
| --- | --- | --- | --- |
| INIT | Boot both cores, wait for ready/Config-NoC acknowledgement | Write ready | Every live core initialized before RUN |
| RUN | Authorize RUN, emit greeting, wait for all peers | Emit greeting from SRAM | Exactly expected per-core greeting |
| CHECK | Release CHECK, read peer greeting, wait for all acknowledgments | Check peer and acknowledge | CPU execution/peer checks and exact phase completion |

Greetings are source-checked signatures, **not** real UART output. Mailboxes are single-writer with no AMO/coherence or OS scheduler. Host BFMs never write CPU result words or forge boot phases.

## Shared SRAM, DMA and memory safety

`tools/sram_layout.py` and `sw/common/memory_pool.[ch]` keep active firmware, stack and mailboxes disjoint from descriptors/payloads. With CPUs executing, select `boot_live`. `dma_only` can reuse boot SRAM **only in a separate reset test**. DMA pools cannot retire before descriptor writeback, DMA idle, AXI drain and CPU quiescence.

The default chip boots with bounded AXI memory stand-ins at HBM/DDR architecture windows, not real DRAM. Invalid model capacity must return errors, never alias. The existing boot BFM probes modeled HBM/DDR through exposed legal verification ports after CPU coordination; the real CPU C mode checks modeled DDR/HBM by iDMA round-trip into CPU-visible SRAM. CPU cores are 32-bit and cannot directly load/store above 4 GiB.

The **real DDR variant** replaces only the selected DDR target with pinned LiteDRAM RTL and a behavioral DFI/BankModel, plus 16 KiB Config-NoC/Wishbone initialization. Its routed out-of-range negative requires DECERR without forwarding forbidden AW/AR to the controller, preserving in-range contents. Even this variant is not a physical DDR4 PHY or same-run Ethernet+PCIe interoperability proof.

## Protocol ownership and acceptance

`DmaTestMode=1` AXI data/config BFMs may drive CPU0 ports only when CPUs are held in reset and all inactive adapter responses are electrically isolated; otherwise false B/R ownership violates upstream AXI arbiter assertions. In **CPU C mode**, no active AXI BFM may attach to passive iDMA response mirrors. A separate DDR verification-only manager takeover may occur **only after** real CPU/iDMA CHECK and all responses drain, to test controller aperture DECERR.

Use the pinned upstream adapters: SERV `wbm2axilite`, PULP `axi_lite_mux`/`axi_lite_demux`, `axi_lite_to_axi`, `axi_to_axi_lite` and PULP `axi_to_detailed_mem`/`tc_sram`. The SRAM/model memory and reset register versions must agree with the selected variant source and NoC IDs. Source topology is not protocol evidence; require actual accepted bus handshakes, exact bytes, CPU signatures, bounded timeouts and named expected failures.

## Reproduce

```sh
make gen
make check-generated
make dv-chip
make dv-chip-dma
make dv-chip-cpu-dma
make dv-chip-ddr4-real
python3 tools/regress.py chip-boot-negative
```

The real CPU C-DMA path uses **bounded status polling**, not an interrupt handler. The negative CPU boot test must fail for the named missing-init acknowledgement, not a generic compile failure. Xezim's chip profile is structural compilation rather than complete routed CPU/NoC traffic. Keep simulator/variant-specific `plan.json`, `identity.json`, logs, XML, passive `axi-transactions.json` and `result.json` together; do not reuse an old SHA's PASS for current RTL. See [verification scopes](verification.md) and [combined test acceptance](multiprotocol-integration-readiness.md).
