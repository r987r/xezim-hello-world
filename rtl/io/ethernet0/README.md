# Ethernet0 standalone 1G MAC / GMII bring-up

Scope: **real upstream RTL** for 1G frame RX/TX and two frame-aware clock
domain crossing FIFOs, with upstream Cocotb GMII VIP. This branch intentionally
does **not** connect Ethernet0 to the local/global FlooNoCs, instantiate SRAM
DMA, implement UDP filtering in hardware, or model an analog PHY. The external
GMII BFM is a simulation-only wire interface, not a silicon SerDes.

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
  AXI-Stream is 8-bit at 100 MHz in the test. **Separate clock domains** are
  passed through real frame FIFOs. This profile implements 1 GbE only.
* TX FIFO stores an entire frame before sending through the MAC; TX adds
  preamble, padding as required and Ethernet FCS.
* RX MAC checks FCS and strips FCS. RX FIFO drops whole errored or oversize
  frames (and on full). It never advertises a partial RX frame as complete.
* RX/TX `tuser[0]` is the upstream error marker, not classification metadata.
  The existing Python `frame_contract.py` is a golden model, not RTL.
* FIFO sizes in this milestone are 2048 bytes. Oversize/overflow and frame
  accounting require dedicated stress coverage before DMA integration.

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

## Follow-ons before #37 can close

1. Verify actual packet count/overflow under long GMII input with DMA-side
   stalls, reset during a frame, bad preamble and minimum/maximum sizes.
2. Add upstream packet parser/UDP-port classifier with a documented split
   between local/DDR/PCIe fast-path policy, preserving full frame metadata.
3. Qualify the pinned upstream PULP iDMA AXI-Stream frontend/backend or another
   established streaming-to-AXI DMA, then connect local SRAM. **No homegrown
   DMA.**
4. Wire DMA+SRAM to a generated Ethernet0 local FlooNoC through the #38
   integration owner; only then claim hardware NoC routing. Track actual
   AXI/packet events using the existing protocol-neutral report.
5. Keep #52 a draft until the complete standalone MAC/DMA/SRAM acceptance
   tests are green; a green MAC smoke is not that acceptance.
