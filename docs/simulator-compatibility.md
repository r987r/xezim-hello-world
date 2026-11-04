# Cross-simulator FlooNoC compatibility status

This is a targeted integration note for future coding agents, not a request
to reintroduce the old standalone Xezim port-slice reproducer.

## Same source, two independent compilers

The workflow [`floonoc-elab.yml`](../.github/workflows/floonoc-elab.yml)
downloads **the pinned upstream FlooNoC commit and its Bender.lock**,
compiles all eight generated local/global NoC structural tops via
**Verilator 5.020**, and separately checks the **same eight tops
and upstream file list** via the pinned **Xezim 0.11.4** binary.
Both simulator probes discover configured networks through the shared
[YAML regression](regression.md): `python3 tools/regress.py compatibility`
and `python3 tools/regress.py noc-verilator`.

Both structural compile/elaboration stages pass for all eight NoCs.
Those stages alone are not packet-transfer tests. The same workflow also
runs the separate connected NoC traffic and corruption checks in Verilator. The separate [super-NoC test](supernoc-verification.md) now
runs real routed traffic in Verilator, including concurrent IDs, stalls,
bursts, destinations and downstream SLVERR. Xezim's NoC path remains
compile-only; no equivalent Xezim routed-traffic pass is claimed.

## Warnings that must not be hidden

The first successful all-eight comparison:
[run 41549692954](https://github.com/r987r/xezim-hello-world/actions/runs/41549692954).

| NoC | Xezim structural compile | Reported Xezim warning lines |
| --- | --- | ---: |
| compute0.local_config | success | 0 |
| compute0.local_data | success, width diagnostics | 6 |
| compute1.local_config | success | 0 |
| compute1.local_data | success, width diagnostics | 6 |
| global_config | success | 0 |
| global_data | success, width diagnostics | 6 |
| memory0.local_config | success | 0 |
| memory0.local_data | success, width diagnostics | 6 |

The reported six lines per data mesh are **five warnings plus
Xezim's suppression notice**, not necessarily the total number of
width warnings. `XEZIM_DIAG_LIMIT=0` allows deeper debugging, but do
not flood CI logs by default.

The warnings repeatedly point into pinned upstream
[`hw/floo_rob.sv`](https://github.com/pulp-platform/FlooNoC/blob/05368bdff914f91a48b47c4ceddfc6ff266c6b3a/hw/floo_rob.sv)
and its dependencies:

- `cc_fifo` array-of-instances connections `data_i`, `data_o`:
  a 2-bit per-instance port is compared with a much wider packed-array
  expression in Xezim. The source deliberately declares
  `fifo_data_t [NumIds-1:0] fifo_data_in/fifo_data_out` and instantiates
  `i_status_table_fifo [NumIds-1:0]`. Verify IEEE module-array port
  slicing rather than blindly assuming a design bug or truncating data.
- `cc_fifo.usage_o`: 4-bit module port versus e.g. 64/128-bit packed
  array expression in the Xezim warning (also an array-instance boundary).
- `cc_lzc.cnt_o`: 3-bit output versus a reported 1-bit connection.
- `tc_sram_impl.addr_i`: 3-bit expected versus a 1-bit connection.

The Verilator path also prints some width diagnostics for upstream
`floo_rob`, `floo_meta_buffer` and helper cells. **Do not claim each
difference is an Xezim simulator bug** until the exact specialized
parameter widths, packed-array semantics and observable routed traffic
have been compared between both simulators.

In a previous compile attempt, upstream `floo_rob_status_table`
used `$clog2(MaxTxnsPerId)` for `fifo_usage_t` while `cc_fifo`
exports a `$clog2(Depth+1)` usage counter. A power-of-two
`MaxTxnsPerId=8` caused Verilator's fatal width error; the current
native configuration deliberately uses **MaxTxnsPerId=9** for a data
MaxTxns budget of 8, without modifying any upstream Verilog.
The generated RTL documents this sizing parameter. Do not remove
this guard or suppress the error silently.

## Follow-up verification within subsystem-level testbenches

- Preserve the passing Verilator connected-NoC regression; establish an
  equivalent Xezim routed-traffic path on the same pinned RTL before
  claiming cross-simulator functional agreement.
- Preserve the chip's implemented CPU/SRAM/reset and upstream AXI-Lite
  adapters; integrate real iDMA/CSRs next. No custom AXI-Lite NoC or new
  router implementation and **no per-bridge/per-router TB proliferation**.
- Compare observed data, IDs and backpressure; if Xezim differs from
  Verilator, record the precise hierarchy, source line, configuration,
  waveform and result in this doc and an upstream issue.
- The shared NoC assembly now serves the CPU boot configuration. Keep
  actual CPU/bridge/SRAM/reset paths distinct from pending real iDMA and
  physical-controller paths in the one chip diagram.

The regular [`dv-soc.yml`](../.github/workflows/dv-soc.yml)
continues to execute the existing Xezim CPU ROM boot, SERV program,
local SRAM and 2x2 Verilog-AXI memory tests. It does not replace this
independent upstream FlooNoC compatibility check.

## Chip boot configuration

`chip-xezim-compile` compiles the assembled chip and shared SV checker;
`chip-boot` runs it with Verilator/cocotb. Keep these results separate.
The first Xezim functional probe exceeded a 180-second wall budget before
phase completion; it is not a functional pass. The CPU address-classification
adapter uses named select wires: Xezim 0.11.4 warned about implicit nets for
parameter names in inline instance-port expressions. Upstream IP is unmodified.
The first local Verilator build also hit an undefined generated scheduling
helper at link time; validation must use a complete successfully linked
current configuration, never patched generated C++.
