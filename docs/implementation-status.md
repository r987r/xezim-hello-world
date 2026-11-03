# SoC implementation status

The architecture comes from `config/soc.yaml`; its generated verification
plan distinguishes independent executable scopes from the planned full SoC.
A passing BFM test does not establish CPU/iDMA/controller integration.

| Part | Executable scope | Remaining boundary |
| --- | --- | --- |
| Verilog-AXI memory crossbar | `make dv-memory`, full/sparse routing profiles, negative corruption test | Separate 2x2 crossbar with behavioral HBM/DDR AXI RAM targets |
| Local SRAM | `make dv-sram`, read/write ports and byte strobes | Existing custom test SRAM; no silicon macro integration |
| SERV | `make dv-serv`, real instruction execution | Standalone core test |
| Dual-CPU cold boot | `make dv-boot`, PicoRV32 ROM/flash reads, stores into uninitialized SRAM, MMIO release of SERV, both signatures | Separate boot memory/bus scope |
| Eight local/global FlooNoCs | `make dv-supernoc`, all real meshes connected by 11 AXI4 links, six upstream managers and nine mapped sparse targets | AXI BFMs at CPU/DMA/CSR/SRAM/memory-crossbar boundaries |
| Xezim FlooNoC compatibility | `scripts/run-floonoc-xezim.sh all`, all eight structural compilations | Data-mesh width warnings remain; no Xezim NoC traffic proof |
| AXI-Lite endpoint adapters | Upstream PULP `axi_lite_to_axi` / `axi_to_axi_lite` selected | Not connected in the NoC BFM wrapper; config traffic is single-beat AXI4 |
| PULP iDMA | No executable subsystem | Frontend, CSR, data and interrupt connections pending |
| HBM/DDR controllers and PHYs | No executable physical path | All current targets are behavioral AXI models |
| Full-chip `soc_top` | No executable RTL | Real CPU → DMA → NoC → memory integration pending |

See [super-NoC verification](supernoc-verification.md) for the exact traffic
checks, local evidence, test commands and known limitations. See
[simulator compatibility](simulator-compatibility.md) for diagnostics.
The generic FlooNoC backend registry remains non-executable because it does
not emit a complete SoC; scoped FlooGen and BFM-wrapper emission do exist.

## Single architecture diagram

[The one whole-chip diagram](../gen/diagrams/noc-hierarchy.svg) is embedded
in README. Its Mermaid source and `noc-topology.json` preserve topology
for inspection. Router positions come from actual FlooGen profiles. The
cross-network link set is checked against `supernoc_tb`; dashed chip
endpoint links still denote pending real endpoint integration. There are
no separate per-router, boot or verification pictures.

All generated sources are checked in under `gen/`; `make gen` owns the
tree and `make check-generated` checks exact file names and contents.
Generator output is not a test result: use logs for the current source
and the exact completed CI SHA before merging.

## Preserved boot boundary

The pinned Xezim 0.11.4 release replaces the historical 0.11.3 SERV shim.
CPU0 must load firmware through its bus into uninitialized SRAM; no
backdoor SRAM preload is allowed in the cold-boot regression. Seeded
boot-window reads in the separate NoC BFM test establish routing only.
