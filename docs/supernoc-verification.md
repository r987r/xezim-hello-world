# Reuse open-source AXI verification IP for the single super-NoC test

## Chosen baseline

The entire data/config NoC hierarchy is exercised through **one** integrated
`gen/supernoc/supernoc_tb.sv`, not separate BFM/bridge/router smoke testbenches.

- **DUT:** all eight actual upstream FlooGen SystemVerilog mesh modules,
  linked through their full AXI4 request/response types with port widths
  checked against the source FlooGen YAML.
- **Protocol agents:** mature open-source
  [cocotbext-axi](https://github.com/alexforencich/cocotbext-axi)
  `AxiMaster` and `AxiRam` sparse-memory AXI4 BFM. This supports
  multi-ID requests, bursts, mixed read/write, and configurable stalls.
- **Simulator:** standard upstream Verilator via
  [cocotb](https://github.com/cocotb/cocotb) 2.0.1, both dependencies
  pinned in CI. Xezim 0.11.4 remains the separate structural compilation
  and existing CPU boot/AXI memory regression path.
- **Thin shims only:** `tools/supernoc_gen.py` flattens generated AXI4
  packed-port structs to ordinary per-channel signals for cocotb; it does
  not implement a router, bus fabric, DMA, SRAM, or AXI protocol BFM.
- **Data/config protocol:** FlooGen carries AXI4 physical transport for
  both; config operations are single-beat 32-bit accesses. Actual CPU/CSR
  AXI4-Lite bridges are later upstream PULP integration work.
- **Test acceptance:** reports must show actual B/R OKAY, correct data
  readback and route coverage across the **connected** local/global
  data/config networks, not merely compiler exit status. Additional
  concurrency/burst/backpressure/error tests are future coverage stages.

The original candidate, [PULP AXI `axi_test.sv`](https://github.com/pulp-platform/axi/blob/master/src/axi_test.sv),
provides excellent AXI SV drivers, `axi_rand_master`, mapped
`axi_rand_slave`, AXI-Lite drivers and scoreboards, with example
[`tb_axi_xbar.sv`](https://github.com/pulp-platform/axi/blob/master/test/tb_axi_xbar.sv).
However our installed Verilator 5.020 cannot parse the upstream
`randomize() with` constraints/class definitions in that file. Do **not**
fork/copy the IP or add ad-hoc SV BFM shims to disguise the issue.
The cocotb library is the selected supported alternative.

## Existing UVM sequence/IP options (not yet integrated)

**Yes, open-source AXI UVM sequence libraries exist.** Evaluate, don't
reinvent them. Their author claims need actual pinning and simulator tests.

1. [KVIPS AXI4](https://github.com/kiranreddi/kvips): UVM AXI4 master/slave
   agents, sequences, protocol assertions, coverage, scoreboard and
   documented Verilator back-to-back/DUT flows. Candidate for a future
   UVM mode; first verify a full UVM 1.2/1800.2 sequence with Xezim
   and all relevant outstanding read/write semantics.
2. [AXI_UVM_verification](https://github.com/k1thhh/AXI_UVM_verification):
   reusable master/slave agents, constrained-random plus directed read,
   write, FIXED/INCR/WRAP burst sequences and scoreboard; openly states
   it is an AXI4 **subset** and its tested flow targets Vivado XSim.
3. [axi-uvm](https://github.com/marcoz001/axi-uvm):
   established publicly available AXI3/AXI4 master and slave drivers,
   coverage, scoreboard, and parallel pipelined transactions. It has
   limitations, so do not assume full AXI4 compliance.
4. [Accellera UVM / Chips Alliance UVM-Verilator](https://github.com/chipsalliance/uvm-verilator)
   is the **UVM base class library**, not an AXI VIP or sequence package.

Do not add a second complete super-NoC testbench merely to switch a
driver. Reuse one integrated DUT and adapt the verification driver
binding if/when an actual existing AXI UVM library passes on both
relevant simulators. Preserve the separate CPU/boot/memory regression
scopes for fault isolation.

## Current integration boundary

The NoC wrapper terminates true external CPU/DMA/CSR/SRAM boundaries
using reusable AXI BFMs. Real CPU, DMA, SRAM register adapters, and the
memory target crossbar are **not yet attached to this full-chip wrapper**;
they are separately tested where available. Physical HBM/DDR controllers
remain future work. A successful NoC BFM test does not imply the complete
CPU+iDMA+memory system is functional.
