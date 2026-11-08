# AXI traffic capture and per-test run reports

The NoC and chip boot cocotb targets produce a self-contained `report.html`
beside their logs. The page embeds its data, works offline, and contains:

- a filterable table of reads/writes at initiator, inter-mesh and target boundaries;
- full address, local AXI ID, every data beat, write strobes, responses and sidebands;
- a completion timeline with one row per initiator and simulation time on the X axis;
- accepted B and accepted final-R-beat completion points, with latency/details on selection;
- run outcome, capture coverage, in-flight/reset-aborted observations and diagnostics;
- filtered CSV/JSON export, with wide addresses/data retained as hexadecimal strings.

The timeline defaults to initiator observations. The same transfer is also
observed at downstream links/targets; those observations are available in
the table or by clearing the initiator-only timeline control. Performance
summaries count initiator completions once. These are simulation bus metrics,
not physical DDR/HBM timing or maximum-throughput measurements.

## Capture provider and coverage

The pinned `cocotbext-axi==0.1.24` package already used for the AXI agents
also provides passive `AxiAWMonitor`, `AxiWMonitor`, `AxiBMonitor`,
`AxiARMonitor` and `AxiRMonitor`. These upstream monitors sample handshakes;
the collector does not drive VALID, READY, data or reset.

`tools/supernoc_gen.py` emits read-only channel aliases under `COCOTB_SIM`
and `gen/supernoc/axi_monitors.json` from the same actual endpoint/link graph
as `soc_noc`. The default architecture has 26 distinct AXI connections:
six initiator boundaries, nine target boundaries and eleven inter-mesh
links, covering all 37 NoC endpoint ports. Each link is captured once and
catalogs both connected endpoints. Router-to-router FlooNoC flits are not
AXI channels and are outside this capture scope.

Both existing testbenches attach this catalog: `u_noc` in the NoC BFM test,
and `dut.u_noc` in the chip boot test. There is no extra RTL testbench or
vendor fork. Eager bus binding rejects missing channel aliases. A configured
event limit fails the test explicitly and marks the artifact incomplete.
Successful monitored simulations also require nonempty, internally
consistent capture; an idle individual boundary is allowed.

