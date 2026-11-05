# Generic peripheral generator integration boundary

The generic peripheral emitter in this branch must be integrated without
inventing packet-capable hardware behind the reserved endpoints.

- `config/soc.yaml` defines the typed SoC peripheral and address map.
- `tools/socgen.py`, `tools/floonoc_gen.py`,
  `tools/supernoc_gen.py`, and `tools/full_chip_gen.py` own generation.
- `gen/noc/floonoc/`, `gen/supernoc/`, `gen/chip/`,
  and `gen/diagrams/` are canonical **generated** outputs.
- PCIe0/Ethernet0 packet interface present in a NoC diagram means only a
  structural connection **if** the chip manifest marks that endpoint as
  `reserved_idle`. Control endpoints marked `explicit_axi_error`
  are **not** queue registers.
- Future Ethernet attachment must use the proven MAC/CDC, queue/DMA,
  completion writer, and actual AXI arbitration; only then may the
  generated manifest promote attachment to live.
- Build and source hash verification must run again after merge onto main,
  because newer memory and DV changes may affect generated collateral.

This document is an integration handoff, not proof of actual packet traffic.
