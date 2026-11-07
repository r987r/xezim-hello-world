# Source-of-truth and IP replacement contract

This is an **implementation audit**, not a declaration that every RTL/IP
backend is swappable today. It describes the current code, its deliberate
fail-closed restrictions, and the contract a replacement must satisfy.
Keep this document as a pointer to authoritative sources, **not a second
source of topology, IP parameters, or test lists**.

## Authoritative inputs versus generated/observed evidence

| Fact | Source of truth | Derived evidence (do not edit manually) |
| --- | --- | --- |
| Subsystems, roles, buses, fabric selection, connectivity destinations, physical apertures and boot policy | `config/soc.yaml` | `gen/noc/fabric_ir.json`, generated NoC and chip manifests, architecture diagram |
| AXI read/write outstanding **budgets**, FlooNoC-native knob values and per-port overrides | `config/interface_contracts.yaml` | Generated native NoC parameters / interface sizing audit; **not observed queue depth** |
| Exact upstream IP commits | `config/ip.lock.yaml` plus the independently pinned, controller-specific `rtl/memory/ddr4/toolchain.lock.yml`; upstream FlooNoC has its own Bender lock | Fetched source and individual build provenance; audit pin consistency rather than guessing one lock owns unrelated vendored dependencies |
| Test targets, simulator, firmware mode, selected actor/report/capture sources, required milestones | `config/regression.yaml` | Original per-test `plan.json`, `planned-flow.json`, `test-flow.json`, protocol/AXI results |
| Executable directed/randomized actions, arguments and dependencies (where implemented) | Explicitly referenced `config/scenarios/*.json` and common `dv/common/scenario.py`; a seed is selected per run, **not necessarily fixed** | Source-selected and hashed scenario plan, real action events and checked completions |
| Actual selected variant RTL, endpoints, NoC routes and passive AXI taps | Generated source and manifest for **that variant**, tied to its exact hash | Selected-variant topology/monitor manifest and per-test diagram; only accepted bus events prove runtime traffic |
| Execution outcome and trace timings | Simulator/RTL/VIP observations in the original CI attempt | Test report, AXI/TLP/GMII/DFI traffic and measured (never invented) latency |
| Planned/deferred work | Issues and acceptance criteria | Not executable RTL, not evidence, not a reason to mark a source-only attachment live |

`gen/` is generator-owned; `tools/generate.py --check` detects stale
files. A selected run's frozen plan and source SHA are historical evidence:
never reinterpret an old run using today's `config/soc.yaml`.

## Current IP replacement reality

| Replacement | Would a config-only swap pass? | Hard binding discovered in source | Required adapter before qualification |
| --- | --- | --- | --- |
| FlooNoC → custom NoC | **No** | `tools/floonoc_gen.py::profiles` checks every live mesh's `backend: floonoc`; `tools/supernoc_gen.py` consumes FlooGen endpoint YAML, emits `soc_noc`; `tools/noc_diagrams.py` parses FlooGen routers/XY routes. `tools/regress.py` resolves FlooNoC-specific Bender/filelist/source closure. | Consume common SoC/fabric IR and interface budgets; emit identical **logical** AXI ingress/egress contract, routable address windows, complete port/ID/clock metadata, RTL filelist, monitor catalog and source-true graph; prove ordering, errors, reset and real end-to-end accepted transactions. Keep `soc_noc` as a stable logical wrapper if practical. |
| Memory-local Verilog-AXI crossbar → other | **No** | `tools/noc_backends.py` only has the Verilog-AXI executable **standalone memory-crossbar** emitter; `tools/socgen.py` requires it for this scope. `config/interface_contracts.yaml` contains upstream `S_THREADS/S_ACCEPT/M_ISSUE` knobs. | Implement a real alternative crossbar emitter and translate canonical port capacity/route policy to native parameters. Prove asymmetric behavior or fail closed; run sparse/full/negative memory tests. |
| LiteDRAM DDR → other DDR controller | **No** | `tools/socgen.py::validate` fixes DDR controller=`litedram` for the modeled baseline; `tools/ddr_chip.py` requires LiteDRAM output, 32-MiB modeled storage, generated CSR/init/Wishbone/DFI, and regenerated FlooNoC; `tools/full_chip_gen.py` has a special `real_ddr_mode`. | Separate memory **AXI4 target** from controller-specific control/bring-up and passive physical/DFI model probes. Define variant-owned CSR register map, init-ready, reset, address geometry, response ordering and externally verifiable storage. A controller with a different native port needs a protocol shim, not a fake AXI test. |
| HBM behavioral RAM → physical HBM controller | **No** | `config/soc.yaml` names `hisa_hbm` but its default sim backend is `axi_ram`; `config/ip.lock.yaml` notes a vendor PHY/Questa dependency. | Select a viable controller/model, document license/PHY limits, define AXI/config/clock boundary and live model evidence; do not silently replace the behavioral stand-in with an unqualified PHY claim. Track #45. |
| PULP iDMA → different DMA | **No** | `tools/socgen.py` requires `subsystem_types.compute.dma=pulp_idma`; `tools/full_chip_gen.py`, `tools/idma_rtl.py` and `sw/dma/` use specific descriptor/CSR/interrupt behavior. | Preserve abstract `dma.copy` scenario and AXI/data integrity checks; provide a **driver/CSR/descriptor/IRQ adapter**, native source closure and recorded completion semantics. Do not rewrite all directed tests to the new descriptor layout. |
| PicoRV32 or SERV → different CPU | **No** | `tools/socgen.py` enumerates the exact `(ip,bus,adapter)` pairs; `tools/full_chip_gen.py` instantiates dedicated CPU adapters; `tools/chip_bootgen.py` and `tools/cpu_dma_firmware.py` expect current boot/software ABI. | CPU bus shim, reset/interrupt/boot model, compilable firmware ABI and observable CPU instruction/INIT/RUN/CHECK evidence; keep the same run-level action semantics. |
| Ethernet MAC/PCIe bridge replacement | **No** | Full-chip emitters and opt-in firmware modes refer to their current MAC/queue, TLP bridge, CSRs and packet/CQ contracts. | Preserve normalized GMII or interface-level frame events and accepted PCIe TLP/AXI events; provide endpoint-specific descriptors/CSR/host model and a true selected-variant source/monitor inventory. |

