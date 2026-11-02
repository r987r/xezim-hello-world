# Boot debug traces (adapted from Sv-test)

The failing cold-boot regression now has opt-in **Xezim VCD waveforms** and timestamped Wishbone instruction/data transactions. The failed GitHub Actions job uploads `boot-trace.vcd` and `boot-dv.log` alongside generated manifests. This is intentionally not a pass criterion change: both CPU application signatures remain mandatory.

```bash
BOOT_WAVE=1 BOOT_TRACE=1 XEZIM_BIN=/path/to/xezim make dv-boot
python3 tools/debug/vcd_find_edge.py boot-trace.vcd c1_ibus_ack --edge rising
python3 tools/debug/vcd_signal_activity.py boot-trace.vcd c1_dbus_cyc
```

The two VCD inspection utilities are copied from [Sv-test](https://github.com/r987r/Sv-test/tree/main/scripts/vcd), retaining its Python implementation. Xezim supports [`--wave` and native `--fst`](https://github.com/aionhw/xezim/blob/main/docs/user-guide.md); [`XEZIM_VALUE_TRACE`](https://github.com/aionhw/xezim/blob/main/docs/DEBUGGING.md) provides targeted source-level change logs. **The CPU1 boot is still failing**, and the earliest observed erroneous transaction is the first SERV data write after fetching `0x110002b7` at `0x11000000`. The next task is to resolve instruction acknowledgment and decoder/RF state, not to accept a partial boot.

The Sv-test AXI4-Lite UVM scoreboard was *not* imported into this Wishbone scope: it checks AXI AW/W/B/AR/R channels and would be misleading here. It can be adapted later for the DMA CSR fabric.
