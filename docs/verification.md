# Hierarchical verification plan

`config/soc.yaml` declares executable and planned scopes, reflected in
`gen/verification/plan.json`. Generated memory/boot/NoC scopes derive their
addresses and topology from that configuration. Standalone CPU/SRAM checks
remain independent bring-up tests. There is one architecture diagram;
verification details live in source, manifests and logs.

`gen/verification/routes.json` enumerates the separate memory crossbar's
expected paths. `gen/supernoc/manifest.json` records the connected NoC
wrapper's source windows, leaf destinations, network paths and AXI links.
`make check-generated` checks exact artifact names and contents. Each
fabric scope drives actual interconnect RTL; the connected NoC scope
uses upstream AXI agents.

The executable build/test catalog is resolved directly from the current regression YAML (including its runtime and compile/lint-only targets); it is [regression YAML](../config/regression.yaml), not a separately maintained fixed list;
[Bender source sets](../Bender.yml) replace per-test shell file arrays.
See [build and regression commands](regression.md) for the full suite,
filelist inspection, stage separation and retained results.

## Implemented scopes

| Scope | RTL under test | Checks |
| --- | --- | --- |
| Generator/configuration | SoC schema, addresses, backends and generators | Determinism, invalid configurations rejected, generated-file drift |
| Memory fabric | Verilog-AXI 2×2 crossbar and HBM/DDR behavioral targets | Default/full/sparse routes, responses, IDs, burst data and denied-path DECERR |
| Negative memory check | Same crossbar with a corrupted expectation | Must fail with the intended `FAIL AXI read` diagnostic |
| Local SRAM | Existing reusable dual-port SRAM test model | Uninitialized power-up, byte strobes and both ports |
| SERV execution | Real SERV and standalone Wishbone RAM | Three instructions execute and store the checked signature from a four-word image |
| CPU cold boot | PicoRV32/SERV, ROM, flash, blank SRAM and reset MMIO | CPU0 copies both programs through bus stores, releases CPU1 and both produce signatures; default and relocated address maps |
| Chip boot configuration | Real CPUs, shared NoCs, upstream WB/AXI/SRAM/reset and AXI memory stand-ins | CPU0-driven cold boot and init/run/check, every CPU greeting/peer check, missing-CPU negative, HBM/DDR model readback |
| Connected NoC BFM | All twelve generated FlooGen data/config meshes | All 28 mapped source/window routes, intended storage, concurrent reused IDs with distinct stream payloads, bursts, byte guards, stalls, SLVERR and corruption detection |

The CPU fetch smoke is a request-only diagnostic included in `full` and
CI diagnostics. [Boot details](boot.md) distinguish real instruction execution
from request-only smoke checks. The connected NoC scope uses AXI BFMs at
real endpoint boundaries; it does not attach CPUs, iDMA, AXI-Lite bridges
or the separately tested memory crossbar. Behavioral targets do not prove
physical HBM/DDR controller or PHY behavior.

## Canonical selected-run plan and honest adapter boundary

Every YAML regression target saves one `selected-test-plan.json` before HDL execution; it records tested source revision, resolved command arguments, selected firmware/variant, INIT/RUN/CHECK source intent, and a deterministic plan digest. The common runner records actual command start and checked outcome in `runner-events.json`. The publisher verifies the saved plan, its hash, CI provenance and observed command envelope before showing it in that exact historical test report.