The backend registry's `executable` field describes availability of the
**standalone memory-crossbar emitter**, not whether separately written
FlooNoC chip/NoC generators work. Do not use that boolean as proof that a
custom full-chip backend is plugged in. Likewise, a YAML backend name,
reserved RTL port or source-qualified picture does not prove an elaborated
pin connection or accepted transaction.

## Common verification boundary to retain across all testbenches

1. **One regression and stimulus identity:** `tools/regress.py` +
   `config/regression.yaml` select the test and its exact run-local plan.
   All directed and future randomized flows must resolve to the **same**
   `dv/common/scenario.py` action representation; record the selected seed,
   variant, actors, addresses, dependencies and plan hash. No second planner
   or per-IP independent PASS definition.
2. **One action and phase ABI:** `dv/common/test_flow.py` and
   `dv/common/action_events.py` accept checker-verified lifecycle/RTL
   observations. C/SV/Python can use thin language-specific emitters, but
   cannot certify their own hardware completion without passive evidence.
   Existing compile-only and opaque legacy test adoption tiers remain
   accurately labeled under #119.
3. **One passive AXI evidence path:** `dv/common/axi_trace.py` uses existing
   `cocotbext-axi` monitors at actual selected boundary pins.
   `tools/axi_report.py` correlates accepted AW/W/B/AR/R and errors; NoC
   swaps change a **port binding**, not the external AXI handshake criteria.
   Do not introduce a competing custom AXI BFM or reconstruct unknown
   global IDs from arbitrary downstream traces.
4. **One protocol-neutral evidence envelope:** `dv/common/protocol_trace.py`
   and `tools/protocol_report.py` retain vendor-native GMII/TLP/DFI/CSR
   sources and explicit clock domains. Protocol-specific decoders are
   legitimate adapters; duplicate run-report engines are not.
5. **One topology and selected-variant provenance:** the backend must
   produce source-owned port/route/monitor metadata consumed by the
   common visualizer, plus an **elaborated** top/port binding test. Do not
   hand-author a second diagram. Default reserve/tied-off packet engines
   are not equivalent to opt-in wired variants.
6. **One storage and ownership model:** addresses and memory allocations
   derive from `config/soc.yaml` and the shared physical allocator.
   Model-only backdoor actions must have independent frontdoor equivalence,
   quiescence and safe semantics; physical controller probes are scoped to
   the selected backend and recorded as modeled vs observed.

## Cheap source-selection mutation gate

`tests/test_ip_portability_contract.py` validates the **existing configured**
NoC roles from `config/soc.yaml` and asserts that deliberately selecting an
unimplemented NoC backend, DDR model/controller, CPU or DMA raises an
explicit error instead of quietly reusing the default test DUT. This runs
under ordinary `make check-config` discovery and needs no proprietary IP.
It tests **rejection**, not the functionality of any replacement; the
positive RTL/end-to-end gate below remains mandatory.

## Swap acceptance gates (new implementation, not implied by current green CI)

- Mutation of an unsupported backend, controller, CPU, DMA or port width
  must fail **before** expensive simulation with an actionable error, never
  fall back to the default RTL or report a reserved endpoint as attached.
- An explicit backend adapter must publish the complete logical AXI/TLP/
  Ethernet/DDR interface contract: direction, width, ID, outstanding
  budget, address map, clock/reset, filelist/source SHA, decode/response
  semantics, actor and monitor bindings, and modeled-versus-real tier.
- Directed **and** run-seeded randomized tests use the same action ABI and
  original report, with actual INIT/RUN/CHECK, data readback, AXI responses,
  negative routes and ordering. Cross-clock latency requires independently
  measured clock normalization; otherwise label unmeasured.
- The canonical selected-profile 2D diagram comes from its generated
  ports and validated source, **not** hand-coded IP name aliases. The
  physical-bit connectivity gate and separate accepted-traffic gate must
  both pass before claiming a new backend is integrated.
- No need to make *every* backend swappable before the first combined
  Ethernet/DDR/CPU/PCIe acceptance run. But keep the integration flow at
  the abstract boundary and isolate each provider-specific implementation,
  or the next IP replacement will require rewriting all tests.

Related tracked work: [#34](https://github.com/r987r/xezim-hello-world/issues/34)
(shared verification), [#119](https://github.com/r987r/xezim-hello-world/issues/119)
(executable adapter migration), [#46](https://github.com/r987r/xezim-hello-world/issues/46)
(exact selected-variant bit-level connectivity), [#90](https://github.com/r987r/xezim-hello-world/issues/90)
(CSR/firmware ABI), [#35](https://github.com/r987r/xezim-hello-world/issues/35)
(DDR timing/stress), and [#45](https://github.com/r987r/xezim-hello-world/issues/45)
(HBM provider selection).
