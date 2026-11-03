# AXI verification IP and UVM sequence reuse

## Chosen immediate testbench implementation

The single generated `gen/dv/supernoc_tb.sv` composes *all eight* real
FlooGen router meshes, with module/port widths checked by
`tools/supernoc_tbgen.py`. It uses the **already-pinned PULP AXI library**:

- `src/axi_test.sv` / `axi_test::axi_driver` for AXI4 directed
  AW/W/B and AR/R sequences. This is an upstream driver, not custom BFM RTL.
- `src/axi_sim_mem.sv` for AXI slave memory and register-window
  responders. These are **behavioral targets**, not production SRAM,
  DDR/HBM or iDMA controller hardware.
- `include/axi/assign.svh` for interface/struct channel mapping.
- `src/axi_test.sv` also supplies `axi_rand_master`,
  `axi_rand_slave`, `axi_lite_rand_master`, `axi_lite_rand_slave`
  and `axi_scoreboard`, for follow-up stress/scoreboard coverage.
- Reuse its original [upstream `tb_axi_xbar.sv`](https://github.com/pulp-platform/axi/blob/70b8e54fd460e3308e58be596ceb3566a6e3576e/test/tb_axi_xbar.sv)
  for concurrency and route-monitor methodology instead of building a
  custom AXI VIP.

**Important limitation:** The verification-level target at
`memory0_local_data.target_crossbar` presently uses a single PULP
`axi_sim_mem` to isolate real NoC routing; the independently verified
2x2 Verilog-AXI memory crossbar is not connected into this new TB yet.
Both global memory ingress links reach Memory0's local FlooNoC, but
they share one outgoing NI. Do not claim two independently exercised
memory crossbar ingresses or actual HBM/DDR controllers.

## Upstream UVM sequence libraries considered

- [OpenTitan DV Base Library](https://github.com/lowRISC/opentitan/tree/master/hw/dv/sv/dv_lib):
  useful **UVM env/agent, scoreboard, sequence and RAL methodology**.
  [CSR utility sequence library](https://opentitan.org/book/hw/dv/sv/csr_utils/index.html)
  provides reset, read/write, bit-bash, aliasing and memory-walk
  sequences. It is not a drop-in PULP AXI4 VIP.
- [PULP AXI test classes](https://github.com/pulp-platform/axi/blob/70b8e54fd460e3308e58be596ceb3566a6e3576e/src/axi_test.sv):
  **preferred today** because exactly the same upstream package defines
  our Bender-resolved protocol types and AXI driver. Not UVM framework
  classes, but reusable mature AXI transactions with constrained random
  support and scoreboarding.
- [cocotbext-axi](https://github.com/alexforencich/cocotbext-axi):
  broad AXI/AXI-Lite verification IP, but Cocotb/Python rather than UVM.
  Good independent simulator differential test, no SV class compatibility
  assumed, and could run with Verilator once integration tests are ready.
- [OpenTitan CSR sequences](https://github.com/lowRISC/opentitan/tree/master/hw/dv/sv/csr_utils):
  reusable once actual AXI-Lite control registers are integrated.

**Decision:** do not import a random third-party student UVM AXI
implementation, create a second independent AXI driver, or build
a giant UVM layer just for topology bring-up. First prove full
end-to-end transactions and preserve diagnostic waveform/coverage.
Then add one UVM environment with sequence library using verified
upstream agent and scoreboard components if UVM gives real value.

## Simulator compatibility

Xezim is the primary runner for PULP AXI class-driven sequences.
The pinned Verilator build rejects some upstream
`axi_test.sv` constrained-random class constructs during parser setup.
That is a **VIP/simulator support limitation**, not evidence that
the FlooNoC RTL failed a transaction. The separate
`.github/workflows/floonoc-elab.yml` independently elaborates all
eight real FlooNoC modules under Verilator; a green elaboration does not
replace actual read/write tests. Do not disable protocol assertions
or replace router RTL to paper over either simulator's limitations.
