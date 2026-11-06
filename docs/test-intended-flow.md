# Planned test flow first — INIT / RUN / CHECK

Parent: [verification epic #34](https://github.com/r987r/xezim-hello-world/issues/34).

Every configured regression now has an **intended flow** entry on the existing GitHub Pages **Test runs** page. Select any target, including a target with no CI artifacts, to see what the test definition says it plans to do.

The view is intentionally **not an evidence or PASS/FAIL report**. It is available without simulating and without an AXI, TLP, GMII, DFI, CPU mailbox, test-flow or scoreboard event.

- For tests with `report.flow.required_steps`, the existing ordered INIT/RUN/CHECK milestones (actor.step) appear without requiring `test-flow.json`.
- For SCN-2 CPU/BFM tests, the scenario source in `config/scenarios/cpu-bfm-ddr-roundtrip.json` contributes each action, actor, phase, dependencies, size/pattern/addresses and expected-result ID where authored. The source scenario is **not** the replay-resolved random output or actual runtime history; its configured seed and case are shown.
- For tests with no detailed `report.flow`, the view still shows all three phases and explicitly says the detailed actions are **not declared**. It displays the known test top/module, scope context, and exact runner acceptance or expected-failure rule. It **does not invent** setup, stimulus, phase checks or fake successes.
- Every test can be opened via **View flow** in the configured catalog; every recorded result also gets a **View intended flow** button. Where a verified run exists, a separate link opens the original report and its optional measured step/AXI/protocol debugging evidence.
- Where an original per-run report is published, the trusted publisher also inserts the known intended flow (and a `test-intent.json` metadata artifact) independently of any measured flow events. This applies to runs with no AXI collector and to protocol-only reports as well.

The static publisher uses the same `config/regression.yaml` test catalog that feeds the automatic test discovery; new tests appear automatically. It does **not** fabricate detailed per-test actions when a future test lacks declared `flow.required_steps`; those tests should add their own intent metadata as they are implemented. The source catalog is labeled as the **current repository definition**, not an assertion about historical CI revisions.

## Verification and next increments

`python3 -m unittest tests.test_test_intent tests.test_scenario_plan -v`

The CI suite enumerates every regression target, tests PCIe multi-actor phase definitions, SCN actor/action/dependency metadata, negative acceptance rules, no-evidence catalog behavior and safe HTML escaping.

**Still to do:** enrich every non-instrumented test with explicit source-authored detailed phase and stimulus metadata, then show per-action dependency DAG/timeline for parallel steps rather than only a textual ordered/parallel list. Evidence links to accepted transactions are a separate debugging enhancement. Keep the view useful and truthful even when execution fails or has never started.
