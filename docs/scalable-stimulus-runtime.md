# P0: composable SoC stimulus actions across Python, C, and SV

**Status:** design and implementation plan, NOT implemented system-wide. **Owner:** [P0 issue #152](https://github.com/r987r/xezim-hello-world/issues/152); predecessor [#119](https://github.com/r987r/xezim-hello-world/issues/119) closed after partial progress, but its broader legacy migration is not complete. Integration consumers: [#76](https://github.com/r987r/xezim-hello-world/issues/76), [#34](https://github.com/r987r/xezim-hello-world/issues/34).

## Why this is P0

Full-chip test writers must be able to express **what** to do using typed actions, rather than implement each directed case as another dedicated Cocotb script with hard-coded addresses, packet bytes, poll loops and status checks. The *same* actions should drive directed, chained, parallel and randomized cases. Migrate the first new integrations before adding more one-off tests; do not block necessary isolated RTL debugging.

**Merged [PR #149](https://github.com/r987r/xezim-hello-world/pull/149) now uses real CPU0 Config-NoC CSRs and hardware-owned requester descriptors**, rather than direct Cocotb descriptor injection; the merged-head full-chip RTL gate passed. However, the test still assumes 64-byte payloads, fixed SRAM offsets `0x600`/`0x700`, fixed RC host offsets and hard-coded C/host coordination. This is a valid controlled feature milestone, **not** the proposed reusable typed action API. Passive packet-level outbound TLP source correlation is in follow-up [#154](https://github.com/r987r/xezim-hello-world/pull/154), separate from #152's generic runtime.

## Source-backed current state (after merged #149, main `45b0427` at reconciliation)

| Existing authority | What it actually does | What it **does not** prove |
| --- | --- | --- |
| `config/regression.yaml`, `tools/regress.py` | Select sources, engine, variant, acceptance and artifact identity | Internal action execution by every driver |
| `config/stimulus/tests.yaml`, `tools/test_intent.py` | Human-reviewed intended flow, exported pre-run | Execution or hardware activity |
| `dv/common/scenario.py`, `tools/scenario_plan.py` | Resolve one canonical JSON IR with actions, dependency DAG, seed/replay, allocations | Generic device and protocol dispatch |
| `dv/common/action_runtime.py` (merged #146) | Typed Python handler dispatcher for selected actions, currently sequential by phase | Parallel resource scheduling, universal C/SV adapters, RTL acceptance |
| `dv/common/scenario_dma.py` | Existing eight-action SRAM→modeled DDR→SRAM BFM/CPU scenario | Arbitrary multi-protocol composition |
| `tools/memory_service.py`, `tools/memory_plan.py`, `sw/common/memory_pool.[ch]` | Bound memory allocations, owner/lifetime rules, configured access providers | Automatic proof of software allocation/free or DMA drain |
| `sw/dma/dma.[ch]` | Real PULP iDMA descriptor building, CSR submission and polling | PCIe requester submission by itself |
| `dv/common/action_events.py`, `dv/common/test_flow.py` | Action driver events and existing INIT/RUN/CHECK evidence | Independently checked transfers without passive monitors/scoreboards |

**Do not create a second scenario compiler, scheduler authority, source catalog, event format, passive monitor, test viewer or report site.**

## Target architecture

```text
config/regression.yaml                config/scenarios/<scenario>.json
    | exact hardware selection                  | human-authored typed actions
    +-------------------------+----------------+
                              |
                 SCN existing resolver/validator
                 seed, action ID, actor, resources,
                 dependencies, buffer allocations,
                 exact plan/source/config digest
                              |
                   scenario-plan.json
                     SINGLE EXECUTABLE IR
                              |
             existing registered ActionDispatcher
                + resource/dependency extension
                  /            |             \
            Python           C firmware       SV adapter
       cocotbext AXI/PCIe   real CPU CSR      native SV TB
       GMII/RC host model   PULP iDMA        assertions/commands
                  \            |             /
                      actual DUT interfaces
                              |
                 passive AXI/TLP/GMII/DFI/CSR
                         observations
                              |
                independent action scoreboard
                  expected vs actual bytes,
                  completion/visibility, status
                              |
          original action-events / test-flow / reports
                        Test Runs UI
```

INIT prepares actors, allocates owned resources, configures legal endpoints and registers checkers. RUN dispatches ready actions; dependent actions wait for **required hardware-observed** readiness, not simply a Python function returning. CHECK waits for quiescence, compares independent bytes and completes releases. Existing CPU0 and host phase coordinators remain in control.

### Actions and capabilities

Use versioned, strict, typed parameters and explicitly named actor capabilities. Initial extensible registry:

| Action | Inputs | Dispatcher / verifier |
| --- | --- | --- |
| `memory.allocate`, `memory.release` | region, size, alignment, owner, lifetime | Existing allocation service; prove real frees separately where applicable |
| `memory.initialize`, `memory.check` | buffer handle, pattern/golden origin, access policy | Existing providers and independent frontdoor/backdoor qualification |
| `dma.copy`, `dma.wait_idle` | real engine, src/dst handles, length, descriptor ID | C/PULP iDMA or authorized Cocotb BFM; AXI/descriptor/IRQ/busy passive checks |
| `pcie.mem_write` | requester, device buffer, host buffer, len/tag | Pinned upstream requester/real CSR or queue; accepted TLP and host-visible bytes |
| `pcie.mem_read` | requester, host source, device destination, len/tag | Real MRd/completions; completion length, tag and data integrity |
| `ethernet.receive`, `ethernet.transmit` | queue, frame bytes, destination/source, FCS policy | GMII VIP, RTL Ethernet queue/DMA and CQ/AXI observation |
| `host.mem_write`, `host.mem_read` | host/BAR target and bytes | Existing modeled Root Complex, never bypasses required device transport |
| `cpu.invoke`, `csr.write`, `csr.poll` | CPU actor, registered operation/CSR, timeout | Real firmware/config-fabric access, no direct DUT pin substitution for CPU-owned actions |
| `event.emit`, `event.wait` | queue, cookie, dependencies, credits, timeout | Real mailbox/event-queue hardware once qualified; otherwise unsupported, not simulated as hardware |
| `scoreboard.check` | action/result IDs, source/destination golden identity | Independent monitor + actual byte/completion comparison |

A missing or unsupported handler **fails selection before simulation**. No generic 'execute any Python expression' actions.

### Runtime scheduling, concurrency and lifetime rules

- Resolve all `choose` and `randint` from a **per-run selected** seed, not a fixed universal seed. Archive the exact resolved graph and allow explicit replay by seed/source revision or immutable plan.
- Enforce dependency DAG (including no cycles or backward-phase edges), typed resource ownership, disjoint regions and queue credits. Permit independent actions concurrently; serialize or reject conflicting mutations, e.g. overlapping buffer writes or two drivers controlling the same interface.
- Distinguish `driver_issued` from `protocol_accepted`, `device_completed`, `independently_checked`, and `unmeasured`/failure. A driver's `driver_done` is **never** independent RTL acceptance.
- Wait for real DMA descriptor retirement and outstanding reads/writes before `memory.release`, and before another agent reuses the buffer. A predicted `consumers_quiesced` field is intent, not measurement.
- Posted PCIe MWr has no completion TLP; use independently observed host memory visibility/drain rather than interpreting write-descriptor ready as host completion. MRd requires matching real completion TLP bytes and tags. For AXI, require source-captured accepted AW/W/B or AR/RLAST and valid completion semantics.
- Support negative outcomes (unsupported request, timeout, malformed response, early release, duplicate completion, wrong tag/bytes, full queue) with exact expected-failure identity, no generic FAIL→PASS.
- Never infer measured latency from planned hop topology or host-model API timing; preserve source/target clock identity and report unmeasured stages honestly.

### Single cross-language execution ABI

Each executable action includes `scenario_id`, `plan_sha256`, `action_instance_id`, `actor`, `phase`, `kind`, typed `args`, `depends_on`, `expected_result_id`, resource lifetime, and required completion condition. Python/C/SV receives **the same resolved action instances**, not a separately hand-written equivalent sequence. Generated C headers/SV packages are build artifacts from the selected plan, not checked-in duplicate YAML/JSON. Any firmware action telemetry must be correlated against accepted CPU MMIO writes and real bus observations.

Keep additive `action-events.jsonl`, existing `test-flow.json`, and existing original passive AXI/protocol files. The action-correlator/scoreboard reads those files by stable transaction references; never let the stimulus driver certify its own 'independently_checked' stage. The run viewer shows planned intent even after failure but only qualifies execution from real bound action evidence.

## Illustrative composed source (NOT currently executable)

```yaml
scenario: ethernet_rx_to_host
seed: auto                 # resolved and archived before DUT starts
actions:
  - {id: ddr, phase: init, op: memory.allocate, region: memory0.ddr0, bytes: 2048}
  - {id: device, phase: init, op: memory.allocate, region: pcie0.sram, bytes: 2048}
  - {id: host, phase: init, op: memory.allocate, region: host.ram, bytes: 2048}
  - {id: rx, phase: run, op: ethernet.receive, queue: rx0, dst: ddr, payload: packet0}
  - {id: stage, phase: run, op: dma.copy, engine: compute0.dma, src: ddr, dst: device, after: [rx]}
  - {id: write, phase: run, op: pcie.mem_write, src: device, dst: host, after: [stage]}
  - {id: visible, phase: run, op: pcie.wait_write_visible, after: [write]}
  - {id: check, phase: check, op: scoreboard.check, buffer: host, expected_from: rx, after: [visible]}
  - {id: free, phase: check, op: memory.release, buffers: [ddr, device, host], after: [check], require_quiescent: true}
```

This example is *design syntax only*. The current canonical compiler accepts JSON with different typed fields. If future YAML is adopted, it must compile to that same IR, with no second source of truth. Ethernet packet header is **not** a hidden control command: configured RX queue/classification controls routing. The first Ethernet MVP has one RX and one TX queue; do not invent additional queue behavior.

## Delivery and exact-head qualification (all tracked by #152)

1. **M0 — documentation and issue hierarchy:** P0 contract, index, explicit #34/#76 link, reviewed existing/new distinctions.
2. **M1 — scheduler and action registry:** extend existing dispatcher to support resource/hazard-aware concurrent actions, timeouts and capability validation; independent unit/negative tests.
3. **M2 — C/Python/SV source sharing:** compile one resolved selection to C/SV and Python adapter arguments; ensure real cross-language action events correlate to the selected plan, not hardcoded test values.
4. **M3 — migrate #76 to typed actions:** CPU0's actual Config-NoC requester CSR and real C/iDMA→PCIe→host DMA (and reverse MRd) passed in merged #149. Remaining: source-selected, resource-parameterized typed actions shared with C/Python/SV, distinct passive packet-level AXI/TLP/host checker evidence, and randomized boundary tests. Keep direct descriptor driving only in the isolated requester unit test.
5. **M4 — migrate #34 first combined flow:** the one-run Ethernet GMII→real DDR/DFI→CPU/iDMA→PCIe BAR host milestone passed and #34's scoped MVP is closed. Remaining: compile that directed transfer from the common typed action plan, verify independent action-instance evidence, then compose an alternate direction with the same handlers; a combined RTL PASS alone is not typed-action migration.
6. **M5 — random/concurrent replay:** variable seed, alignment, length, queues, cross-4KiB transfers, multiple actors, stalls, outstanding tags, scoreboard/correct negative tests; preserve exact seed and sources.
7. **M6 — gradual legacy retirement:** migrate existing opaque C/Python/SV/standalone-memory drivers in test families, remove only truly migrated entries from `config/runtime_migration.yaml`, retain failure reproduction, exact-head CI and report gates.

**Merge rules:** documentation is not implementation. The first end-to-end test must not claim canonical execution without real typed dispatch/accepted/completed/checked evidence; keep #76 open for its advanced qualification and respect #34's closed, narrowly scoped MVP status. A PR may add a temporary, explicitly owned and reviewed exception while hardware is being brought up, but this must not be treated as closure of #152.
