# Implementation boundaries

This page describes **which RTL/model is selected**, not a rolling CI/PR status log. For open work and acceptance evidence see [completed functional MVP #34](https://github.com/r987r/xezim-hello-world/issues/34), [post-MVP flow matrix #158](https://github.com/r987r/xezim-hello-world/issues/158), [open issues](https://github.com/r987r/xezim-hello-world/issues) and the [live Test Runs hub](https://r987r.github.io/xezim-hello-world/).

| Component | Supported configuration | Important limit |
| --- | --- | --- |
| CPU/boot/SRAM | PicoRV32 and SERV execute ROM/flash-to-SRAM boot with reset coordination | Boot SRAM is not preloaded; physical SRAM macro selection is separate |
| Data/Config NoCs | FlooGen-derived FlooNoC meshes, independent AXI monitor/NoC BFM tests | Diagram/compilation does not prove every optional IP's elaborated pins |
| PULP iDMA | Real desc64 frontend/backend, generated Data/Config connections, CPU0 C polling or reset-isolated BFM drive | CPU interrupt service is not implemented; simultaneous CPU-directed dual engines remain #47 |
| Ethernet | Opt-in GMII RX/TX MAC, queues, DMA, CSR/CQ; real CPU0 control and one-chip Ethernet/real DDR/iDMA/PCIe host BAR-pull smoke | Default chip keeps packet engines reserved; endpoint host-RAM DMA is separately qualified, not proven chained to Ethernet (#158) |
| PCIe | Opt-in actual TLP↔AXI bridge, modeled host RC, SRAM BAR access, and separate CPU0/Config-NoC-controlled endpoint MWr/MRd to modeled host RAM | No physical PCIe PHY, generalized host DMA queue/stress, or full outbound passive packet correlation (#76) |
| DDR | Default bounded AXI RAM; opt-in real LiteDRAM RTL with Config-NoC init and behavioral SDRAM DFI/BankModel | No silicon PHY; DDR stress remains #35 |
| HBM | Bounded modeled AXI RAM behind HBM aperture | No real HBM controller/PHY (#45) |

The [RTL source selection](../config/regression.yaml), [SoC configuration](../config/soc.yaml), [generated manifest](../gen/manifest.json) and [interface contracts](../config/interface_contracts.yaml) determine actual instances and address/ID widths. Variant-specific CI evidence is authoritative for what *ran*; older passing runs cannot qualify newer RTL.

For execution and reporting: [regressions](regression.md), [IP substitution limits](ip-portability.md), [source-derived architecture](architecture.md), and [combined-test acceptance](multiprotocol-integration-readiness.md).
