# Canonical test-flow step evidence (schema v1)

The existing [regression YAML](../config/regression.yaml) and
`tools/regress.py` remain the **only** test-selector/engine.
The existing `dv/full_chip/test_boot.py` and SV/ROM CPU coordinator remain
the **only** INIT → RUN → CHECK lifecycle. A PCIe root complex or a future
Ethernet peer is a participant implementing actions, **not** a new phase engine.

## What a recorded step means

Each test action has: `phase` (`init`, `run`, `check`),
`actor` (CPU, RTL engine, host/VIP), `step` (stable routine/operation),
`status` (`start`, `pass`, `fail`), `origin`
(`stimulus`, `observed`, `rtl_observed`, `checker`),
`time_ps` (sim time), monotonic `seq`, and scalar `details`.

An example event (one JSONL line):

```json
{"schema_version":1,"seq":6,"time_ps":131000,"phase":"run","actor":"host0","step":"bar_write_0","status":"start","origin":"stimulus","details":{"address":"0x12000100","bytes":8}}
```

It is essential that:
- **Stimulus issued** does not imply real RTL acceptance. Real acceptance
  must come from separately captured AXI AW/W/B, PCIe completion or target
  accepted-SRAM evidence.
- **RTL observed** comes only from accepted bus writes, or a conditional
  assertion in the actual SV checker. Compiler and model-only events never
  become real NoC traffic just by naming them.
- **Checker pass** means a checker executed; it must contain independent
  expected-vs-actual comparisons, and no result is green merely because
  a routine returned.
- Every expected step is explicitly listed in `report.flow.required_steps`
  in the **same** regression test YAML. Unknown, duplicate, malformed,
  incomplete, out-of-order, or failed steps fail the run.
- Raw `test-flow-events.jsonl`, normalized `test-flow.json` and
  `test-flow.html` appear alongside the existing `axi-events.jsonl`,
  `axi-transactions.json`, `protocol-transactions.json`, and
  `report.html`; there is no separate site or database.

## Implemented sources

| Producer | API / transport | Origin of proof |
| --- | --- | --- |
| Python stimulus / Root Complex | `dv.common.test_flow.StepRecorder.step()` context | `stimulus`, with failure captured even on exceptions |
| Cocotb memory/check code | same context, `origin="checker"` | actual assertion result |
| Real CPU firmware and SystemVerilog checker | generated `SOC_FLOW_V1` markers printed on accepted SV checker phase events | `rtl_observed` (phase start and pass) |
| Native C firmware (prepared reusable ABI) | `sw/common/test_flow.h`, `soc_flow_emit(volatile uint32_t *sink, ...)` | **only** after correlated accepted AXI write with OKAY response; optional `report.flow.firmware_mmio` codebook |
| Ethernet/IP/other external actors | same Python step context; their VIP monitor reports independently through `dv/common/protocol_trace.py` | events are `stimulus`; real packets/completions require VIP/RTL evidence |

The PCIe-host (combined CPU/iDMA + modeled DDR + host) and separate CPU C/iDMA
scenarios opt into the strict step-flow gate.
The generic API and cross-language adapters are implemented and unit-tested;
**other existing tests have not all been instrumented**. Their existing
capture/results remain unchanged. Add the `report.flow` contract to each
as it is migrated, and make the contract required before calling that
scenario's step coverage complete.

## Declaring a test in the existing YAML

```yaml
report:
  axi:
    scope: dut.u_noc
    clock: clk
    reset: rst_n
    catalog: gen/supernoc/axi_monitors.json
  flow:
    required_steps:
      init: [host0.enumerate, host0.init_ack, cpu0.firmware_init]
      run: [host0.bar_roundtrip, host0.run_ack, cpu0.firmware_run]
      check: [host0.check_ack, cpu0.firmware_check]
```

Flow `required_origins` optionally binds each required `actor.step` to its
expected provenance (`stimulus`, `observed`, `checker`, or
`rtl_observed`). PCIe0 and CPU C/iDMA require origins explicitly; a Python
stimulus event cannot masquerade as a firmware/RTL completion. A CHECK step
observed before RUN, or RUN after CHECK, fails **for the same actor** when
it occurs on a later simulator tick. Independent CPU, host and SV checker
actors may legitimately have overlapping phases; same-tick boundaries are
not assigned a fabricated global ordering. Start and finish of a step must
have the same origin.

For the two real-CPU tests, `report.axi.required_complete: true` rejects
outstanding AXI transactions at capture close, including the final firmware
status store. The testbench allows a bounded drain interval, but no successful
capture may omit an AXI B or final RLAST.

The full PCIe0 definition lists every one of the four BAR writes and reads
individually, not just `bar_roundtrip`. Missing an expected operation fails
CI. The plan is validated before the HDL build. Test writers add the
corresponding `StepRecorder.step` around *each* routine invocation.

For a native C program, the same YAML can optionally declare:
```yaml
  flow:
    required_steps:
      init: [cpu0.setup]
      run: [cpu0.dma_start, cpu0.dma_end]
      check: [cpu0.dma_check]
    firmware_mmio:
      monitor: compute0_local_data.cpu
      address: '0x10000f00'
      actors: {'7': cpu0}
      steps: {'101': dma_start, '102': dma_end, '103': dma_check}
```
This is an example only: the trace-word sink address must be allocated,
reserved and nonoverlapping through the existing SRAM memory planner for
the particular test. The software marker consists of a 32-bit
`0xF1`-prefixed code with phase, status, actor and step IDs; names resolve
through the YAML codebook. An unobserved software emit is **never accepted**.

