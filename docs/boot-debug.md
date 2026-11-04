# Smallest SERV bring-up and simulator debugging

For bring-up, run the small standalone SERV execution test before the
two-CPU boot test. Individual Make targets do not enforce that ordering. `make dv-serv` uses one real SERV core and a
registered-read Wishbone RAM with four preloaded RISC-V instructions:

```text
110002b7  LUI  x5,0x11000
06600313  ADDI x6,x0,0x66
1062a023  SW   x6,0x100(x5)
0000006f  JAL  x0,0
```

A PASS requires an actual store to `0x11000100` with data `0x66`, a
full-word strobe and three successful instruction fetches. The program is
preloaded only **in this standalone CPU unit test**; the cold-boot test
still requires CPU0 to copy both firmware images from flash into uninitialized
SRAM through real bus writes.

## Two failures isolated by comparing simulators

1. The initial boot model returned SERV instruction/data read values
   combinationally. Upstream [`servant_ram.v`](https://github.com/olofk/serv/blob/main/servant/servant_ram.v)
   registers read data and Wishbone acknowledgment. Matching that timing
   lets Icarus 12.0 execute the complete ROM-to-SRAM boot.
2. Xezim 0.11.3 mis-maps a **direct part-select connected to a module input**
   with non-zero lower bound. Passing `i_wb_rdt[31:2]` to a `[31:2]`
   decoder port changes the opcode from `01101` (LUI) into `01011`; the
   same issue affects `[31:7]` to SERV's immediate decoder.
   A historical isolated reproducer established the problem:
   Icarus 12.0 passes, while Xezim 0.11.3 fails the assertion.

Xezim 0.11.4 includes the upstream packed port part-select fix. The historical port-slice reproducer is removed from the SoC regression; the pinned upstream SERV source and end-to-end cold-boot regression must still pass. Do not patch upstream SERV sources for this issue.
The original 0.11.3 workaround is removed.

## Debug the real boot if it regresses

```bash
XEZIM_BIN=/path/to/xezim make dv-serv
BOOT_WAVE=1 BOOT_TRACE=1 XEZIM_BIN=/path/to/xezim make dv-boot
python3 tools/debug/vcd_find_edge.py boot-trace.vcd c1_ibus_ack --edge rising
python3 tools/debug/vcd_signal_activity.py boot-trace.vcd c1_dbus_cyc
```

The VCD analysis utilities are adapted from
[`Sv-test`](https://github.com/r987r/Sv-test/tree/main/scripts/vcd).
The CI workflow retains target logs/plans/results on every run.
Local debug commands above additionally produce `boot-trace.vcd`;
see `.tools/regression/boot/boot.log` for the transaction trace. Xezim also provides `XEZIM_VALUE_TRACE`, described in its
[debugging guide](https://github.com/aionhw/xezim/blob/main/docs/DEBUGGING.md).

The Sv-test AXI4-Lite UVM scoreboard is intentionally not used here:
SERV's interface is Wishbone, and importing AXI-Lite checks into this scope
would hide the actual protocol boundary. The AXI scoreboard is a candidate
for the future DMA CSR fabric.
