# SCN-3: SystemVerilog action contract and driver-event ABI

This is the small SV-facing complement to [#79](https://github.com/r987r/xezim-hello-world/issues/79). The existing `config/regression.yaml`, `dv/full_chip/test_boot.py` INIT/RUN/CHECK coordinator, and `dv/common/test_flow.svh` remain authoritative. **No new UVM or Accellera PSS runtime is introduced.**

The SV adapter is **generated from the same resolved, canonical `scenario-plan.json`** consumed by the Python and real CPU C scenario adapters. The package exposes stable scenario ID and plan SHA-256, typed action-instance identity, actor, kind, phase, expected-result ID, and flattened primitive arguments via `scn_text_arg(index, key)` and `scn_uint_arg(index, key)`.

## Generate, compile and inspect the smoke contract

```sh
python3 tools/scenario_plan.py \
  --scenario config/scenarios/dma-roundtrip.json \
  --soc config/soc.yaml \
  --out .tools/scenario-sv/scenario-plan.json

python3 tools/scenario_sv.py generate \
  --plan .tools/scenario-sv/scenario-plan.json \
  --out .tools/scenario-sv/soc_scenario_contract_pkg.sv

verilator --binary --timing -Wno-fatal \
  --top-module test_scenario_sv_adapter \
  --Mdir .tools/scenario-sv/obj \
  -o scenario_sv_smoke \
  .tools/scenario-sv/soc_scenario_contract_pkg.sv \
  dv/common/test_scenario_sv_adapter.sv

.tools/scenario-sv/obj/scenario_sv_smoke > .tools/scenario-sv/smoke.log

python3 tools/scenario_sv.py audit \
  --plan .tools/scenario-sv/scenario-plan.json \
  --log .tools/scenario-sv/smoke.log \
  --out .tools/scenario-sv/sv-driver-events.json
```

The generated SV package provides `soc_scenario_contract_pkg::scn_emit_driver(index, stage, sim_ticks)`. Allowed stages are exactly `issued` and `driver_done`. A bench can use these events around a **real** bus driver, but may only claim *driver progress*, not that a target has accepted, completed or independently checked traffic.

The parser requires the exact plan SHA and scenario identity; it rejects unknown action IDs, phase mismatches, malformed records, duplicates, driver-DONE without issue, and time reversal within one action. Independently interleaved actions are legal. The output is **`kind: soc_scenario_sv_driver_events`, `status: driver_log_unverified`, `rtl_evidence: null`**. It is deliberately **not** a test pass or independent AXI/PCIe/GMII protocol proof.

## Scope and next integration

This adapter is not a general SV driver implementation. A component-specific SV BFM can dispatch based on `scn_action_kind()`, `scn_action_actor()`, `scn_action_phase()` and primitive args; it remains responsible for the proper bus protocol and RTL simulation lifecycle.

The next step belongs to active runtime [#152](https://github.com/r987r/xezim-hello-world/issues/152): add a versioned **action-instance event recorder** joining `issued`/driver-completed evidence with **independently accepted** AXI/TLP/GMII events and check verdicts, with separate plan-vs-observed provenance. A `SOC_SCN_SV_V1` line must never fill an `rtl_observed` field. The SCN-3 compiler performs no live NoC or real LiteDRAM testing; the independent CPU/BFM and DDR regressions remain their own CI gates. The pure SV smoke verifies only syntax, ABI and deterministic driver-event formatting.

Constraints: v1 scalar SV arguments include printable ASCII strings, unsigned 64-bit integers and booleans. Nested objects flatten to dotted field names (e.g. `pattern.seed`). Unsupported lists/negative values fail closed and need a future typed ABI extension. Maximum 4,096 actions per generated package to avoid unbounded compile-time code generation.
