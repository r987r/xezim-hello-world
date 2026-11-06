# SoC implementation status

The architecture comes from `config/soc.yaml`; its generated verification
plan distinguishes independent executable scopes from the planned full SoC.
A passing BFM test does not by itself establish CPU/iDMA/controller integration. The real CPU0 C-DMA gate now provides separate CPU-executed proof; no physical DDR/HBM controllers or PHYs are integrated.

| Part | Executable scope | Remaining boundary |
| --- | --- | --- |
| Verilog-AXI memory crossbar | `make dv-memory`, full/sparse routing profiles, negative corruption test | Separate 2x2 crossbar with behavioral HBM/DDR AXI RAM targets |
| Local SRAM | `make dv-sram` and YAML `sram-synthesis`, read/write ports and byte strobes | Legacy custom test SRAM; no silicon macro integration |
| SERV | `make dv-serv`, real instruction execution | Standalone core test |
| Dual-CPU cold boot | `make dv-boot`, PicoRV32 ROM/flash reads, stores into uninitialized SRAM, MMIO release of SERV, both signatures | Separate boot memory/bus scope |
| Twelve configured local/global FlooNoCs | Generated `gen/noc/floonoc/manifest.json` and `gen/supernoc/manifest.json` currently record 12 meshes, 19 structural cross-network links, 10 masters and 13 slaves; independent routed BFM and CPU/DMA proof must be scoped to its exact test SHA | Generated topology is not proof of an attached Ethernet/PCIe packet engine; endpoint/data-path coverage differs by test |
| Xezim FlooNoC compatibility | Historical Xezim structural NoC compilations; verify twelve-mesh exact-head run separately | Data-mesh width warnings remain; no claim of Xezim NoC routed-traffic proof |
| AXI-Lite endpoint adapters | Upstream converters/mux/demux and reset register bank attached in the chip boot scope | The independent NoC BFM wrapper still uses AXI agents |
| PULP iDMA | Isolated `make dv-dma` verified RTL descriptors ([CI](https://github.com/r987r/xezim-hello-world/actions/runs/41860245485)). Generated `DmaEnable=1` instances attach to each compute data NoC and `dma_regs` config NoC; `make dv-chip-dma` **passed** the real dual-engine full-chip RTL traffic test ([CI](https://github.com/r987r/xezim-hello-world/actions/runs/41885417960), 1,902 AXI observations). | CPU0 C-side submission/polling is verified ([full-chip CPU DMA CI](https://github.com/r987r/xezim-hello-world/actions/runs/41933332567), 39,150 AXI observations); CPU ISR/service, simultaneous CPU-launched dual-DMA and physical HBM/DDR remain pending |
| Ethernet0 standalone MAC, queue/DMA and CQ writer | Merged #52, #61, #68; isolated GMII/FCS, queue policy/descriptor, SRAM AXI B and CQ writer tests have passed | MAC/queue/CQ modules are **not yet connected** to generated Ethernet0 local Data/Config FlooNoCs; draft [PR #73](https://github.com/r987r/xezim-hello-world/pull/73) adds interface plumbing and [five pending E2E RUN/CHECK gates](ethernet0-closure-gate.md), not completed packet/CPU/host data flow |
| Ethernet0 local Data/Config FlooNoCs | #70 merged canonical structural RTL, four global structural links and source/diagram audit | Full-chip manifest says `rtl_attachment: reserved_idle`, `csr_attachment: explicit_axi_error`; packet, CSR, CQ and host paths must remain planned/unmeasured |
| PCIe0 local Data/Config FlooNoCs | Generated structural RTL; separate draft PCIe integration PRs | Physical host/link and complete PCIe integration not established on main |
| HBM/DDR controllers and PHYs | No executable physical path | All current targets are behavioral AXI models |
| Chip boot `soc_top` | `make dv-chip`: real CPUs cold-boot and coordinate INIT/RUN/CHECK; `chip-cpu-dma` runs compiled C on PicoRV32 and validates SRAM/DDR/HBM roundtrips through iDMA ([CI 41933332567](https://github.com/r987r/xezim-hello-world/actions/runs/41933332567)) | CPU ISR, mixed-engine concurrent firmware and physical controller/PHY integration remain pending |

See [super-NoC verification](supernoc-verification.md) for the exact traffic
checks, local evidence, test commands and known limitations. See
[simulator compatibility](simulator-compatibility.md) for diagnostics.
The generic FlooNoC backend registry remains non-executable as a universal
arbitrary-SoC plugin; dedicated generated chip and BFM emitters exist. Shared NoC, BFM and CPU boot-configuration
emitters exist; optional real iDMA wiring is emitted and passed full-chip RTL traffic regression ([CI run 41885417960](https://github.com/r987r/xezim-hello-world/actions/runs/41885417960)); CPU C-DMA integration has been verified; interrupt-service firmware and physical controllers remain pending.

## Single architecture diagram

[The one whole-chip diagram](../gen/diagrams/noc-hierarchy.svg) is embedded
in README. Its Mermaid source and `noc-topology.json` preserve topology
for inspection. Router positions come from actual FlooGen profiles. The
cross-network link set is checked against `supernoc_tb`; chip DMA/CSR links are generated when enabled; physical-controller integration remains pending.
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
