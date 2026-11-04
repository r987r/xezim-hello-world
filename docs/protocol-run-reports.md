# Protocol-neutral verification observations

**Purpose:** one monitor-to-report contract for AXI4 today and later AXI-Stream,
DFI, APB, Ethernet MAC/packet and PCIe TLP traffic. This is *not* a new
protocol VIP or a replacement for existing monitors.

## Architecture

Existing (verified) VIP / passive monitor → tiny event adapter →
`dv/common/protocol_trace.py` → newline-flushed `protocol-events.jsonl` →
`tools/protocol_report.py` → `protocol-transactions.json` +
`protocols.html` → GitHub Pages run view.

For **AXI4**, the proven upstream cocotbext-axi channel monitors and
`tools/axi_report.py` are **still the only** channel/transaction correlator.
Their original `axi-events.jsonl`, `axi-transactions.json`, `report.html`,
Fabric Explorer attribution and pass/fail policies remain intact. The
protocol-neutral output is a read-only projection of the already-correlated
AXI records—there is no second AXI monitor.

For DFI, prefer upstream LiteDRAM's existing DFI simulation/timing checks;
the separate draft DDR4 latency-probe PR is measurement instrumentation,
not a protocol-checking VIP. A third-party DFI monitor is only warranted
after validating pin/phase and DDR4 command compatibility.

## External VIP/testbench API

Configure the opt-in additional monitor sources under a cocotb target:

```yaml
report:
  context: Real MAC traffic and APB register programming
  protocols:
    max_events: 100000
    sources:
      mac.rx: {protocol: ethernet, clock_domain: mac_rx, role: target, implementation: ethernet_vip, modeling: behavioral_vip}
      mac.stream: {protocol: axi-stream, clock_domain: stream_clk, role: link, implementation: axis_vip}
      eth.regs: {protocol: apb, clock_domain: csr_clk, role: target, implementation: apb_vip}
```

An existing VIP's transaction callback, or a testbench consuming an upstream
VIP queue, calls the reusable event sink:

```python
from dv.common.protocol_trace import open_from_plan
from cocotb.utils import get_sim_time

capture = open_from_plan()   # initialize before the DUT clock
try:
    # In a real VIP callback, derive time from the observed handshake.
    capture.event("mac.rx", "frame_rx",
                  int(get_sim_time(units="ps")),
                  {"length_bytes": 64, "ether_type": "0x0800"})
    # A protocol monitor that already matched setup and access may
    # publish one completed operation.
    capture.transaction("eth.regs", "write",
                        start_ps=120000, end_ps=140000,
                        identifier=5,
                        fields={"address": "0x20", "response": "okay"})
finally:
    capture.close("pass")
```

The timestamps above illustrate API usage, **not measured timings**. An
actual test must pass its observed simulation timestamps. Call `close("fail")`
on failed tests and always close the capture in a top-level `finally`.
The sink does not poll DUT signals or interpret protocol handshakes.

For combined AXI + additional protocols, include both `axi` and
`protocols` under `report`. The original AXI report remains the
canonical AXI view; `protocols.html` shows all protocol types in one
time/monitor chart and filterable table.

## Contract and evidence

- All timestamps use integer picoseconds; display normalizes to nanoseconds.
  Clock domains and implementation/model provenance are declared per source; they are never inferred from timestamps.
- Protocol/source/operation names and event inventory are explicitly
  configured and validated. Unknown sources and malformed captures fail.
- Large integer payload values are hex strings, avoiding JavaScript
  precision loss. No arbitrary JSON/HTML is executed.
- Events can be single observed boundary points; paired transactions must
  derive their start/end from a VIP that supports that correlation.
- Missing start/end markers, overflow, decreasing timestamps and aborted
  protocol captures invalidate success. No missing stage latency is inferred.
- Each report records the CI run, tested commit and attempt. The Pages
  publisher validates provenance before including protocol artifacts.
- Raw JSONL and versioned JSON remain downloadable; historical AXI report
  files are not rewritten in-place.

## Supported now / later

| Protocol | Existing capture | Generic display |
| --- | --- | --- |
| AXI4 | Existing cocotbext-axi five-channel monitors | **Implemented projection** |
| Ethernet packets | Existing VIP callback/packet tap required | Event/transaction schema supported |
| AXI-Stream | Existing VIP callback required | Event/transaction schema supported |
| APB | Existing VIP callback required | Event/transaction schema supported |
| PCIe TLP | Existing VIP callback required | Event/transaction schema supported |
| DDR4 DFI | LiteDRAM DFI/model signal observation | Event/transaction schema supported |

A generic schema does not imply an implemented or tested monitor for each
listed protocol. The future IP PRs should reuse stable VIP libraries and
write only a small protocol adapter. Additional protocol-specific filters
(TLP tags, Ethernet flow IDs, APB register names) can be added without
changing the common source/timestamp/completion fields.

This PR deliberately does not wire new MAC, PCIe or APB RTL, change
full-chip clocks, or merge DDR4's unverified internal-stage measurements.
