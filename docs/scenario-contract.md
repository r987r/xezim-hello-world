# SCN-1: Canonical SoC scenario intent contract

Parent: #79, #34. This is a scenario **intent compiler**, not hardware execution or a second INIT/RUN/CHECK coordinator.

## Generate a source-neutral scenario plan

Run: python3 tools/scenario_plan.py --scenario config/scenarios/dma-roundtrip.json --soc config/soc.yaml --out .tools/scenarios/dma-roundtrip/scenario-plan.json --source-revision $(git rev-parse HEAD)

The example uses one SRAM -> modeled DDR -> SRAM DMA roundtrip with explicit INIT, RUN and CHECK action dependencies. This does not exercise a real DMA/CPU, change RTL, or count as a passed simulation.

## Schema v1

- Root fields: schema_version=1, scenario_id, seed (unsigned 32-bit), variant (boot_live or dma_only), actors and actions.
- Actions require unique action_instance_id, kind, actor, phase and typed args; optional depends_on, parent_action_id and expected_result_id. Missing result IDs are derived from instance IDs.
- Supported kinds: memory.allocate, memory.initialize, memory.check, memory.release, dma.configure, dma.copy, dma.wait_idle.
- Dependency graph remains a DAG; independent actors can run concurrently. Same-region physical allocations require an ordering edge. All buffer readers require causally preceding writes; overlapping read/write and write/write hazards fail closed.
- Memory planning reuses tools/memory_plan.py and the actual modeled region bounds from config/soc.yaml. It never initializes cold SRAM. CPU direct DDR/HBM dereference is rejected. Allocation token/generation and LIFO release semantics follow the existing C memory pool.
- A release requires dependencies on all consuming actions plus consumers_quiesced=true. This is an intent precondition, NOT observed RTL quiescence proof.
- INIT and CHECK patterns have explicit kind/seed and access policy. Execution adapters must independently prove observed bytes and protocol handshakes.

## Deterministic random and replay

Use JSON objects of the form {"choose":[64,128,256]} or {"randint":{"min":1,"max":255,"step":1}} in action arguments.
The pinned sha256-rejection-v1 algorithm hashes ["soc-scenario-random-v1",seed,action_instance_id,argument_path,nonce] as canonical newline-terminated JSON and maps an unbiased 256-bit candidate into the domain. Identical inputs produce byte-identical output. A change to unrelated action ordering does not change another action's random choices.
Manifest provenance includes authoring-spec hash, SoC config hash, random algorithm, resolver version and optional real source-revision SHA. Execution evidence and simulator remain null, explicitly, until supported by actual simulation.

## Next stage: SCN-2

The Python cocotb BFM adapter and freestanding CPU0 C adapter should consume the SAME resolved plan and produce independently corroborated observed AXI/CQ/byte evidence; never attach a BFM to live CPU response ports. Add SV adapter examples without replacing existing checkers or phase engine. Epic #34 owns event v2, allocation visualization, independent scoreboard and linked protocol reports.

Ethernet #73, DDR-B #74 and the NoC same-ID fix are independent tracks; SCN-1 must not modify their RTL or shared generators.

## SCN-2: real CPU C and reset-isolated BFM adapters

- One resolved source-neutral plan: `config/scenarios/cpu-bfm-ddr-roundtrip.json`.
  The SCN-2 adapter accepts **only** the exact supported 8-action single
  SRAM -> modeled DDR -> SRAM flow; unknown kinds, different byte recipes,
  altered buffers or reordered dependencies fail closed. General scenario
  kinds and more complex concurreny remain future work.
- `dv/common/scenario_dma.py` materializes identical canonical intent JSON
  and a generated `scenario_dma_contract.h` in each opt-in regression's
  own ignored `.tools/regression/` output. Both execution profiles preserve
  the same `plan_sha256`, action IDs, physical addresses, pattern and
  length. Intent has `execution_evidence: null` permanently.
- `chip-cpu-scenario` compiles actual RV32I CPU0 C firmware (not a Python
  substitute) with the generated header, loads via the normal immutable flash
  ROM hook and coordinates with existing INIT/RUN/CHECK. It uses real
  `soc_mem_alloc`, actual CSR writes, PULP iDMA descriptors, IRQ and
  descriptor writeback, and checks exact returned SRAM bytes. The host
  checker independently decodes accepted DMA AR/AW and CPU allocation
  MMIO telemetry. No data BFM drives CPU/DMA response ports.
- `chip-dma-scenario` holds CPUs in reset and uses **existing authorized**
  CPU0 data/config AXI BFMs to write source SRAM and descriptors via real
  FlooNoCs; the real RTL DMA copies to DDR and returns to SRAM. BFM compares
  actual accepted AXI reads and exact payload/descriptor data. The original
  `chip-dma` two-engine stress regression still runs independently.
- Each test produces `scenario-execution.json` only AFTER actual observed
  CPU/BFM and independent AXI evidence checks pass; this is not part of
  `scenario-plan.json`. The normal `axi-events.jsonl`, correlator and
  `report.html` remain the canonical transaction proof.

Run the focused contract tests with:
```sh
python3 -m unittest tests.test_scenario_plan tests.test_scenario_dma -v
```

Run the **real RTL** with the established pinned NoC/iDMA/Verilator
dependencies already installed (as in the PR's `dv-scenario.yml` workflow):
```sh
python3 tools/regress.py scenario
```

Check both runs' `scenario-execution.json` plan hashes match each other
and each run's own intent manifest. The CI job checks the two RTL gates
before reporting success. These profiles intentionally use fast modeled DDR,
not a claimed real DDR4/PHY timing model; DDR-B remains an independent track.

### Pending
This is a narrowly scoped 8-action executor, not a fully generic C/SV
interpreter. A generic C-code-generation contract, SV driver, cross-protocol
randomized sequencing and v2 timeline/scoreboard visualization remain
separate follow-on work under issue #79 / epic #34. SCN-2 must not be marked
verified until the exact PR head's CPU C and BFM RTL CI jobs pass.
