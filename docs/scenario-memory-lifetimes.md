# Scenario memory-lifetime evidence

`tools/scenario_memory_trace.py` combines the original `scenario-plan.json`, optional true execution checks and passive AXI capture. It reuses [memory planning](memory-allocation.md) and the existing reporter; it is **not** a memory allocator, DMA engine or new AXI monitor.

## Reproduce for a selected SCN-2 run

```sh
RUN="path/to/the/exact/canonical/CPU/run"
python3 tools/scenario_memory_trace.py \
  --plan "$RUN/variant/scenario-plan.json" \
  --axi "$RUN/axi-transactions.json" \
  --scenario-execution "$RUN/scenario-execution.json" \
  --result "$RUN/result.json" \
  --out "$RUN/memory-lifetimes.json" \
  --report-html "$RUN/report.html"
```

Use the exact canonical directory printed by the runner under `.tools/runs/`;
do not select by latest timestamp or combine captures from different runs.
For the BFM profile use that run's own directory and its top-level
`scenario-plan.json`. The HTML option adds one safe static table to the
existing report, never a second site.

## What may be claimed

- Planned memory regions, ownership, patterns and action dependency lifetimes are visible even before simulation, but marked `plan_only_unmeasured`.
- AXI access attribution requires complete `capture_bound` source-side transactions with accepted B/R, no overflow and an unambiguous physical interval/lifetime match. A matched start address **does not** prove the whole buffer's bytes were transferred.
- CPU allocations are corroborated only when the real SCN-2 CPU mailbox/firmware passes and the source/plan hashes plus physical addresses match exactly. A BFM-run buffer is `planner_only` even if DMA traffic passed.
- Token/generation and release/quiescence remain planned until actual firmware telemetry and independent checks exist. No inferred CPU token from a Python plan; no synthetic memory frees.
- The DDR in these SCN-2 cases is **modeled**. Real LiteDRAM/DFI timing is captured in its separate selected test and cannot be spliced into this run.

Future source-selected token, actor and lifetime timelines are tracked in active P0 [#152](https://github.com/r987r/xezim-hello-world/issues/152) and memory service [#39](https://github.com/r987r/xezim-hello-world/issues/39).
