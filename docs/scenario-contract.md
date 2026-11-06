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
