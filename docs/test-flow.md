# INIT/RUN/CHECK and action evidence

The single regression selector (`config/regression.yaml`, `tools/regress.py`) and the existing CPU/host INIT→RUN→CHECK coordinator own execution. Real CPU firmware, host Root Complex, Ethernet peer, PULP iDMA and protocol monitors are **participants**, not separate phase engines.

## Evidence classes and correctness

`test-flow-events.jsonl` captures ordered records with `schema_version`, `seq`, `time_ps`, `phase`, `actor`, `step`, `status` (start/pass/fail), `origin`, and scalar details.

```json
{"schema_version":1,"seq":6,"time_ps":131000,"phase":"run","actor":"host0","step":"bar_write_0","status":"start","origin":"stimulus","details":{"address":"0x12000100","bytes":8}}
```

| Origin | What it means |
| --- | --- |
| `stimulus` | Driver requested an action; **not** proof hardware accepted anything |
| `rtl_observed` / `observed` | Accepted RTL checker phase or observed protocol/bus boundary under the selected capture contract |
| `checker` | Independent expected-vs-actual comparison executed, with result |
| `unmeasured` | Missing, incomplete or unsupported evidence; never inferred as successful |

Correlate C phase markers only after genuine accepted AXI/OKAY MMIO writes. Passive PCIe TLP observation uses upstream `PcieIfFrame.to_tlp()`; do **not** attach an active sink to a live bridge bus or implement another TLP decoder. AXI IDs can be remapped across NoCs, so never claim an ID is globally unique based solely on its numeric value. Exact selected action plans, driver events, protocol observations and independent checks have **distinct** schemas and must match run/source/plan digests.

## Selected regression declarations and artifacts

The existing YAML `report.flow.required_steps` contract records required named phases with optional `required_origins`. Missing, duplicate, out-of-order, unregistered or failed required steps fail closed. A **required expected-negative** outcome is a named condition, not ordinary success. Independent actors can overlap phases; same-tick events are not assigned a fictional total order.

```yaml
report:
  flow:
    required_steps:
      init: [host0.enumerate, host0.init_ack, cpu0.firmware_init]
      run: [host0.bar_roundtrip, host0.run_ack, cpu0.firmware_run]
      check: [host0.check_ack, cpu0.firmware_check]
```

C firmware uses the allocated telemetry sink and `sw/common/test_flow.h`; host/Python uses `dv.common.test_flow.StepRecorder.step()`; the SV checker reports actual observed phase milestones. Use [SCN typed actions](scenario-contract.md) and [action-instance evidence](action-instance-evidence.md) to represent repeated/concurrent actions, IDs, dependencies and resolved seeds. The human-authored intended-flow viewer may show tests **before first run** but cannot create executed evidence or a PASS.

Raw `test-flow-events.jsonl`, normalized `test-flow.json`, optional `scenario-execution.json`, protocol/AXI traces and HTML summaries remain together under the original run identity. A green PCIe host test needs complete matching accepted TLP/AXI/host-byte evidence; a modeled Root Complex callback measures API time, **not** physical PCIe link latency. See [PCIe host acceptance](pcie0-host-phases.md), [unified protocol reporter](protocol-run-reports.md), and [publication constraints](publication.md).

Implementation/migration backlog belongs to [#119](https://github.com/r987r/xezim-hello-world/issues/119) and the [combined epic](https://github.com/r987r/xezim-hello-world/issues/34); do not maintain a separate rollout checklist here.
