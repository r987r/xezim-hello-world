# Ethernet0 standalone 1G MAC / GMII bring-up

Scope: **real upstream RTL** for 1G frame RX/TX and two frame-aware clock
domain crossing FIFOs, with upstream Cocotb GMII VIP. Additional queue-control,
header staging, descriptor-driven RX/TX DMA and B-gated CQ-writer modules have
now merged independently, but the generated SoC still **does not connect**
those blocks to the Ethernet Data/Config FlooNoCs. `gen/chip/manifest.json`
still labels packet DMA `reserved_idle` and management CSR
`explicit_axi_error`. The external GMII BFM is a simulation-only wire
interface, not a silicon SerDes. See [draft PR #73](../../../docs/ethernet0-closure-gate.md)
for the connected-subsystem acceptance tests.

## Pinned dependencies

`ip.lock.yml` pins exact commits of Alex Forencich's MIT-licensed
`verilog-ethernet` (`axis_gmii_tx`, `axis_gmii_rx`, `lfsr`) and
`verilog-axis` (`axis_async_fifo`). Both repos are deprecated in favor
of Taxi; their established 1G GMII modules and extensive existing tests make
them an intentionally conservative first integration profile. No vendor RTL
is modified or copied into our tree. Source files are fetched unmodified into
ignored `.tools/ethernet0/` with exact-SHA checks.

## Clock and AXIS contracts

* GMII RX and TX run on their respective 125 MHz clocks, while the SoC-side
  AXI-Stream is 64-bit with 8-bit `tkeep` at 100 MHz in the test. **Separate clock domains** are
  passed through real frame FIFOs. This profile implements 1 GbE only.
* The pinned width adapters upsize RX GMII bytes and downsize TX `tkeep`
  bytes without truncating non-multiple-of-eight frame tails. This avoids the
  100 MB/s peak limit of an 8-bit 100 MHz logic bus against 1GbE's 125 MB/s.
* TX FIFO stores an entire frame before sending through the MAC; TX adds
  preamble, padding as required and Ethernet FCS.
* RX MAC checks FCS and strips FCS. RX FIFO drops whole errored or oversize
  frames (and on full). It never advertises a partial RX frame as complete.
* RX/TX `tuser[0]` is the upstream error marker, not classification metadata.
  The existing Python `frame_contract.py` is a golden model, not RTL.
* FIFO sizes in this milestone are 2048 bytes; byte capacity is independent
  of the width adapter. Oversize/overflow and frame accounting need separate
  stress coverage before a full controller-quality claim.

## Focused test

```sh
python3 -m pip install 'PyYAML==6.0.3' 'cocotb==1.9.2' \
  'cocotbext-axi==0.1.28' 'cocotbext-eth==0.1.28' 'cocotb-test==0.2.6'
# Requires iverilog or verilator, internet for pinned IP fetch
python3 dv/ethernet0/run_mac_gmii.py
```

The regression sends independent GMII-source frames into the **actual**
`axis_gmii_rx` and checks AXI-stream payloads; it also sends AXI-stream
payloads through **actual** `axis_gmii_tx` and checks GMII payload/FCS,
then injects a corrupted FCS and requires a MAC error indication and no
delivery to the logic RX FIFO. Runs are bounded by Cocotb timeouts.
CI installs the open-source simulator and runs this test on PRs.

## Remaining system integration gate (#64)

Foundation PRs #52 (MAC/stager), #61 (queue/descriptor/DMA), #68 (real CQ
writer), and #70 (generated Ethernet NoCs/topology) are **merged**. Older
Ethernet prep issues #37/#42 were closed as consolidated, **not** end-to-end
verified. Do not resurrect the standalone bring-up PRs.

One draft [PR #73](https://github.com/r987r/xezim-hello-world/pull/73)
tracks the actual missing MAC→queue→NoC→memory/CQ/IRQ and SRAM→GMII TX
connections plus Config NoC CPU CSR access. Run the five named
[RUN/CHECK tests](../../../docs/ethernet0-closure-gate.md) and require
byte-perfect independent readback, real AXI B/RLAST, GMII TX completion,
and source-true generated diagrams/reporting before merging. Physical DDR
controller/PHY, full PCIe/link, and stress/performance remain separate.