## PCIe0 full-chip ownership

The CPU0-generated firmware, not Python forcing, writes handshake words
into real `pcie0.sram` over Compute0 local → global data → PCIe0 local
NoCs. The modeled host RC enumerates and acknowledges the same words over
BAR0 → real pinned TLP-to-AXI bridge → PCIe0 local NoC. The common CPU boot
test owns phase order. `dv/pcie0/host_adapter.py` owns only host actions.
The full-chip SV checker prints observed firmware start/pass steps.
All stages are bound to the same regression YAML plan and output directory.

### PCIe TLP traffic in the same explorer

The opt-in `chip-pcie-host` run declares `pcie0.rx_req` and
`pcie0.tx_cpl` in its existing `report.protocols.sources`. A passive
accepted-beat observer at the real bridge interface reconstructs the
upstream `PcieIfFrame` and invokes its `to_tlp()` method, which uses
`cocotbext-pcie` for the actual PCIe header parsing. It must **not**
instantiate a second `PcieIfSink` on the live bus: that class drives
`READY` and would contend with the real bridge. The adapter never drives
pins, never implements an independent TLP decoder and never changes the
NoC or PCIe verification stimulus.

The shared `dv/common/protocol_trace.py` reporter records accepted packet
start/end timestamps, PCIe tag/requester, address/length/byte-enables,
completion status, payload and matching request-to-completion delay.
`tools/protocol_report.py` merges these with *existing* AXI monitor rows;
`protocols.html` filters by protocol, monitor, time, status, and payload.
`protocol-events.jsonl` and `protocol-transactions.json` accompany the
existing AXI and DDR/memory reports. A green PCIe-host run requires accepted
memory read/write TLPs, actual completions, matched outstanding tags, and
closed, complete monitor streams. Reported TLP timings are bridge-port
observations, **not** PCIe PHY/LTSSM or wire latency; the Root Complex and
link remain modeled. PCIe config enumeration happens inside the upstream
Root Complex/Endpoint model and is not falsely counted as bridge TLPs.


The original CPU → PCIe0 SRAM DecodeError was a genuine missing destination
from compute-local `global_out`. PR #53 now generates peripheral SRAM
routes from the shared `compute_like` set and includes a negative guard.

## Planned rollout / no false coverage

Before claiming *all tests* have uniform step coverage, migrate:
1. Existing BFM `chip-boot` and other CPU tests to step contexts
   while preserving their physical region allocator and telemetry checks.
2. Standalone super-NoC, DDR, HBM and memory tests: one recorded start/pass/fail
   around every read/write/doorbell/check, plus actual monitor evidence.
3. Ethernet0 RX/TX: device queue programming, host packet generation, received
   frame, DMA descriptor transaction, completion and content check, each a
   step with independent GMII/VIP and AXI evidence.
4. Negative tests (missing/late ack, wrong phase, corrupted data): a
   *deliberate expected error* must be distinguished from unexpected
   step failure, using the existing `expect_failure` contract. Avoid
   reporting deliberate failures as an ordinary successful CHECK.

The flow reporter is a **reporting and acceptance layer**, not a new
protocol VIP, new DMA engine, or alternate test coordinator.

## PCIe, NoC, SRAM and host timing evidence

`tools/pcie_latency_report.py` uses the **existing** PCIe TLP, AXI and
SRAM monitor rows; it does not sample new pins or infer latency from RTL
parameters. The `chip-pcie-host` test fails if the observed request/tag,
completion, AXI initiator, SRAM target, payload or write strobes disagree.
Unique local transactions are matched by address, sequence and captured
timestamps, never by a fabricated global AXI ID across NoCs. Nonunique
matches are an explicit error rather than a guessed path. The report
`traffic-latency.json` is embedded as a stage summary and BAR test-vector
table in the **existing** `protocols.html` explorer, linked from
`report.html`. All latency values and clocks derive from the same
simulation capture, and the final AXI/protocol report metadata records the
actual INIT/RUN/CHECK status after cross-language checks, not the preliminary
`unmeasured` placeholder.

Stages for PCIe reads are: accepted TLP request EOP to bridge AXI AR,
bridge AXI AR to SRAM AR, SRAM AR to RLAST, SRAM RLAST to bridge AXI RLAST,
and bridge AXI RLAST to completion TLP EOP. The sum must equal TLP
request-to-completion time. Write TLPs are posted, so report accepted
TLP-to-AXI B time, **not** a nonexistent PCIe write completion. Separate
`host0.bar_read_N` flow spans measure the modeled Root Complex API read
callback, not real link/PHY/LTSSM or physical host latency. DDR/HBM timings
belong to their actual memory-controller/DFI reports and are not silently
ascribed to the PCIe SRAM target.

## Verified initial PCIe and DDR-model host flow

[PCIe CI #42134213227](https://github.com/r987r/xezim-hello-world/actions/runs/42134213227)
passed the real bridge, full-chip CPU/iDMA/host scenario and the separate
CPU C/iDMA scenario. The combined run's 27 required flow steps completed
with zero issues. The accepted traffic captured 3,741 matched PCIe read
TLPs and completions, 8 posted writes, and 47,864 completed AXI transactions.
Its reported TLP read latency is min 130 ns, avg 130.083 ns, max 200 ns.
See [PCIe initial integration and model limits](pcie0-host-phases.md).
