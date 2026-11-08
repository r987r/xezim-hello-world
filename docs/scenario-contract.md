# Canonical source-selected scenario actions (SCN)

The existing `tools/scenario_plan.py` resolves a versioned action DAG using the source-owned SoC memory configuration. It is an **intent compiler**, not a second simulator or INIT/RUN/CHECK coordinator. The shared scenario executable and observed-evidence formats are defined separately: a valid plan never implies hardware PASS. [#119](https://github.com/r987r/xezim-hello-world/issues/119) tracks the remaining general action-adapter migration.

## Reproduce and replay

```sh
python3 tools/scenario_plan.py \
  --scenario config/scenarios/dma-roundtrip.json \
  --soc config/soc.yaml --out .tools/scenarios/dma-roundtrip/scenario-plan.json \
  --source-revision "$(git rev-parse HEAD)"
python3 -m unittest tests.test_scenario_plan tests.test_scenario_dma -v
python3 tools/regress.py scenario
```

The resolved plan records `schema_version=1`, `scenario_id`, unsigned seed, execution variant, actors, typed action instances and dependency edges. Actions include memory allocate/initialize/check/release and DMA configure/copy/wait-idle, with stable IDs, chosen parameters, expected result IDs and resource lifetimes. Hazardous unordered overlapping writes, source reads without causal writes and premature allocation release fail closed. A declared consumers-quiesced dependency is still **intent**, not observed DMA idle.

Random `choose` and `randint` values use a versioned SHA-256 rejection-sampling resolver keyed by seed, action instance and argument path. Replay must reproduce chosen values without imposing one fixed seed across all tests. `scenario-plan.json` carries source/spec fingerprints and no simulated PASS evidence.

## Actual SCN-2 test adapters

The two selected regressions, `chip-cpu-scenario` and `chip-dma-scenario`, consume the **same** eight-action [SRAM→modeled DDR→SRAM](../config/scenarios/cpu-bfm-ddr-roundtrip.json) source and resolved memory plan:

- **CPU:** real PicoRV32 freestanding C firmware allocates SRAM, submits/polls real PULP iDMA via Config NoC, checks readback and emits independently correlated firmware/AXI evidence. CPU0 data/config pins are **not** BFM-driven during this run.
- **BFM:** CPUs are held in reset; the explicitly authorized CPU0 AXI BFMs initialize source/descriptor SRAM and drive the same actual DMA RTL. The independent read/checker uses accepted AXI/data.
- Only after actual execution and source-compatible passive checks pass may a separate `scenario-execution.json` record completed action IDs and selected-plan hash. Neither evidence nor a shortcut to PASS is written into `scenario-plan.json`.

These are narrow action adapters, not a generic C/SV/Python interpreter for all 28 regressions. Do not create another scenario engine, duplicate the action graph in a test's prose YAML, or claim all legacy internal drivers have migrated. See [test-flow evidence](test-flow.md) and [memory lifetimes](scenario-memory-lifetimes.md).
