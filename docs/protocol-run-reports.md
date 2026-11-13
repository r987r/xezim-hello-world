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
except BaseException as error:
    capture.close("fail", error=error)
    raise
else:
    capture.close("pass")
```

The timestamps above illustrate API usage, **not measured timings**. An
actual test must pass its observed simulation timestamps. Call `close("fail")` on failed tests and `close("pass")` only after all VIP assertions succeed. Ensure every code path closes the sink, even on failure.
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

## Automatic capture publication, including new controllers

A new PCIe, DDR/DFI, Ethernet or other monitor must use the **same**
versioned `protocol-events.jsonl` / `protocol-transactions.json` exporter.
The CI workflow must upload the original `protocol-transactions.json`
explicitly (or use the canonical `.tools/regression/` artifact). The Pages
collector discovers the filename in workflow YAML; there is **no list of
controller or protocol names to update**. Adding a new protocol requires a
source-verified run, not a new HTML renderer.

Publication has two distinct paths:

- **Canonical regression:** original `result.json` plus plan, immutable
  identity and protocol capture. Preserve the existing PASS/FAIL test gates.
- **Standalone capture-only:** protocol JSON, event log and CI metadata only.
  The unified viewer displays the observed events/transactions with
  **OBSERVED** status, never an invented `result.json`, completed full-chip
  transfer or PASS. A failing parent workflow remains visibly failed.

Both paths require an authenticated main/merged-PR source, clean checked-out
SHA, matching workflow run/attempt, a complete monitor catalog and records,
and successful source-level capture validation. Missing or corrupt evidence is
quarantined with a publication note; it cannot silently become a PASS. Open
unmerged PRs have offline previews/artifacts only. A public Pages refresh
requires a trusted `main` publication after merge.

**DDR-specific safeguard:** a newly introduced DFI command, mode-register
write/read, or DDR-controller CSR operation appears only if a passive hardware
observer emits it with real timestamps and source-owned fields. The RDL
register catalog and planned initialization are not evidence that a command
was actually issued. CI tests exercise synthetic PCIe, DFI and Ethernet
source catalogs to prevent omissions when a new protocol is added.

## Unified Test Runs traffic explorer

The primary UI is **Test Runs → Protocol traffic · all tests**. It offers
an all-runs bounded preview, a single verified CI run selector, and protocol,
monitor, operation, status, and payload/text filters. The page renders an
observed-completion timeline and decoded source-native fields inline. Clicking
a row expands the complete JSON record; CSV/JSON export uses the filtered
selection. Choosing one run loads its full provenance-checked
protocol-transactions.json, not only a summary.

All reported protocols belong on this same page: PCIe, Ethernet, AXI4/AXI5,
APB, DFI and new monitored buses need no new traffic-viewer implementation.
The configured test catalog and CI-only checks remain separate from actual
per-run traffic evidence. Independent per-run report.html/protocols.html
artifacts are optional deep diagnostics and source exports, not mandatory
navigation destinations. The architecture IP link inspector opens this
unified page with the matching run, protocol, and source selected.

### Ethernet GMII source/observer capture

For chip-ethernet and chip-ethernet-cpu, the pinned cocotbext-eth GMII
source/sink adapters publish two source-native monitor names:
ethernet0.gmii_rx (VIP-injected frames after source.wait) and
ethernet0.gmii_tx (RTL frames returned by the VIP sink). Their protocol
metadata distinguish injected input from independently observed output.
Fields include MAC addresses, EtherType, IPv4/UDP addresses/ports where
present, original packet bytes, length, FCS status when checked and
simulation time. These are **not physical Ethernet PHY** observations.
AXI DDR/SRAM/CQ traffic still comes from the existing passive AXI
correlator; no new MAC, BFM, decoder, or inferred DMA correlation was added.

## Architecture link traffic explorer (all protocols)

The architecture inspector is a **read-only evidence consumer**. Each published
run retains its exact tested commit, Actions workflow/attempt, complete-capture
status and source monitor provenance. It indexes the protocol-neutral
protocol-transactions.json into a bounded per-monitor summary, then links
to the complete, source-verified protocol viewer.

* Select the chip's subsystem and IP (for example **pcie0 → pcie0.ip**).
  If a verified run includes observations for that IP's monitor source IDs,
  a run/monitor selector and actual transaction preview appears.
* Select a run and monitor to see operation, simulation timestamp, identifier,
  and the source-native fields. **Open full filtered protocol timeline / details**
  deep-links into the full protocol report using protocol and source URL
  parameters; raw JSON, AXI correlations and detailed decoded records remain
  accessible.
* No protocol-specific UI registration or register-list maintenance is needed:
  the index uses the existing source catalog (id, protocol, role,
  clock_domain, implementation) and recorded fields dictionary. The
  detail viewer chooses columns from observed field keys. This works with
  pinned PCIe TLP, Ethernet MAC, APB, AXI4/AXI5 or future VIP adapters,
  including fields not known when the page was authored.
* The architecture resolver attaches a monitor only when its source ID matches
  a known diagram node or a uniquely named IP owner (pcie0.* maps to pcie0.ip).
  Unmatched monitors remain visible through **Test Runs** and never cause
  speculative physical wire attachment. Structural links, an active simulated
  protocol boundary, and physical PHY/DFI signaling are distinct claims.
* Preview samples are capped; counts include all observed records, while the
  full provenance-checked JSON and protocol table preserve the details. An
  incomplete capture is explicitly marked, not promoted to PASS.

**Current PCIe capture:** pcie0.rx_req and pcie0.tx_cpl are accepted
verilog-pcie RTL bridge interface TLPs, parsed by pinned upstream
PcieIfFrame.to_tlp() / cocotbext-pcie, with a *modeled* Root Complex.
The decoder records operation, direction, address, requester/tag, length,
header/payload, byte enables and completions. It **does not** measure
electrical PCIe PHY traffic, negotiated link training or physical-layer timing.

### PCIe native PIPE traffic — one monitor, one exporter

The [OpenPCIe original, SHA-pinned](../config/ip.lock.yaml) `pipe_monitor_bfm.py`
already reconstructs TLP and DLLP packets from its original endpoint PHY
`phy_txdata/phy_txdatak` monitor. Our standalone FuseSoC/Cocotb job
instruments its existing `pipe_agent.py` callbacks **without changing
or duplicating the packet decoder or queue semantics**. Original events carry
Cocotb simulation picoseconds, the native reassembled raw packet bytes and
their original appearance order.

The small, reusable `tools/pcie_native_pipe_capture.py` adapter converts
**both** native packet callback types to the *single* shared monitor catalog
source `pcie0.pipe.ep_tx`, with `tlp_frame` and `dllp_frame` events.
It uses `ProtocolTrace` and the unchanged `tools/protocol_report.py`
renderer. It preserves repeated frames/retries, data hex, byte length,
source log line, endpoint-transmit direction and
`openpcie_native_pipe_monitor` implementation provenance. Unknown or
malformed native events, missing Cocotb result summaries, nonmonotonic
simulation timestamps, duplicate/inconsistent fields and event overflow
fail closed. There is **no new PCIe VIP, independent decoder, HTML renderer,
transaction correlator or special-case Pages list**.

The CI job runs the adapter with `if: always()` after the original source
test. It uploads the same `protocol-events.jsonl`,
`protocol-transactions.json`, and `protocols.html` artifact paths
as other protocols, including if the Cocotb readback **fails**.
`run.test_status` preserves the actual Cocotb PASS/FAIL and
`run.qualification=capture_only_original_upstream` prevents a
source-authentic capture from being interpreted as chip-level PASS.
`capture_complete` means only that the passive capture itself is
well formed: **it does not override test failure**. The original
`ci_require_cocotb.py` remains the mandatory test gate and no
`result.json` is invented.

This first source has **EP PHY transmit** visibility; it does not establish
independent RC receipt, all physical PIPE traffic, host→EP visibility,
link compliance or an on-chip NoC transaction. The cross-provider bench's
existing capped raw PIPE samples are not full transaction tracing.
For complete bidirectional coverage, feed genuine provider-observed
host TX/RX and endpoint TX/RX into the **same event adapter/source catalog**,
each with its own source ID and clock domain; reuse the existing source
decoder instead of implementing a second TLP parser. A packet is marked
fully delivered only after the independent receiving monitor observes it.
Link-packet ACK/NAK, credit updates and LTSSM become further observed
events with source-native fields, not host traffic inferred from endpoint
callbacks. This is the remaining #76 integration gate.

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