**This is not full stimulus migration yet.** The two SCN-2 targets reference the exact immutable source-resolved action scenario and require independent RTL-observed matching scenario evidence to qualify PASS. Three compile/lint-only targets are explicitly not executable stimulus. The remaining 23 runtime tests use a named `legacy_entrypoint_adapter` and their *internal* Python/C/SV/Xezim actions stay opaque unless separately instrumented. Temporary exceptions are source-controlled in [runtime migration policy](../config/runtime_migration.yaml); adding an unregistered legacy target fails CI instead of silently fabricating actions. [#119](https://github.com/r987r/xezim-hello-world/issues/119) owns removal of the exceptions as typed IP/driver adapters are implemented. Never interpret command completion or a planned milestone as proof that a particular AXI/TLP/GMII/DFI transaction occurred.

## Next integration sequence

Initial Ethernet GMII/CPU-C, PCIe host/CPU-iDMA with modeled DDR, and LiteDRAM controller/CPU-iDMA are separately verified in opt-in variants. Their **single-run Ethernet → real DDR → CPU/iDMA → PCIe host** path remains the next distinct acceptance gate; do not infer it from individual passing regressions. The test plan display exists for every configured target, but only two runtime tests presently execute a common resolved scenario. Track executable adoption under [#119](https://github.com/r987r/xezim-hello-world/issues/119).

The [chip boot configuration](full-chip-boot.md) now attaches the CPUs,
SRAM, upstream protocol/width adapters, reset registers and target crossbar.
Keep the existing independent memory/boot/NoC scopes for fault isolation.

1. Preserve verified SS0+SS1 DMA/CSR BFM traffic and real CPU0 C-launched DMA through full-chip NoCs ([CI 41933332567](https://github.com/r987r/xezim-hello-world/actions/runs/41933332567)); next add CPU IRQ service, multi-engine concurrency and stronger faults.
2. Add real controller register maps, ready/interrupt behavior and physical
   controller/PHY models in their proper scopes.
3. Extend the chip scope with congestion/fairness, reset during traffic,
   interrupts and a portable C runtime/BSP as application tests grow.
4. Establish Xezim functional NoC/chip execution; compile-only probes stay
   separate from Verilator's routed-traffic proof.

## Selected-variant RTL, actor and monitor provenance

Every qualified full-chip AXI regression now runs a **read-only selected-variant source preflight** before simulation. It retains `variant-connectivity.json`, `variant-topology.json`, and the exact `variant-chip-manifest.json` in the same CI/test artifact bundle. These are derived from the actual test's chosen `soc_top.sv`, FlooGen network manifests, named module/instance tokens, actors, source-bound AXI monitor catalog, interface budgets, and selected filelist. No extra hand-maintained Ethernet/PCIe topology drawing is authored.

The original per-test report links to **Selected variant 2D NoC/initiator/monitor diagram**. Green solid packet/data or control/CSR links mean *generated source declares a live attachment*; dashed links remain reserved or absent. The canonical checked-in default diagram correctly preserves reserved PCIe/Ethernet packet engines. A separate opt-in PCIe/Ethernet test can display its **own active source attachment** without pretending the default graph had those wires.

Publication checks the original manifest bytes against their SHA-256 and compares all selected source-bound monitor IDs with that run's AXI transaction report. It does **not** convert a generator-declared link into a compiler-elaborated, bit-level wired connection or an actually active transaction. The per-test protocol log, transaction/counter evidence and accepted completions are the separate *runtime-observed* tier. Per-port maximum pending read/write values are configuration **budgets**, while FlooNoC `MaxTxns` is a **shared native cap**; neither means observed peak outstanding. Source-only missing/ambiguous or contradictory actors/monitor bindings fail the preflight.

For active opt-in full-chip tests, an absent variant source or monitor inventory is a **FAIL**, not a reason to show the default chip's actors and call them live. Track actual elaborated-port/bit proof, verified cross-domain normalization and complete protocol/latency evidence under [#46](https://github.com/r987r/xezim-hello-world/issues/46) and [#34](https://github.com/r987r/xezim-hello-world/issues/34).

## Optional CSR generator CI contract

The default SoC, NoC, Ethernet, PCIe and memory regression toolchain installs
`requirements.txt` only. The SystemRDL compiler and PeakRDL exporters are
separate, pinned CSR-only dependencies in `csr/requirements.txt`. Ordinary
unit-test discovery must not import those optional packages before tests run:
the dedicated `csr-firmware.yml` workflow installs both requirement files and
executes the real RDL/header, freestanding RV32I compilation and legacy-vs-
generated ELF equivalence checks. A missing CSR compiler may skip only CSR-
specific tests in a general no-CSR job; it must never be interpreted as
successful CSR qualification. Use the dedicated workflow and its source SHA
for that claim.

## Acceptance gates and present limits

- Every declared route in a scope must complete against the intended target.
- Independent storage/readback checks validate data and B/R responses.
- AXI bursts, byte strobes, IDs and bounded stalls must be exercised; a pass
  covers the stimulus run, not maximum theoretical capacity or AXI compliance.
- Negative mutations must fail for the intended reason; empty/skipped cocotb
  runs cannot count as passes.
- Sparse crossbar denied paths return DECERR. Unmapped FlooNoC addresses
  instead assert upstream `DecodeError`; mapped slave faults test SLVERR.
- Every regression has a finite timeout, reproducible directed stimulus and
  retained diagnostics. Current-source CI must pass before merge.
- Xezim executes boot/memory/SRAM/SERV and has historical structural NoC compilation evidence; qualify all twelve NoCs for the exact tested profile before claiming full current-source compilation. Verilator
  runs the connected NoC traffic test. Xezim NoC traffic remains unverified.
- The SRAM target also runs with `-D SYNTHESIS` to preserve registered
  reads under synthesis guards. This is functional simulation, not synthesis.
- The simulator binary is pinned separately; HDL changes do not rebuild Xezim.

See [implementation status](implementation-status.md) for integration limits
and [super-NoC verification](supernoc-verification.md) for commands and evidence.
