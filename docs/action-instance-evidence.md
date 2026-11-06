# DV-EVENTS v2 — additive action-instance evidence

Parent: [epic #34](https://github.com/r987r/xezim-hello-world/issues/34). Depends on the canonical SCN-1 JSON plan from [#79](https://github.com/r987r/xezim-hello-world/issues/79).

This first increment introduces **only a typed event recorder and offline correlation checker**. It neither alters the existing `SOC_FLOW_V1` INIT/RUN/CHECK coordinator nor creates a new BFM, memory allocator, or source of synthetic transaction proof. Existing `test-flow.json`, `axi-events.jsonl`, `axi-transactions.json` and `protocol-transactions.json` remain authoritative.

## Recording

```python
from dv.common.action_events import ActionEventRecorder
from cocotb.utils import get_sim_time

with ActionEventRecorder(plan_bytes, run_dir / "action-events.jsonl",
                         lambda: int(get_sim_time(units="ps"))) as recorder:
    recorder.emit("copy_out", "issued", "python_driver")
    # Existing cocotb BFM / real RTL executes independently here.
    recorder.emit("copy_out", "driver_done", "python_driver")
```

**Neither event proves RTL acceptance.** To add an `accepted` or `completed` action event, use a reference from an *independently captured* row: `{"capture": "axi", "ref": "compute0_local_data.dma:0:123"}`. Its reference must exist in the existing AXI correlator; the event timestamp must equal the row's real accepted-request or B/R-last timestamp. Never fabricate or infer IDs from scenario intent.

A non-AXI VIP such as Ethernet GMII, PCIe TLP, APB, DFI or AXI-Stream can emit `observed` linked to `{"capture":"protocol","ref":"record:12"}` where the indexed record is present in the full `protocol-transactions.json` with `capture_complete=true`. `observed` does not imply completed transaction. Completed VIP transactions can also supply `accepted` and `completed` evidence when real independent start and end timestamps are available.

A `checked` record must link to `{"capture":"scoreboard","ref":"check123"}` and a **separately produced** `independent_action_scoreboard` artifact containing an actual byte-by-byte golden/received comparison and references to completed passive transactions. This PR does **not** implement that independent scoreboard. Hence its action summary must remain **not passed** when such proof is unavailable.

## Analyze an opt-in test artifact

```sh
python3 tools/action_evidence.py \
  --plan .tools/regression/chip-dma-scenario/scenario-plan.json \
  --events .tools/regression/chip-dma-scenario/action-events.jsonl \
  --axi .tools/regression/chip-dma-scenario/axi-transactions.json \
  --protocols .tools/regression/chip-dma-scenario/protocol-transactions.json \
  --out .tools/regression/chip-dma-scenario/action-evidence.json \
  --require-all
```

Only supply `--protocols` when the test has a protocol capture. Likewise `--axi` and `--scoreboard` are opt-in and **never** implicitly faked when absent. Missing or malformed references, duplicate actor claims for the same passive transaction, non-OKAY AXI, overflowed/incomplete captures, out-of-order times and unchecked accepts are errors. `--require-all` also demands all planned action instances issued, even when no independent protocol check exists. Note that **the command can exit zero for valid but unverified evidence**; always inspect the reported `passed` and `status` separately.

## Compatibility and next steps

The v2 row carries `scenario_id`, `plan_sha256`, `action_instance_id`, actor, phase, kind, stage, sequence, simulator timestamp (picoseconds), origin and optional evidence reference. A source-neutral `action-events.jsonl` stream is additive to current test-flow v1; it permits 1,200+ interleaved and repeated actions without the old one-required-step-per-run restriction.

Follow-up PRs (still owned by #34):
- Wire each CPU/host/BFM/SV adapter to this event stream and correlate observed source/target transactions; do not presume driver-only evidence proves transfer completion.
- Add independent byte/packet/descriptor/CQ checker artifacts, then memory allocation/lifetime and quiescence evidence.
- Embed validated action timelines and buffer maps in the **existing per-run** `report.html` / GitHub Pages test explorer; don't make another run dashboard.
- Extend from modeled DDR to real LiteDRAM and combined Ethernet/PCIe only with independently qualified controller/MAC/bridge/DFI/TLP traces.

No new PSS/UVM stack and no changes to PCIe/Ethernet/DDR RTL.
