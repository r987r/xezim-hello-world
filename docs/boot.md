# Boot, local SRAM, and CPU bring-up contract

This project uses **one of the existing compute CPUs as the primary boot
processor**. We do not need a separate management CPU for the initial SoC.
This follows the common staged-boot model: immutable ROM -> firmware image in
nonvolatile storage -> on-chip SRAM -> additional cores. A future independent
management/security processor is an optional *replacement*, not a prerequisite.

## Actual cold-boot test (`make dv-boot`)

1. Reset holds **SERV / compute1** while **PicoRV32 / compute0** is released.
2. CPU0's `PROGADDR_RESET=0` selects the immutable **Boot ROM** at `0x0`.
3. The boot ROM executes real RV32I loads from a **read-only flash model** at
   `0x20000000`. In simulation only, the ROM and flash models are initialized
   from `gen/boot/bootrom.hex` and `gen/boot/flash.hex`.
4. CPU0 copies four words of its program into previously blank `compute0.sram`
   at `0x10000000`, then four words for SERV into `compute1.sram` at
   `0x11000000` (second flash slot begins at `0x20000100`). **No SRAM
   `$readmemh` is used.** The stores are real PicoRV32 AXI4-Lite transactions.
5. CPU0 writes `1` to the implemented **boot reset-control MMIO register** at
   `0x40020000`. Only then does SERV come out of reset, with its reset PC
   configured as `0x11000000`.
6. CPU0 jumps to its SRAM program. Each real CPU executes a four-instruction
   program and writes a completion signature to its SRAM (`0x10000100=0x55`,
   `0x11000100=0x66`). The test rejects missing ROM fetches, flash reads,
   SRAM copy stores, premature CPU1 acknowledgment, missing signatures,
   or failure to execute CPU0's SRAM image.

**Scope boundary:** The boot scope contains real CPU RTL and real CPU bus
transactions, but uses a **minimal standalone memory-mapped bootstrap bus
model** for SRAM/ROM/flash and SERV's instruction/data ports. It is *not* the
full-chip FlooNoC or PULP AXI implementation, not a SPI/QSPI controller, and
not HBM/DDR initialization. The 16-KiB-per-CPU **boot test SRAM model limit**
is explicit: accesses outside this implemented capacity fail instead of
wrapping within the 1-MiB architectural SRAM windows.

The tiny RV32I images are generated deterministically from `config/soc.yaml`.
`gen/boot/bootrom.lst` and `flash.lst` document each emitted instruction and
address for code review; `gen/boot/manifest.json` states the addresses,
image sizes, reset policy, completion signatures and model limitations.
`make gen` removes obsolete image files, and `make check-generated` catches
drift.

## Minimal bring-up ladder

1. Run `make dv-serv`: one real SERV core, one small synchronous Wishbone
   RAM, and a four-word RV32I test with a checked data store.
2. Run `make dv-boot`: CPU0 executes Boot ROM, reads flash, writes both blank
   SRAMs, releases CPU1 via reset MMIO, and requires **both** CPU signatures.
3. Only after that integrate local AXI/AXI-Lite fabrics and the real
   programmable PULP iDMA.

Xezim 0.11.4 uses unmodified upstream SERV RTL. The prior compatibility
workaround and the independent regression are documented in [boot-debug.md](boot-debug.md).

## Why there is no prefilled ASIC SRAM

ASIC SRAM macros are normally volatile; their power-on contents must not be
assumed. Firmware arrives from a *nonvolatile* boot device (SPI/QSPI NOR,
eMMC, SD, on-die ROM/flash, host JTAG/UART, etc.) through a boot ROM and
software or hardware copy path. FPGA BRAM may alternatively receive an
initial image at bitstream configuration, but that is a different boot mode.

A simulator's `$readmemh` can legitimately initialize ROM/flash **because
those stand in for persistent boot storage**. Preloading SRAM in a simulation
is also useful for bypass/accelerated tests, but such tests must be labeled
`preloaded` and cannot count as a cold-boot proof.

## Map and security decisions

| Region | Address | Width | Current implementation |
| --- | --- | --- | --- |
| Boot ROM | `0x00000000` | read-only 32-bit | RV32I ROM, loaded from generated hex |
| Local SRAM0 | `0x10000000` | R/W 32-bit | volatile 16-KiB modeled subset of 1-MiB window |
| Local SRAM1 | `0x11000000` | R/W 32-bit | volatile 16-KiB modeled subset of 1-MiB window |
| Boot flash | `0x20000000` | read-only 32-bit | immutable model backing flash slots |
| DMA0 CSR | `0x40000000` | AXI4-Lite | **planned**, no register bank yet |
| DMA1 CSR | `0x40010000` | AXI4-Lite | **planned**, no register bank yet |
| Reset control | `0x40020000` | R/W 32-bit | **implemented only in scoped boot TB** |
| HBM data | `0x1_00000000` | AXI4 64-bit | behavioral AXI RAM in separate memory DV |
| DDR data | `0x1_40000000` | AXI4 64-bit | behavioral AXI RAM in separate memory DV |

We removed invented HBM/DDR controller CSR windows. Those registers should be
allocated only after choosing a real controller and specifying its actual
management interface. CPU0 and CPU1 are 32-bit cores and **cannot directly
load/store addresses above 4 GiB**; later DMA engines will have 64-bit
source/destination registers for transfers to HBM/DDR.

The bootstrap model supports aligned, full-word transfers only. Future boot
ROM implementation should check a firmware container header, lengths,
checksums/authentication, failures, timeouts, image placement, and reset
permissions. Secure boot is **not implemented**.

## Next hardware integration

1. Replace direct boot-memory address mux with a local AXI interconnect and
   byte-enabled SRAM macro/model; connect a Wishbone-to-AXI adapter for SERV.
2. Add a minimal SPI/QSPI reader or a debug/UART streaming boot interface;
   keep exactly the same image/load, reset and completion contracts. Test
   *traffic-driven* SRAM loading (no SRAM backdoor preload in cold boot).
3. Integrate PULP iDMA frontend CSRs: CPU0 programs source, destination,
   length, status and interrupt. Accelerate future firmware staging/copies.
4. Implement global data/config networks. CPU0 coordinates memory-controller
   initialization and waits for DDR/HBM ready before issuing DMA there.
5. Release the secondary core through controlled, addressable reset with
   error handling. Add optional secure management processor only if isolation,
   always-on power domains, or recovery requirements justify it.

The system remains intentionally **non-cache-coherent** for now. Once caches
are added, DMA/shared-memory synchronization and cache maintenance must be
specified and verified, not assumed.
