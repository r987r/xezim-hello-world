# Scenario memory-lifetime evidence

`tools/scenario_memory_trace.py` combines the original `scenario-plan.json`, optional true execution checks and passive AXI capture. It reuses [memory planning](memory-allocation.md) and the existing reporter; it is **not** a memory allocator, DMA engine or new AXI monitor.

## Reproduce for a selected SCN-2 run

```sh
python3 tools/scenario_memory_trace.py \
  --plan .tools/regression/chip-cpu-scenario/variant/scenario-plan.json \
  --axi .tools/regression/chip-cpu-scenario/axi-transactions.json \
  --scenario-execution .tools/regression/chip-cpu-scenario/scenario-execution.json \
  --result .tools/regression/chip-cpu-scenario/result.json \
  --out .tools/regression/chip-cpu-scenario/memory-lifetimes.json \
  --report-html .tools/regression/chip-cpu-scenario/report.html
```

This is the existing **private** runtime scratch convention; published new reports use [canonical identity paths](test-identity.md). Re-run the CLI using the real current run's selected paths if they change under [#139](https://github.com/r987r/xezim-hello-world/issues/139). For the BFM profile substitute `chip-dma-scenario` and its matching original plan/capture. The HTML option adds one safe static table to the existing report, never a second site.

## What may be claimed

- Planned memory regions, ownership, patterns and action dependency lifetimes are visible even before simulation, but marked `plan_only_unmeasured`.
- AXI access attribution requires complete `capture_bound` source-side transactions with accepted B/R, no overflow and an unambiguous physical interval/lifetime match. A matched start address **does not** prove the whole buffer's bytes were transferred.
- CPU allocations are corroborated only when the real SCN-2 CPU mailbox/firmware passes and the source/plan hashes plus physical addresses match exactly. A BFM-run buffer is `planner_only` even if DMA traffic passed.
- Token/generation and release/quiescence remain planned until actual firmware telemetry and independent checks exist. No inferred CPU token from a Python plan; no synthetic memory frees.
- The DDR in these SCN-2 cases is **modeled**. Real LiteDRAM/DFI timing is captured in its separate selected test and cannot be spliced into this run.

Future source-selected token, actor and lifetime timelines are tracked in [#119](https://github.com/r987r/xezim-hello-world/issues/119) and [#34](https://github.com/r987r/xezim-hello-world/issues/34).
