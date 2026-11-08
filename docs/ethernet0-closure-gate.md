# Ethernet0 functional MVP contract

The opt-in Ethernet subsystem instantiates one upstream 1G GMII MAC, RX/TX queues, descriptor and packet AXI DMA, PULP AXI mux and 32-byte B-gated completion queues. Ethernet's local Data/Config FlooNoCs and queue CSR bridge are connected **only in the selected variant** (`ethernet_mode=True`); default checked-in chip RTL leaves packet-management attachments reserved. The Ethernet #64 MVP is closed; current expansion and combined-system requirements belong to [#34](https://github.com/r987r/xezim-hello-world/issues/34).

## Retained regression

```sh
python3 tools/regress.py chip-ethernet-cpu  # real CPU0 C queue configuration and GMII
python3 tools/regress.py chip-ethernet      # CPU-reset BFM, SRAM/modeled-DDR paths
python3 dv/ethernet0/run_mac_gmii.py       # standalone GMII/FCS
```

The CPU firmware regression must actually run on PicoRV32, write queue policy/descriptor CSRs through Config NoC, and check SRAM RX bytes, TX bytes, CQ cookie/length/status, producer/consumer indices and IRQ acknowledgments. A physical **simulation GMII peer** injects and captures frames; no CPU0 AXI BFM substitutes for real CPU execution in `chip-ethernet-cpu`. The separate BFM regression covers SRAM and **modeled** DDR transfers, including no-buffer and bad-FCS negatives.

Acceptance requires actual accepted AXI AW/W/B and AR/R traffic, B-gated completion metadata, line-level GMII and independent byte comparisons. Declared phase names are not hardware transactions. Use the original tested source and [CI evidence](https://github.com/r987r/xezim-hello-world/actions/workflows/ethernet-mvp.yml), not a hardcoded dated PASS count.

## Beyond the MVP

Combined Ethernet-produced bytes/CQ → **real LiteDRAM** → CPU/iDMA → modeled PCIe host BAR readback passed the bounded [combined #34 functional MVP](multiprotocol-integration-readiness.md); further directed/randomized chaining remains [#158](https://github.com/r987r/xezim-hello-world/issues/158). An Ethernet-to-PCIe fast hardware bypass, autonomous outbound PCIe host-RAM DMA **in this Ethernet test** (a separate PCIe variant proves CPU-controlled outbound DMA), silicon PHY, and stress/performance are not implied by this MVP.
