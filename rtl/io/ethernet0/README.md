# Ethernet0 1G GMII implementation

Upstream pinned `verilog-ethernet` RX/TX MAC/FCS and `verilog-axis` async FIFOs connect GMII to a 64-bit AXI-Stream SoC datapath. A one-RX/one-TX-queue descriptor DMA, AXI mux and completion ring are attached only in the opt-in generated `ethernet_mode=True` configuration. Default generated chip packet/management ports remain reserved, and the GMII peer is a simulation source/sink, **not** a silicon Ethernet PHY.

## Clock/data and drop rules

- GMII RX and TX run at 125 MHz; test SoC AXI-stream uses 64-bit `tdata` and eight `tkeep` bytes at 100 MHz across actual clock-domain FIFOs.
- RX FCS is checked/removed; oversized, corrupt, overflowing frames are dropped rather than being declared complete. TX adds Ethernet preamble, padding and FCS.
- `tuser[0]` denotes the upstream error marker, not packet classification metadata. FIFO capacity in this profile is 2048 bytes; stress limits are separate.

## Focused test

```sh
python3 -m pip install 'PyYAML==6.0.3' 'cocotb==1.9.2' \
  'cocotbext-axi==0.1.28' 'cocotbext-eth==0.1.28' 'cocotb-test==0.2.6'
python3 dv/ethernet0/run_mac_gmii.py
python3 tools/regress.py chip-ethernet-cpu
```

Tests require an installed open-source simulator and exact pinned third-party RTL fetch. The GMII regression checks RX bytes/error behavior and TX FCS. The real CPU0 C regression exercises queue CSR, SRAM, DMA/CQ and accepted AXI data; the BFM regression `chip-ethernet` adds modeled-DDR SRAM paths. See [MVP acceptance](../../../docs/ethernet0-closure-gate.md) and [combined system](../../../docs/multiprotocol-integration-readiness.md). Remaining fast-route work is [#43](https://github.com/r987r/xezim-hello-world/issues/43).