The PULP AXI revision already locked by FlooNoC also contains
[`axi_dumper`](https://github.com/pulp-platform/axi/blob/0ccc838fe06aeeb857eb83c6be9a915c4bf99566/src/axi_dumper.sv),
which can log all five channels when enabled. Its simulation-only SV
implementation and dictionary-log format would need separate simulator
validation and transaction/report processing. Reusing the working cocotb
flow avoids introducing another logger or AXI dependency revision.

## Transaction semantics and limits

`dv/common/axi_trace.py` writes accepted channel events to flushed JSONL.
`tools/axi_report.py` correlates them after the simulator process exits,
including failed and expected-failure runs. Ordering rules are explicit:

- AW and W are independent. AXI4 has no WID; complete W bursts pair with
  accepted AW requests in address-channel order, including W-before-AW.
- B responses pair by BID and FIFO order within that ID. Different IDs
  can complete out of order. A write completes on BVALID && BREADY.
- R beats pair by RID and FIFO order within that ID. Interleaved read IDs
  are supported. A read completes on RVALID && RREADY && RLAST.
- Reset starts a new correlation epoch. Old in-flight requests become
  `reset_aborted`; late/unmatched responses are diagnostics.
- Same-edge events are processed in request/data/response order. All
  accepted data beats, responses and local IDs remain available in JSONL.

IDs can be remapped through the NoCs. The report deliberately correlates
within each observed interface, rather than guessing a global transaction
identity from matching addresses, payloads or IDs. The address-region label
comes from the architecture map; it is not proof of the original source or
actual destination. Existing independent destination/readback scoreboards
remain the functional acceptance checks.

Data values are full AXI bus beats. For narrow or unaligned reads, interpret
valid byte lanes using ARSIZE and address; R has no write-strobe field.
The shared memory crossbar's HBM/DDR traffic is observed at its common
NoC target boundary and labeled by address region. Downstream crossbar
ports and non-AXI CPU interfaces are separate future capture points.

Pending traffic at test termination is retained without a completion point.
Malformed/truncated logs, response orphans and burst-length mismatches are
visible. The report is not full AXI protocol VIP. Startup failures before a
simulation plan exists may stop before a report is created. Xezim targets
retain their current logs; this first capture provider runs in the two
Verilator/cocotb NoC scopes and their negative variants.

## YAML, commands and published artifacts

Each observed target opts in through `config/regression.yaml`:

```yaml
report:
  context: 'Real CPU firmware; a verification AXI BFM uses the reserved compute0 DMA boundary. No DMA engine is instantiated.'
  axi:
    scope: dut.u_noc
    clock: clk
    reset: rst_n
    catalog: gen/supernoc/axi_monitors.json
    actors: gen/chip/manifest.json
    max_events: 500000
```

The provider currently requires active-low reset and the declared common
clock. New clock domains need separate explicit clocks/timestamps and
correlation review.

```bash
make dv-chip
make dv-supernoc
python3 tools/regress.py chip-boot --stage run
```

Open `.tools/regression/<target>/report.html`. That directory also contains
`axi-events.jsonl` (raw accepted handshakes), `axi-transactions.json`
(versioned run metadata and AXI observations), `result.json`, and the
existing plans/logs/XML. Local attempts replace that target's prior output;
CI artifacts preserve the workflow run and attempt.

The [GitHub Pages hub](https://r987r.github.io/xezim-hello-world/) publishes
the topology, docs and trusted main CI results. See [publication](publication.md)
for provenance, retention and offline preview instructions.

The chip and NoC workflows upload dedicated AXI run report artifacts in
addition to their full evidence artifacts. Download the artifact from the
Actions run, extract it and open a target's `report.html`; GitHub artifact
downloads do not execute or host the HTML page directly.

## Controlled one-beat fabric latency baseline

The existing **supernoc** test runs serial one-beat transactions across each allowed
initiator-to-target route before applying concurrent stalls/bursts or faults.
It uses three distinct addresses per route and checks the correct destination,
write data and readback. This does not replace concurrent traffic tests.

The passive AXI collector records a measured clock period and annotates each
AR/AW with its test phase. Per-mesh request and response timing is published
only when the complete, clean, successful capture matches the Pages source SHA
exactly, the clock period is known, and all boundaries agree uniquely on
address, plane, operation, one-beat length and ordering.

Each mesh's request delay runs from incoming AXI acceptance to outgoing
AXI acceptance. Response delay runs from downstream B/RLAST acceptance
to upstream B/RLAST acceptance. The final target-facing AXI service
covers the last target port's request-to-completion interval; in the memory
subsystem it includes the behavioral memory crossbar and model, **not** an
isolated DDR/HBM controller or device measurement. The sums must equal the
measured end-to-end request-to-completion interval, or the trace is rejected.

All timing values are retained in picoseconds; reported cycles divide by
the **observed simulation clock period**, not an assumed hardware frequency.
Individual router/flit/NI latencies, inter-mesh physical link costs and
standalone target service are still unknown. Stalled, unmatched and
historical captures remain end-to-end observations with explicit provenance,
not fabricated per-mesh timing.

GitHub may execute a PR against a temporary merge commit whose SHA differs
from the eventual main merge SHA, even when the two Git source trees are
identical. The published evidence collector first verifies that the PR really
merged into main, validates the CI tested merge commit against the exact PR
head, and compares the tested Git tree to the published main Git tree.
Only captures with the same tested SHA, identical authenticated Git tree,
or a verified matching RTL/DV execution-input fingerprint can populate
per-mesh timing. The fingerprint includes pinned dependencies, RTL, generated
NoC, AXI monitors, test stimulus, clock/capture code and simulation CI job
execution steps; report rendering, docs and workflow scheduling do not alter
it. Any execution-input modification forces new evidence rather than silently
reusing old timing. The original tested SHA remains on every measurement. When execution inputs
change, observations remain historical, even if a route is still structurally
reachable. A new passing real NoC AXI test must then supply current timing. The wide table shows min, arithmetic average and
max cycles on read and write separately, with sample count and the measured
clock period. Stage minima/maxima are independent quantiles and need not
sum to end-to-end extrema; for the same paired samples, stage averages sum.

## Extension points

New captures record CPU/test phase markers and explicit one-request expected
responses. Generated actor metadata labels RTL CPUs, verification BFMs and idle
reserved DMA ports. Expected-error markers name an initiator, operation and
address before the request; undeclared initiator SLVERR/DECERR or mismatched
responses fail capture validation. Downstream errors remain observations, and
legacy captures without intent markers are labeled unannotated. The standalone
NoC checks 24 write/read SLVERR pairs; chip memory capacity tests check four
SLVERR transactions. Normal CPU boot expects successful responses.

Run metadata and report `sections` are versioned separately from raw event
capture. Later sections can add descriptor-level DMA correlation and CPU-driven interrupts,
latency distributions or throughput windows without changing AXI monitor
behavior. Waveform/flit traces and cross-NoC global transaction correlation
remain separate future work.

## DMA completion and DDR-controller isolation

A DMA transfer is **not** complete because the DDR-facing target asserted
`BVALID`, because a read exposed `RLAST`, or because a cocotb wait saw an
interrupt edge. For completed AXI writes, require an accepted
`BVALID && BREADY` handshake at each relevant observable boundary. For
completed reads, require accepted `RVALID && RREADY && RLAST`. An
`RLAST` signal without acceptance does not retire the read.

The integrated `chip-dma` regression uses **CPU0 AXI BFM (data)** and
**CPU0 AXI BFM (config)**, both simulation-only initiators at CPU0's NoC
manager ports while CPUs are in reset; neither is PCIe. The real iDMA
engine fetches descriptors and transfers payloads. On a timeout the test
reuses `tools/axi_report.py` to correlate accepted AR/R and AW/W/B
requests by AXI ID at each boundary, then reports incomplete requests,
IDs, addresses, read beats and missing responses. IDs may be remapped
between local/global NoC boundaries, so do not equate their values globally.

Historical stalls and follow-up experiments are retained in [the verification issue](https://github.com/r987r/xezim-hello-world/issues/34) and original CI, not in this contract. `chip-dma` uses behavioral AXI RAM; it does not exercise a DDR4 controller. The opt-in `chip-ddr4-real` test uses a LiteDRAM DDR4 controller with separate RTL/DFI evidence and a behavioral PHY/bank model, not a silicon PHY. On timeout, find the first incomplete **accepted** AXI boundary. Do not infer memory commit from BVALID or a DMA interrupt alone.
