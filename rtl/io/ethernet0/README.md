# Ethernet0 standalone 1G MAC / GMII bring-up

Scope: pinned upstream 1G GMII RX/TX MAC/FCS, clock-domain FIFOs, programmable queue/descriptor DMA, completion ring and an optional generated-chip Data/Config NoC attachment. The connected functional Ethernet MVP has **passed** in the opt-in variant: [CI #42145885849](https://github.com/r987r/xezim-hello-world/actions/runs/42145885849), including GMII RX/TX to/from SRAM and modeled DDR with real AXI and CQ readback. Standalone MAC/queue/CQ groundwork is merged from #52/#61/#68 and structural Ethernet NoCs from #70.

The **default** committed generated `soc_top` / manifest still reserves packet DMA and queue CSRs. The RTL is physically wired only when generating with `ethernet_mode=True` in `tools/full_chip_gen.py`; this distinction is deliberate, not an incomplete IP-level test. A GMII BFM is simulation wire traffic, not an off-chip silicon PHY.
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

## Ethernet MVP vs. final combined integration (#64)

One MAC, RX/TX queues, upstream DMA, six-source PULP AXI mux, Config NoC CSR target, and B-gated 32-byte CQ are now connected in [draft PR #73](https://github.com/r987r/xezim-hello-world/pull/73). The real opt-in generated-chip test `python3 tools/regress.py chip-ethernet` passed [CI 42145885849](https://github.com/r987r/xezim-hello-world/actions/runs/42145885849). It checks RX SRAM/DDR, TX SRAM/DDR and no-buffer negative; focused regressions also check bad FCS and CQ B stalls.

The SoC test uses CPU0 **AXI BFMs** with the actual CPUs in reset. **Issue #64 is still open** because one combined CPU0 C / modeled PCIe Root Complex run must verify host visibility of the Ethernet-generated buffer and CQ, emit the prescribed five INIT/RUN/CHECK records, and reconcile real variant reports/diagrams. General global-NoC same-ID concurrency assertion #75/#78, physical DDR controller/PHY #40 and PCIe post-MVP #76 are separate work; do not hide the failing NoC regression.

Details: [five-step closure gate](../../../docs/ethernet0-closure-gate.md) and [combined-protocol readiness](../../../docs/multiprotocol-integration-readiness.md).
