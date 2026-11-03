# Reuse open-source AXI verification IP for the single super-NoC test

## Chosen baseline

The entire data/config NoC hierarchy is exercised through **one** integrated
`gen/supernoc/supernoc_tb.sv`, not separate BFM/bridge/router smoke testbenches.

- **DUT:** all eight actual upstream FlooGen SystemVerilog mesh modules,
  linked through their full AXI4 request/response types with port widths
  checked against the source FlooGen YAML.
- **Protocol agents:** mature open-source
  [cocotbext-axi](https://github.com/alexforencich/cocotbext-axi)
  `AxiMaster`, `AxiSlave`, `AddressSpace` and `SparseMemoryRegion`.
  Each target exposes only its decoded windows, with no address wrapping. This supports
  multi-ID requests, bursts, mixed read/write, and configurable stalls.
- **Simulator:** standard upstream Verilator via
  [cocotb](https://github.com/cocotb/cocotb) 1.9.2, with `cocotbext-axi==0.1.24`, pinned in CI to match
  the Ubuntu 24.04 Verilator 5.020 release. Xezim 0.11.4 remains the separate structural compilation
  and existing CPU boot/AXI memory regression path.
- **Thin shims only:** `tools/supernoc_gen.py` flattens generated AXI4
  packed-port structs to ordinary per-channel signals for cocotb; it does
  not implement a router, bus fabric, DMA, SRAM, or AXI protocol BFM.
- **Data/config protocol:** FlooGen carries AXI4 physical transport for
  both; config operations are single-beat 32-bit accesses. Actual CPU/CSR
  AXI4-Lite bridges are later upstream PULP integration work.
- **Test acceptance:** reports must show actual B/R OKAY, correct data
  readback at the intended endpoint and all 28 source/window routes across
  the **connected** local/global data/config networks. The same test runs
  136 concurrent burst/partial/single-beat cases, all-five-channel stalls,
  multiple outstanding data streams with reused IDs and distinct per-stream
  payloads, byte-strobe guard
  checks, and 24 routed B/R SLVERR pairs. Four boot-window routes are reads
  against seeded BFMs; the real CPU cold-boot scope remains separate.

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
   documented Verilator back-to-back/DUT flows. Its README currently uses
   Verilator 5.048 and says SVA assertions are skipped in that flow;
   this is not validation on this repo's 5.020 baseline. Candidate for a
   future UVM mode after pinning and testing its sequences and checkers.
2. [AXI_UVM_verification](https://github.com/k1thhh/AXI_UVM_verification):
   reusable master/slave agents, constrained-random plus directed read,
   write, FIXED/INCR/WRAP burst sequences and scoreboard; openly states
   it is an AXI4 **subset** and its tested flow targets Vivado XSim.
3. [axi-uvm](https://github.com/marcoz001/axi-uvm):
   established publicly available AXI3/AXI4 master and slave drivers,
   coverage and parallel pipelined transactions. Its README describes a
   scoreboard that counts address/response packets, not a full memory-data
   reference model. Do not assume full AXI4 compliance or payload checking.
4. [Accellera UVM / Chips Alliance UVM-Verilator](https://github.com/chipsalliance/uvm-verilator)
   is the **UVM base class library**, not an AXI VIP or sequence package.

Do not add a second complete super-NoC testbench merely to switch a
driver. Reuse one integrated DUT and adapt the verification driver
binding if/when an actual existing AXI UVM library passes on both
relevant simulators. Preserve the separate CPU/boot/memory regression
scopes for fault isolation.

## Native FlooNoC non-atomic ID capacity

The first integrated 8-mesh simulation hit upstream
`floo_meta_buffer.sv:142` `TooFewIdBits2` at time zero, starting with
`memory0_local_config.controller_regs_ni`. The original FlooGen
instances used the upstream default **one reserved atomic transaction
ID**, even though the SoC never issues AXI ATOPs. One-bit config
destination IDs could not accommodate the reserved atomic space *and*
multiple unique non-atomic IDs.

**Fix in the generated wrapper (no upstream RTL fork):** bind native
`floo_axi_chimney.AtopSupport=0` and `MaxAtomicTxns=0` on **every**
upstream FlooGen-generated NI, from `config/interface_contracts.yaml`.
This satisfies upstream `NoAtomicTxns`, `TooFewIdBits1`, and
`TooFewIdBits2` capacity assertions without reducing the configured
`MaxUniqueIds=2` on control or `MaxUniqueIds=4` on data. The generator
fails closed on unintended atomic reservations. Any future ATOP-capable
SoC must add correct output ID width and real atomic verification before
enabling them.

Do not silence source assertions or restrict all pending IDs to one
merely to make the simulator start. A passing compile is not enough;
the full AXI data/readback regression must pass independently.

## Target-only FlooNoC reorder-buffer configuration

A later full eight-mesh simulation reached a different upstream
time-zero assertion:
`floo_axi_chimney.sv:887 NoMgrPortRobType` at
`memory0_local_data.target_crossbar_ni`.
The pinned `floo_pkg::set_ports(cfg, en_sbr, en_mgr)` marks
destination-only NIs with `EnMgrPort=0`, and the upstream
`NoMgrPortRobType` assertion **requires both BRoBType and RRoBType to
be NoRoB whenever EnMgrPort=0**. Our generic native chimney config
previously applied `NormalRoB` to both initiator and target NIs.

The generator now derives `xezim_chimney_cfg_no_mgr()` directly from
the configured native RoB capacities, changing only B/R types to
`NoRoB` for the upstream-generated **destination-only** chimney
instances. Initiator-facing NIs retain their configured types: `NormalRoB` on data
and `NoRoB` on config.
The generator checks role counts and tests the mixed-role case.
There is no fork of FlooNoC and no simulator assertion suppression.
CI regeneration produces checked-in SystemVerilog with these role-specific
parameter bindings. Actual AXI traffic must still pass before reporting
functional NoC verification.

## Current integration boundary

The NoC wrapper terminates true external CPU/DMA/CSR/SRAM boundaries
using reusable AXI BFMs. Real CPU, DMA, SRAM register adapters, and the
memory target crossbar are **not yet attached to this full-chip wrapper**;
they are separately tested where available. Physical HBM/DDR controllers
remain future work. A successful NoC BFM test does not imply the complete
CPU+iDMA+memory system is functional.

## RAM setup and destination validation

The prior PR head failed before traffic: `AxiRam` defaults to `2**64`
bytes, and its `Memory` constructor calls Python `len()` on that sparse
memory, raising `OverflowError`. Merely reducing the size would still
allow its modulo address mapping to hide wrong destinations.

The test now uses the same upstream library's `AxiSlave` backed by an
`AddressSpace` containing `SparseMemoryRegion` objects for the exact leaf
windows. It also compares each bus write with the intended target's
storage before routed readback. No RAM, responder or AXI handshake code
has been copied or invented. Empty upstream `AddressSpace` objects inject
mapped target faults; upstream `AxiSlave` produces SLVERR and the real
NoCs must preserve it. This does not test unmapped NoC DECERR: the pinned
FlooNoC address translator instead asserts `DecodeError` on unmapped traffic.

`gen/supernoc/manifest.json` records each source window, expected leaf,
network path and every cross-network connection. Generation traces both
ends of each range and rejects missing decodes, loops and width mismatches.
No numeric cutoff excludes relocated SRAM or CSR apertures.
`tests/test_supernoc_gen.py` independently compares the wrapper's link set
with the canonical architecture graph.

## Running and retaining evidence

Install [the regression prerequisites](regression.md), then:

```bash
make test-noc
# Python-only rerun of a fingerprint-verified successful RTL build:
python3 tools/regress.py supernoc --stage run
# Success means the expected named corruption failure was detected:
python3 tools/regress.py supernoc-negative
```

The runner resolves the locked Bender graph and checks cocotb XML,
rejecting failed, empty, errored or skipped results. A positive run also
requires the final `PASS supernoc:` marker. Negative acceptance requires
the exact injected mismatch and a failing simulation, excluding timeouts
or compile errors. CI retains `.tools/regression/` positive/negative logs,
XML, resolved sources, plans, results and the route manifest on success
and failure. CI rebuilds RTL before the positive run. A run-only request
must match the source/header/options/tool fingerprint and executable hash;
a stale or missing binary is rejected.
Generation metadata names verification commands instead of hardcoding
historically false pass/fail flags. Current-source evidence belongs in
actual run logs and the CI head SHA.

## Local validation on 2026-11-03

The local Verilator 5.020 / cocotb 1.9.2 run completed at 84,980 ns:

```text
PASS concurrent traffic: 6 managers, 136 burst/partial/single-beat cases with stalls
PASS downstream errors: 24 routed B/R SLVERR pairs
PASS supernoc: 8 real FlooNoC meshes, 11 local/global links, 28 AXI4 routes
TESTS=1 PASS=1 FAIL=0 SKIP=0
```

The opt-in corruption run failed at the intended
`FAIL supernoc injected data mismatch detected` assertion; its XML reports
one failure, while the positive XML reports zero. All 63 configuration
checks, generated-file drift checking, Xezim default/full/sparse memory
profiles, negative memory checker, SRAM, SERV and two-core cold boot also
passed locally. Xezim independently compiled all eight meshes with the
known data-network width warnings retained.

Published baseline `bd572f0` also passed [the complete NoC CI job](https://github.com/r987r/xezim-hello-world/actions/runs/41659508505)
and [Xezim CPU/memory CI](https://github.com/r987r/xezim-hello-world/actions/runs/41659508518).
Final review strengthened the concurrent streams with distinct payloads;
check the [NoC workflow](https://github.com/r987r/xezim-hello-world/actions/workflows/floonoc-elab.yml)
for the exact current head before merging. Passing historical runs do not
validate later RTL or test changes.

Validated RTL wrapper SHA-256: `27ab3ad2c8e7757f132c2b33388539ce86c886e2ff553884d7701e75417fc33a`.
