# SoC implementation status

The architecture comes from `config/soc.yaml`; its generated verification
plan distinguishes independent executable scopes from the planned full SoC.
A passing BFM test does not establish CPU/iDMA/controller integration.

| Part | Executable scope | Remaining boundary |
| --- | --- | --- |
| Verilog-AXI memory crossbar | `make dv-memory`, full/sparse routing profiles, negative corruption test | Separate 2x2 crossbar with behavioral HBM/DDR AXI RAM targets |
| Local SRAM | `make dv-sram` and YAML `sram-synthesis`, read/write ports and byte strobes | Legacy custom test SRAM; no silicon macro integration |
| SERV | `make dv-serv`, real instruction execution | Standalone core test |
| Dual-CPU cold boot | `make dv-boot`, PicoRV32 ROM/flash reads, stores into uninitialized SRAM, MMIO release of SERV, both signatures | Separate boot memory/bus scope |
| Eight local/global FlooNoCs | `make dv-supernoc`, all real meshes connected by 11 AXI4 links, six upstream managers and nine mapped sparse targets | AXI BFMs at CPU/DMA/CSR/SRAM/memory-crossbar boundaries |
| Xezim FlooNoC compatibility | `python3 tools/regress.py compatibility`, all eight structural compilations | Data-mesh width warnings remain; no Xezim NoC traffic proof |
| AXI-Lite endpoint adapters | Upstream converters/mux/demux and reset register bank attached in the chip boot scope | The independent NoC BFM wrapper still uses AXI agents |
| PULP iDMA | `make dv-dma` isolated scope now instantiates pinned desc64 frontend + generated rw_axi backend and tests AXI descriptor fetch, payload copy and writeback through upstream AXI BFM. **Verified in the independent [DMA RTL CI run](https://github.com/r987r/xezim-hello-world/actions/runs/41860245485).** | Config NoC CSR, real local NoC integration, IRQ to CPUs and chip boot scope still pending |
| HBM/DDR controllers and PHYs | No executable physical path | All current targets are behavioral AXI models |
| Chip boot `soc_top` | `make dv-chip`: CPU0 loads SRAM, releases SERV and coordinates init/run/check through real NoCs; AXI memory model readback | Real iDMA/CSR/interrupts and physical controllers remain pending |

See [super-NoC verification](supernoc-verification.md) for the exact traffic
checks, local evidence, test commands and known limitations. See
[simulator compatibility](simulator-compatibility.md) for diagnostics.
The generic FlooNoC backend registry remains non-executable because it does
not emit a general complete SoC. Shared NoC, BFM and CPU boot-configuration
emitters exist; real iDMA and physical-controller integration remains pending.

## Single architecture diagram

[The one whole-chip diagram](../gen/diagrams/noc-hierarchy.svg) is embedded
in README. Its Mermaid source and `noc-topology.json` preserve topology
for inspection. Router positions come from actual FlooGen profiles. The
cross-network link set is checked against `supernoc_tb`; dashed chip
endpoint links denote pending iDMA/CSR/physical-controller integration.
CPU/SRAM/reset and memory-model paths are wired in the boot configuration. There are
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

## Resolved SRAM audit item

The registered port-B read in `rtl/memory/local_sram.sv` now sits outside
`ifndef SYNTHESIS`; only the simulation collision assertion is guarded.
The YAML `sram-synthesis` target runs the existing read/write bench with
`-D SYNTHESIS`, alongside the normal SRAM target. This checks functional
behavior under the define; it is not a technology synthesis/macro gate.

The [chip boot configuration](full-chip-boot.md) uses upstream `tc_sram`
and PULP AXI responders. The legacy SRAM remains only in the independent
SRAM and older boot scopes.
