# SoC implementation status

The architecture comes from `config/soc.yaml`; its generated verification
plan distinguishes independent executable scopes from the planned full SoC.
A passing BFM test does not by itself establish CPU/iDMA/controller integration. The real CPU0 C-DMA gate now provides separate CPU-executed proof. **Opt-in DDR-B has a passing real LiteDRAM controller RTL/behavioral DFI full-chip CPU/iDMA run** ([CI #42217902632](https://github.com/r987r/xezim-hello-world/actions/runs/42217902632)); default SoC DDR/HBM targets remain behavioral AXI RAM, and no physical DDR/HBM PHY is integrated.

| Part | Executable scope | Remaining boundary |
| --- | --- | --- |
| Verilog-AXI memory crossbar | `make dv-memory`, full/sparse routing profiles, negative corruption test | Separate 2x2 crossbar with behavioral HBM/DDR AXI RAM targets |
| Local SRAM | `make dv-sram` and YAML `sram-synthesis`, read/write ports and byte strobes | Legacy custom test SRAM; no silicon macro integration |
| SERV | `make dv-serv`, real instruction execution | Standalone core test |
| Dual-CPU cold boot | `make dv-boot`, PicoRV32 ROM/flash reads, stores into uninitialized SRAM, MMIO release of SERV, both signatures | Separate boot memory/bus scope |
| Eight local/global FlooNoCs | `make dv-supernoc`, all real meshes connected by 11 AXI4 links, six upstream managers and nine mapped sparse targets | AXI BFMs at CPU/DMA/CSR/SRAM/memory-crossbar boundaries |
| Xezim FlooNoC compatibility | `python3 tools/regress.py compatibility`, all eight structural compilations | Data-mesh width warnings remain; no Xezim NoC traffic proof |
| AXI-Lite endpoint adapters | Upstream converters/mux/demux and reset register bank attached in the chip boot scope | The independent NoC BFM wrapper still uses AXI agents |
| PULP iDMA | Isolated `make dv-dma` verified RTL descriptors ([CI](https://github.com/r987r/xezim-hello-world/actions/runs/41860245485)). Generated `DmaEnable=1` instances attach to each compute data NoC and `dma_regs` config NoC; `make dv-chip-dma` **passed** the real dual-engine full-chip RTL traffic test ([CI](https://github.com/r987r/xezim-hello-world/actions/runs/41885417960), 1,902 AXI observations). | CPU0 C-side submission/polling is verified ([full-chip CPU DMA CI](https://github.com/r987r/xezim-hello-world/actions/runs/41933332567), 39,150 AXI observations); CPU ISR/service, simultaneous CPU-launched dual-DMA and physical HBM/DDR remain pending |
| HBM/DDR controllers and PHYs | **Opt-in `chip-ddr4-real`: real pinned LiteDRAM controller RTL, 16-KiB Config NoC CSR init, real PicoRV32/PULP iDMA SRAM↔DDR and matched AXI/DFI/BankModel evidence** ([CI](https://github.com/r987r/xezim-hello-world/actions/runs/42217902632), [artifact](https://github.com/r987r/xezim-hello-world/actions/runs/42217902632/artifacts/13503312198)) | Default chip/PCIe/Ethernet modes still use AXI RAM; LiteDRAM DFI PHY and bank are behavioral; HBM controller/physical PHY, real-controller interoperability and full-chip negative-aperture closure remain outstanding |
| Chip boot `soc_top` | `make dv-chip`: real CPUs cold-boot and coordinate INIT/RUN/CHECK; `chip-cpu-dma` runs compiled C on PicoRV32 and validates SRAM/DDR/HBM roundtrips through iDMA ([CI 41933332567](https://github.com/r987r/xezim-hello-world/actions/runs/41933332567)) | CPU ISR, mixed-engine concurrent firmware and physical controller/PHY integration remain pending |

See [super-NoC verification](supernoc-verification.md) for the exact traffic
checks, local evidence, test commands and known limitations. See
[simulator compatibility](simulator-compatibility.md) for diagnostics.
The generic FlooNoC backend registry remains non-executable because it does
not emit a general complete SoC. Shared NoC, BFM and CPU boot-configuration
emitters exist; optional real iDMA wiring is emitted and passed full-chip RTL traffic regression ([CI run 41885417960](https://github.com/r987r/xezim-hello-world/actions/runs/41885417960)); CPU C-DMA integration has been verified (including opt-in LiteDRAM DDR); interrupt-service firmware, HBM controller and physical PHYs remain pending.

## Single architecture diagram

[The one whole-chip diagram](../gen/diagrams/noc-hierarchy.svg) is embedded
in README. Its Mermaid source and `noc-topology.json` preserve topology
for inspection. Router positions come from actual FlooGen profiles. The
cross-network link set is checked against `supernoc_tb`; chip DMA/CSR links are generated when enabled. The checked-in diagram is the **default modeled-memory topology**; the real LiteDRAM attachment is generated within the opt-in DDR-B runtime variant and preserved in the CI artifact.
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
