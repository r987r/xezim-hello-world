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
4. CPU0 copies four words of its program into previously uninitialized `compute0.sram`
   at `0x10000000`, then four words for SERV into `compute1.sram` at
   `0x11000000` (second flash slot begins at `0x20000100`). **No SRAM
   `$readmemh` is used.** The stores are real PicoRV32 AXI4-Lite transactions.
5. CPU0 writes `1` to the implemented **boot reset-control MMIO register** at
   `0x40020000`. Only then does SERV come out of reset, with its reset PC
   configured as `0x11000000`.
6. CPU0 jumps to its SRAM program. Each real CPU starts its four-word
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
drift. `gen/boot/boot_config_pkg.sv` binds the same YAML addresses to SERV's
reset PC, both memory-model decoders, SRAM sizes and the bench's fetch/copy
checks. No executable address defaults are relied on by the boot bench.

`python3 tools/regress.py boot-relocated` runs this same bench with SRAM0
at `0x12000000`, SRAM1 at `0x13000000`, flash at `0x21000000`, and reset
control at `0x41020000`. The runner validates and emits the variant's
package and firmware under its result directory, then supplies only ROM/
flash image paths via plusargs. SRAM remains uninitialized. Both default
and relocated boots are required in the YAML `xezim` suite. ROM reset PC
zero, four-word programs, 256-byte slots and 16-KiB model SRAM remain
explicit supported limits; other values are rejected.

## Minimal bring-up ladder

1. Run `make dv-serv`: one real SERV core, one small synchronous Wishbone
   RAM, and a four-word RV32I test with a checked data store.
2. Run `make dv-boot`: CPU0 executes Boot ROM, reads flash, writes both blank
   SRAMs, releases CPU1 via reset MMIO, and requires **both** CPU signatures.
3. Run `make dv-chip` for the implemented local/global NoCs, upstream
   AXI/AXI-Lite bridges and CPU0-coordinated phases. PULP iDMA is generated in an optional separate hardware configuration;
   CPU-started descriptors and interrupt-driven firmware remain next.

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
| DMA0 CSR | `0x40000000` | AXI4-Lite | optional AXI4-to-Lite and staged 64-bit head/doorbell CSR in `DmaEnable=1` |
| DMA1 CSR | `0x40010000` | AXI4-Lite | optional AXI4-to-Lite and staged 64-bit head/doorbell CSR in `DmaEnable=1` |
| Reset control | `0x40020000` | R/W 32-bit | legacy boot responder and chip PULP AXI-Lite register bank |
| Memory controller CSR aperture | `0x40030000` | 32-bit config transport | **reserved**, BFM storage only in the NoC test; no controller register RTL |
| HBM data | `0x1_00000000` | AXI4 64-bit | AXI RAM in memory DV; bounded AXI SRAM stand-in in chip boot |
| DDR data | `0x1_40000000` | AXI4 64-bit | AXI RAM in memory DV; bounded AXI SRAM stand-in in chip boot |

`memory0.ctrl` reserves one subsystem aperture; it does not invent actual
HBM/DDR controller registers. Per-controller register maps must come from
the selected controller's real management interface. CPU0 and CPU1 are 32-bit cores and **cannot directly
load/store addresses above 4 GiB**; the generated DMA engines have 64-bit
source/destination registers for transfers to HBM/DDR.

The legacy bootstrap responder supports aligned, full-word transfers only.
The separate chip AXI memory path checks bursts and partial writes. Future boot
ROM implementation should check a firmware container header, lengths,
checksums/authentication, failures, timeouts, image placement, and reset
permissions. Secure boot is **not implemented**.

## Hardware integration beyond the standalone bootstrap

1. The [chip boot configuration](full-chip-boot.md) now uses upstream AXI
   responders, generic SRAM, and a Wishbone-to-AXI bridge for SERV across
   the shared NoCs. The standalone bootstrap below is retained independently.
   Physical SRAM macros remain future work.
2. Add a minimal SPI/QSPI reader or a debug/UART streaming boot interface;
   keep exactly the same image/load, reset and completion contracts. Test
   *traffic-driven* SRAM loading (no SRAM backdoor preload in cold boot).
3. Integrate CPU-side descriptor/IRQ firmware with the generated PULP iDMA CSR: CPU0 prepares descriptor chains,
   length, status and interrupt. Accelerate future firmware staging/copies.
4. Validate the optional real DMA/CSR endpoints, then add memory controllers alongside CPU/SRAM/reset
   attachments in the chip boot scope. CPU0 must initialize controllers and
   wait for DDR/HBM ready before issuing DMA there.
5. Extend the implemented addressable secondary reset with recovery/error
   policies. Add an optional secure management processor only if isolation,
   always-on power domains, or recovery requirements justify it.

The system remains intentionally **non-cache-coherent** for now. Once caches
are added, DMA/shared-memory synchronization and cache maintenance must be
specified and verified, not assumed.

## Bootstrap local memory integration (implemented)

`rtl/interconnect/boot_local_decode.sv` is a synthesizable one-hot
address decoder instantiated for both CPU0 AXI-Lite AR and captured AW
transactions. It rejects unmapped reads and writes instead of aliasing
addresses. `rtl/memory/local_sram.sv` is a reusable two-initiator RTL
memory bank (CPU0 AXI-Lite-facing access, SERV registered Wishbone
access), with byte strobes and no power-on initialization. Each bank is
an independent RTL module; the standalone SRAM test verifies both ports.

The cold-boot test connects *real* CPU0/CPU1 bus handshakes to this
decoder and these banks. Firmware is copied through CPU0 stores, not
via a testbench backdoor. The memory model still contains the
AXI-Lite/Wishbone protocol responders and a read mux: this is **not**
yet a configurable full-chip AXI crossbar or Wishbone-to-AXI bridge.
A future fabric backend must preserve the exact boot and SRAM tests
without relying on this bootstrap-only protocol responder.

Boot policy is explicit under `boot.strategy`, `boot.image_source`,
`boot.secondary_release`, and `boot.sram_powerup`. Unsupported choices
are rejected by the generator, not quietly remapped to this ROM-copy
implementation. The ROM/flash model is deliberately kept for this
supported boot mode, and actual physical SRAM macro selection is pending.

## Verification scope review

Required CI scopes are configuration and deterministic generation, AXI crossbar
memory/negative scoreboard, independent uninitialized dual-port SRAM, standalone
SERV instruction execution, and ROM/flash-to-SRAM cold boot. The `dv-cpu` request-only fetch smoke is retained as a diagnostic in the
full/CI diagnostics suite; it does not prove instruction execution.
We no longer pass `SERV_CLEAR_RAM`: the SERV architectural register file
starts without a testbench initialization and the real program executes.
Boot SRAM contains unspecified contents, never zero-preloaded firmware.

## Chip-level execution

`make dv-chip` runs a separate, real CPU/NoC boot assembly with upstream
WB/AXI/width adapters, upstream SRAM, reset registers and AXI memory
stand-ins. CPU0 coordinates init/run/check and every CPU checks a peer.
The legacy four-word prototype images above remain its independent
bring-up scope. The chip has its own generated phased firmware in
`gen/chip/`, using the same ROM-copy boot policy and address map.
See [full-chip boot](full-chip-boot.md) for its framework and boundaries.
