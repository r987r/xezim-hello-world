# DV-MEM-TRACE — per-run memory lifetimes from the canonical scenario

Part of [epic #34](https://github.com/r987r/xezim-hello-world/issues/34). Reuses `tools/memory_plan.py`, `sw/common/memory_pool.[ch]`, SCN-1 `scenario-plan.json`, SCN-2's optional actual run evidence, and the existing passive AXI correlator. There is **no new allocator, NoC monitor or test runner**.

The first slice is deliberately fail-closed and restricted: the existing CPU/BFM SCN-2 DDR roundtrip is the only scenario whose legacy unnamed CPU allocation mailbox is recognized. The BFM runs **never** prove that C allocations happened. Other canonical scenarios can still show the predicted physical buffer layout, but must be labeled `plan_only_unmeasured` until actual evidence is available.

## Produce a memory-lifetime view

After running the real SCN-2 regressions (PR #84), use:

```sh
python3 tools/scenario_memory_trace.py \
  --plan .tools/regression/chip-cpu-scenario/variant/scenario-plan.json \
  --axi .tools/regression/chip-cpu-scenario/axi-transactions.json \
  --scenario-execution .tools/regression/chip-cpu-scenario/scenario-execution.json \
  --result .tools/regression/chip-cpu-scenario/result.json \
  --out .tools/regression/chip-cpu-scenario/memory-lifetimes.json \
  --report-html .tools/regression/chip-cpu-scenario/report.html
```

For the BFM profile, use `chip-dma-scenario` and its `scenario-plan.json` (not the CPU variant path).

**`--report-html` appends a safe, static memory buffer table to the existing per-run `report.html`**; it does not publish a separate dashboard or infer a PASS. It rejects insertion if the table is already present. The JSON preserves buffer physical addresses as 64-bit hex strings and records planned owners, generation/token, allocation/release action IDs, planned consumers, initialization/check recipes, and individually referenced accepted AXI source-side read/write transactions.

## Evidence rules

- Every buffer must be inside the configured **modeled backing range**; physical address reuse is ambiguous without independently observed lifetime timestamps and therefore blocks AXI attribution. Boundaries use a sorted physical interval index so matching large traces does not require comparing every transaction with every buffer.
- AXI observations must come from `axi-transactions.json` with `capture_bound: true`, no overflow/correlation issues, source initiator role, completed B/R and OKAY response. Each counted access is explicitly labeled **start-address match**; that does not prove a full buffer's bytes were transferred.
- A CPU physical address is labeled `rtl_cpu_mailbox_checked_by_existing_test` **only** if the SCN-2 run and firmware INIT/RUN/CHECK tests passed, `scenario-execution.json` matches the exact canonical plan hash, and the actual observed CPU mailbox addresses match all three planned buffers. This is corroboration by the already existing hardware checker, not a newly inferred allocation.
- The physical addresses in a reset-isolated cocotb BFM run stay `planner_only` even if the iDMA accesses those addresses and the returned data passes. The BFM does not call the C allocator.
- **All generation/token values are always `planner_only`** until real firmware emits and independently verifies token/generation telemetry. Release intent is not proof of CPU/DMA quiescence or actual C `soc_mem_release`; allocated buffers currently remain `retained_at_run_end` in the opt-in scenario. No arbitrary frees are introduced.
- Real LiteDRAM controller/PHY timing is out of scope for this modeled-DDR scenario. Existing independent real DDR-B and DFI tests remain the source of those facts.

## Tested scope and follow-ups

The source-neutral unit suite covers plan-only evidence, CPU and BFM profiles, tampered CPU physical addresses and hashes, incomplete AXI, non-OKAY responses, duplicate allocation tokens, overlapping historical physical buffers, and HTML escaping. The implementation was additionally exercised against both modes' retained [SCN-2 run 42223276288](https://github.com/r987r/xezim-hello-world/actions/runs/42223276288) artifacts, including the large actual CPU AXI trace. That archive test is a manual compatibility check, **not a new real-RTL CI run**.

Next milestones: actual CPU token/generation and release/quiescence telemetry; stage-to-stage memory timeline with v2 action IDs, independent checker evidence and byte/descriptor/CQ scoreboards; embed live lifetimes and protocol backlinks in the unified Pages test explorer. Only tests that actually produce and verify those artifacts should advertise full lifetime proof.
