# Standalone CPU cold boot and SRAM contract

The independent `make dv-boot` test runs actual PicoRV32 (CPU0) and SERV (CPU1) instruction execution through a **minimal bootstrap bus/memory model**, not the full FlooNoC chip. The real SoC variant uses the separate [full-chip boot](full-chip-boot.md) NoC/AXI assembly. The primary boot CPU is an existing compute core; no separate management CPU is required.

## Exact boot sequence

1. Reset holds CPU1 while PicoRV32 starts at immutable ROM `0x00000000`.
2. ROM copies four RV32I instruction words per CPU from a *read-only modeled flash* at `0x20000000` (secondary slot `0x20000100`) into **uninitialized** `compute0.sram` `0x10000000` and `compute1.sram` `0x11000000`. Both CPU memories are modeled with **16 KiB** backing inside the architectural 1 MiB SRAM windows; accesses outside backing fail.
3. CPU0 writes the real reset-control MMIO at `0x40020000`, releasing SERV at its configured SRAM reset PC.
4. Both execute from SRAM and write checked completion signatures (CPU0 `0x10000100=0x55`, CPU1 `0x11000100=0x66`). Missing ROM/flash reads, SRAM stores, release or CPU signatures fail the checker.

Only ROM/flash may use initialization files. This **cold boot never preloads writable SRAM**. The stand-alone bootstrap is a simple memory model, not a silicon SRAM macro, QSPI controller, secure boot or HBM/DDR initialization. Those require their own selected hardware tests.

The generator derives instruction images, listings, reset address and memory-map constants from `config/soc.yaml` into `gen/boot/`. Unsupported boot policies, wrong image size or overlaps fail before simulation. The relocated profile `boot-relocated` selects SRAM0 `0x12000000`, SRAM1 `0x13000000`, flash `0x21000000` and reset CSR `0x41020000` in its **per-run generated variant**, not by hand-editing tracked RTL.

## Regression commands

```sh
make gen
make check-generated
make dv-serv
make dv-boot
python3 tools/regress.py boot-relocated
make dv-chip     # distinct full-chip connected FlooNoC and CPU phase test
```

`make dv-serv` proves standalone instruction execution. `make dv-boot` proves bus-driven ROM→SRAM cold boot and actual two-core signatures. `make dv-chip` adds generated Data/Config NoCs, upstream AXI/SRAM, CPU0 phase coordination and separately selected optional iDMA. Do not combine their results into one hardware PASS.

## Hardware limits

The standalone decoder `rtl/interconnect/boot_local_decode.sv` is a one-hot unmapped-access checker; `rtl/memory/local_sram.sv` is a reusable dual-port RTL SRAM model with registered SERV reads and byte strobes, not a silicon macro. The SoC remains non-cache-coherent; future caches, clock domains, real flash transport and secure boot require synchronization, verified loader integrity and reset/recovery design.

The 32-bit CPU cannot directly dereference the configured DDR/HBM windows above 4 GiB. iDMA can carry 64-bit physical addresses in a separate descriptor/Config-NoC path. CPU ISR service and real controller/PHY integration are not implied by a boot pass. See [memory allocation](memory-allocation.md), [DMA](dma-bringup.md) and [simulator compatibility](simulator-compatibility.md).
