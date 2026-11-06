# Generic peripheral generator integration boundary

The generic peripheral emitter and current variant-specific hardware attachments must be distinguished without inventing packet-capable hardware behind default reserved endpoints. This is a historical boundary note; the maintained entry points are [architecture](architecture.md), [verification](verification.md), and [next-stage integration](multiprotocol-integration-readiness.md).

- `config/soc.yaml` defines the typed SoC peripheral and address map.
- `tools/socgen.py`, `tools/floonoc_gen.py`,
  `tools/supernoc_gen.py`, and `tools/full_chip_gen.py` own generation.
- `gen/noc/floonoc/`, `gen/supernoc/`, `gen/chip/`,
  and `gen/diagrams/` are canonical **generated** outputs.
- PCIe0/Ethernet0 packet interface present in a NoC diagram means only a
  structural connection **if** the chip manifest marks that endpoint as
  `reserved_idle`. Control endpoints marked `explicit_axi_error`
  are **not** queue registers.
- The opt-in Ethernet variant now uses the verified MAC/CDC, queue/DMA,
  completion writer, and real AXI arbitration. Only its **own** generated
  manifest may mark that RTL attachment live; default chip remains reserved.
- Build and source hash verification must run again after merge onto main,
  because newer memory and DV changes may affect generated collateral.

This document is an integration handoff, not proof of actual packet traffic.
