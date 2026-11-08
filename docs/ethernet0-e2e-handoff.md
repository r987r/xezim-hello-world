# Ethernet0 handoff references

The standalone and CPU-driven GMII/queue/DMA MVP has a stable [reproduction and acceptance contract](ethernet0-closure-gate.md). The **one-chip multi-protocol functional MVP is independently qualified** ([merged #150](https://github.com/r987r/xezim-hello-world/pull/150)); use [combined integration acceptance](multiprotocol-integration-readiness.md) and [post-MVP transfer matrix #158](https://github.com/r987r/xezim-hello-world/issues/158) for remaining work. Older PR timelines, failure investigations and milestone notes belong in the related issue/PR history, not a second implementation document.

Do not treat a BFM-driven Ethernet↔modeled-DDR test as real CPU firmware or a newly qualified Ethernet↔endpoint-initiated host-RAM DMA chain. The completed combined smoke uses real CPU0/DDR/DFI and modeled host BAR pulls.
