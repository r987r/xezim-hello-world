# Ethernet0 handoff references

The standalone and CPU-driven GMII/queue/DMA MVP has a stable [reproduction and acceptance contract](ethernet0-closure-gate.md). The **new multi-protocol functional test is separate**; use [combined integration acceptance](multiprotocol-integration-readiness.md) and [epic #34](https://github.com/r987r/xezim-hello-world/issues/34) for current work. Older PR timelines, failure investigations and milestone notes belong in the related issue/PR history, not a second implementation document.

Do not treat a BFM-driven Ethernet↔modeled-DDR test as real CPU firmware or an Ethernet↔real-DDR↔PCIe host completion.
