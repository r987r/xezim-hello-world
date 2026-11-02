# Exact unit-level testbench inventory and next verification gates

As of 2026-11-02, audited against `main` commit
[`28fc5483`](https://github.com/r987r/xezim-hello-world/commit/28fc5483314732e4f8c81333525a19369389dc4c)
and its
[passing GitHub Actions RTL run](https://github.com/r987r/xezim-hello-world/actions/runs/41496052295).
Keep this inventory updated whenever a DUT, testbench, or CI scope changes.
**Do not conflate unit TBs with SoC integration.** Check the current CI SHA.

## All seven RTL testbench tops

| DUT/testbench and source | Exact command | Verified today / exclusions |
| --- | --- | --- |
| Xezim executable smoke: `dv/smoke/hello_world_tb.sv` | `make smoke` or direct pinned simulator | Tests basic SV arithmetic and `$finish`; used in simulator *publishing* workflow, not the SoC `make test` target or normal DV CI |
| Simulator part-select reproducer: `dv/simulator/port_slice_repro.sv` | `"$XEZIM_BIN" --no-cache -s port_slice_repro dv/simulator/port_slice_repro.sv` | Main CI: PASS. Xezim 0.11.4 preserves nonzero-index input port part-select mapping. Older 0.11.3 was broken; do not reintroduce the old SERV patch |
| Optional two-CPU fetch smoke: `dv/cpu/heterogeneous_cpu_tb.sv` | `make dv-cpu` | Both *real* PicoRV32/ SERV are instantiated and required to request an instruction. No acknowledgments: NOT a CPU software execution/NoC test. Excluded from normal CI and `make test`; not newly verified by the cited CI run |
| Standalone SERV execution: `dv/cpu/serv_minimal_tb.sv` | `make dv-serv` | Main CI: PASS. Unmodified pinned upstream SERV executes LUI, ADDI, SW from deliberately preinitialized **unit-test-only** RAM, writes 0x66 to 0x11000100 with full strobes and >=3 fetches. Not a cold boot or general ISA conformance test |
| Behavioral SRAM unit: `dv/memory/local_sram_tb.sv` | `make dv-sram` | Main CI: PASS. 256-byte instance of `rtl/memory/local_sram.sv`, initially unknown contents; full write, byte strobes, registered Port B read, independent addresses, Port B write visible to Port A. Real RTL model, NOT an ASIC SRAM macro or a complete corner-case suite |
| Actual dual-CPU cold boot: `dv/boot/boot_tb.sv` | `make dv-boot` (`BOOT_WAVE=1 BOOT_TRACE=1` for traces) | Main CI: PASS. PicoRV32 executes ROM; flash model is read-only; CPU0 does 4-word bus copies into each of two originally blank 16-KiB `local_sram` banks, writes reset-controller MMIO, SERV is released and both execute SRAM images. Signatures: CPU0=0x55, CPU1=0x66. Actual main CI: 66 ROM reads, 8 flash reads, 4+4 SRAM copy stores, >=3 SERV fetches, 423 cycles. This is a **standalone boot memory responder**, not AXI crossbar, PULP AXI, FlooNoC, SPI NOR controller, or HBM/DDR |
| Generated AXI4 memory fabric: `gen/memory/memory_tb.sv` | `make dv-memory` and two `AXI_CONFIG=...` variants | Main CI: PASS. Two deterministic custom master BFMs, *real upstream Verilog-AXI crossbar*, two upstream `axi_ram` behavior targets, passive AXI route monitor. Default/full profiles: each initiator performs 4-beat write/read to each target; checks data, B/R responses, ID return and target range. Sparse profile: master0 only HBM-labelled RAM, master1 only DDR-labelled RAM; forbidden reads/writes must return `DECERR`. It is NOT a global FlooNoC or physical DRAM controller |

**Multiple test modes, one memory TB, not multiple new RTL tops:**

- `make dv-memory`: default 2x2 full reachability and burst readback.
- `AXI_CONFIG=config/examples/memory-fabric-connectivity.yaml make dv-memory`: explicitly configured native upstream crossbar parameters and full routing; ephemeral generated top (does not overwrite `gen/`).
- `AXI_CONFIG=config/examples/memory-fabric-sparse.yaml make dv-memory`: sparse mask with allowed transfers and read/write `DECERR` on prohibited routes; ephemeral generated top.
- `make dv-memory-negative`: inject bad expected data and **require** a deliberate read-check failure. It passes only when corruption is caught.
- `make dv-cpu`: optional fetch-only diagnostic, not in main CI. Its script currently still passes `-D SERV_CLEAR_RAM`; investigate/remove this leftover flag rather than treating it as evidence that a boot patch remains. `dv-boot` and `dv-serv` do not use this flag.

**CAUTION:** Permitted and forbidden AXI transfers are deliberately issued in separate phases. An earlier mixed/interleaved sparse regression hung; separating phases made current regression pass. **Simultaneous permitted/forbidden traffic under load is NOT proven.** Current master BFM uses a fixed transaction ID and a small deterministic INCR burst; no random AXI concurrency/ordering/backpressure claim is justified.

## Non-SV tests, generation, and source-of-truth

`make check-config` runs **32** Python `unittest` tests on main:

- `tests/test_socgen.py`: 20 tests. Architecture/address overlap, CPU adapter selection, backend capability rejection, memory sizing, deterministic generator output, README diagrams and obsolete output deletion.
- `tests/test_fabric_config.py`: 10 tests. Native crossbar knob settings, sparse routing, bad/unknown ports, unsupported backend knobs, asymmetric reachability rejection, compatibility.
- `tests/test_boot_policy.py`: 2 tests. ROM-copy boot is accepted; unsupported boot/source/release/init modes are explicitly rejected.

`make check-generated` compares all generated files, diagrams, manifests, and marked README section byte-for-byte (35 generated files at this baseline).
`make test` runs Python tests, generated-artifact checks, *default* memory and negative readback, SERV, SRAM, and boot. It does **not** automatically run the two alternate AXI profiles, optional CPU fetch test, Xezim port-slice test, or simulator publishing smoke. `.github/workflows/dv-soc.yml` **does** run both alternate AXI profiles and the port-slice test. Pinned Xezim is 0.11.4, downloaded as a checksum-verified prebuilt Linux executable. Normal RTL tests do not rebuild Rust.

For the actual logical versus executable graph, read
[`docs/implementation-status.md`](implementation-status.md) and all seven
[`gen/diagrams`](../gen/diagrams/) views.

## Missing unit-level DUT testbenches — implement in this order

These are **proposed** scopes and file names, not files already in the repo.

| Priority | Missing scope / suggested TB | Upstream IP to integrate and concrete PASS requirements |
| --- | --- | --- |
| P0 | `dv/bridges/serv_wishbone_axi_tb.sv` | Use a real open-source Wishbone-to-AXI bridge; connect SERV's instruction and data ports (with arbitration if shared); verify reads/writes, correct acknowledgments, request ordering, stalling, reset and error response. Existing direct boot responder does **not** prove this |
| P0 | `dv/bridges/picorv_axi_bridge_tb.sv` | Verify PicoRV32's 32-bit AXI4-Lite initiator through an upstream protocol/32-to-64-bit width bridge where needed; read/write bytes, response, address decode and stalls. Do not claim a 32-bit CPU can directly address HBM/DDR above 4 GiB |
| P0 | `dv/fabrics/compute_local_data_tb.sv` | Generate/instantiate real upstream PULP AXI local data crossbar. Connect CPU/bridge, DMA-like master, local SRAM endpoint, remote fabric egress; prove multiple initiator routes, address decode, unique return IDs, arbitration and backpressure |
| P0 | `dv/fabrics/compute_local_config_tb.sv` | Generate PULP AXI/AXI4-Lite local config fabric; multiple CSR targets and reset-control address, unmapped address error, backpressure; separate from data fabric |
| P0 | `dv/memory/tech_sram_tb.sv` | Evaluate upstream PULP `tech_cells_generic/tc_sram` or macro-compatible memory wrapper, not a new custom SRAM; prove init unknown, bytes, dual-port collisions, bounds and read latency. Adapt current Port A asynchronous versus Port B registered semantics without compromising cold-boot proof |
| P1 | `dv/dma/idma_tb.sv` | Instantiate actual pinned PULP iDMA frontend/backend and documented CSRs. Program real transfers: local->local, local->remote, remote->local, burst, boundaries, partial lengths, response errors, interrupt/status; independent data comparison. Both compute subsystems should instantiate the **same** reusable DMA IP |
| P1 | `dv/noc/floonoc_unit_tb.sv` | First compile real FlooGen-emitted upstream FlooNoC routers, network interfaces and links. Prove **at least two routers and a multi-hop** path between AXI initiators and AXI memory models; compare read/write data/IDs with contention, link backpressure and negative/unreachable cases. Until then `floonoc.executable=False` is correct |
| P1 | `dv/noc/global_config_tb.sv` | Independently instantiate global AXI-Lite config network. Route from both compute subsystems to all real CSR targets; prove control traffic progresses while data network is busy; this is a separate network from FlooNoC data |
| P1 | `dv/soc/compute_subsystem_tb.sv` | Combine real CPU, local data and config fabrics, SRAM and iDMA; CPU programs real DMA CSRs and receives completion; firmware memory loading remains bus-driven with no backdoor SRAM preload |
| P2 | `dv/soc/soc_top_tb.sv` | Full generated SoC: two different real CPUs, a DMA in each compute island, local NoCs, real global data NoC, separate config NoC, two memory ingress ports and both modeled memory targets. CPU-configured DMA copies to both global addresses above 4 GiB, dual-DMA concurrency, reset, responses and interrupts |
| P2 | `dv/memory/ddr_controller_tb.sv`, `hbm_controller_tb.sv` | LiteDRAM with supported DFI/PHY model, and HiSA HBM only with its required vendor environment; AXI RAM does **not** verify either controller or physical memory behavior |
| P2 | scalable config/RTL regression | Add `compute2` and `memory1` via YAML only, regenerate ports, IDs, routes and all diagrams, then execute every reachable source/target pair. Current architecture generator *requires exactly one memory subsystem* and its present heterogeneous memory scope requires HBM+DDR |

### Protocol-level regression gaps before any "fully verified AXI" claim

Add independently checked testcases for multiple outstanding IDs, overlapping masters, randomized read/write interleaving, concurrent permitted/denied traffic, independent AW/W timing, response reordering constraints, channel backpressure, reset during transactions, unmapped addresses, narrow/unaligned transfers, bursts crossing boundary errors, ID-width scaling, arbitrary read-versus-write permissions, and timeout/deadlock detection.

Those should come from reusable **upstream AXI verification IP** (PULP `axi_test`, or a simulator-compatible alternative such as `cocotbext-axi`) with only minimal generated signal adapters. The current custom deterministic `axi_master_bfm.sv` is a working bring-up tool, not a complete AXI VIP. Integration capability must be verified with Xezim before choosing a replacement.

### Sv-test is a separate reusable verification repository

`r987r/Sv-test` has YAML-driven unit testbenches for AXI Stream pipeline, width-conversion loopback, multi-width splitter/combiner, AXI4-Lite pipeline and `randcfg`, as well as reusable clock/reset and AXI UVC support. These are **not** currently Xezim SoC testbench tops and **must not** be counted as passing Xezim hardware scopes. Reuse its configuration/providers/UVC-generation patterns and upstream IP where compatible, rather than duplicating code.

## Rules for the next agent

1. For every DUT, maintain a separately executable testbench, with positive data/response checks and an intentionally failing negative/error test where meaningful; distinguish *implementation status* from *configuration-only status*.
2. Require a complete, passing [CI run](https://github.com/r987r/xezim-hello-world/actions/workflows/dv-soc.yml) on the **current commit**; report failed, skipped and opt-in tests accurately.
3. Pin open-source RTL in `config/ip.lock.yaml`, prefer upstream AXI/SRAM/NoC/VIP modules, and label any unavoidable custom shim with its precise protocol-boundary purpose.
4. Generate diagrams/NoC IR/Routing from authoritative `config/soc.yaml` using `make gen`; never edit `gen/`. The real RTL graph must only display actual wired and exercised RTL.
5. Preserve the working cold-boot proof, deterministic Xezim 0.11.4 regression, checksum-verified binary and prior SERV bug fix; do not quietly add compatibility hacks.
