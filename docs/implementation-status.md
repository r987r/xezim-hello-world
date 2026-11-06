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
| Twelve configured local/global FlooNoCs | Generated `gen/noc/floonoc/manifest.json` and `gen/supernoc/manifest.json` currently record 12 meshes, 19 structural cross-network links, 10 masters and 13 slaves; independent routed BFM and CPU/DMA proof must be scoped to its exact test SHA | Generated topology is not proof of an attached Ethernet/PCIe packet engine; endpoint/data-path coverage differs by test |
| Xezim FlooNoC compatibility | Historical Xezim structural NoC compilations; verify twelve-mesh exact-head run separately | Data-mesh width warnings remain; no claim of Xezim NoC routed-traffic proof |
| AXI-Lite endpoint adapters | Upstream converters/mux/demux and reset register bank attached in the chip boot scope | The independent NoC BFM wrapper still uses AXI agents |
| PULP iDMA | Isolated `make dv-dma` verified RTL descriptors ([CI](https://github.com/r987r/xezim-hello-world/actions/runs/41860245485)). Generated `DmaEnable=1` instances attach to each compute data NoC and `dma_regs` config NoC; `make dv-chip-dma` **passed** the real dual-engine full-chip RTL traffic test ([CI](https://github.com/r987r/xezim-hello-world/actions/runs/41885417960), 1,902 AXI observations). | CPU0 C-side submission/polling is verified ([full-chip CPU DMA CI](https://github.com/r987r/xezim-hello-world/actions/runs/41933332567), 39,150 AXI observations); CPU ISR/service, simultaneous CPU-launched dual-DMA and physical HBM/DDR remain pending |
| Ethernet0 connected one-MAC RX/TX IP | [PR #73](https://github.com/r987r/xezim-hello-world/pull/73), [exact-head CI 42162107273](https://github.com/r987r/xezim-hello-world/actions/runs/42162107273) **4/4 Ethernet jobs PASS**: one pinned 1G MAC, GMII RX/TX and FCS, descriptor/packet DMA, 32-byte B-gated CQs, SRAM/model-DDR readback, Config/Data FlooNoCs. Real PicoRV32 C executes cold boot, programs RX/TX queue CSRs/policy, checks RX bytes, CQ/IRQ and acknowledgments; no CPU0 AXI BFM. | **Ethernet #64 MVP satisfied.** After merge, full PCIe RC reading Ethernet-produced bytes/CQ and five combined StepRecorder gates are owned by #34. Physical DDR/PCIe PHY and stress/performance remain deferred. |
| Ethernet0 local Data/Config FlooNoCs | `ethernet_mode=True` physically wires six-source PULP mux to Ethernet Data NoC and queue CSR AXI4-to-Lite through Config NoC; both BFM and real CPU0 C tests pass [CI #42162107273](https://github.com/r987r/xezim-hello-world/actions/runs/42162107273). | Default canonical `gen/chip` stays reserved and must not be misrepresented; combined variant host-route diagram/latency audit belongs to #34. |
| PCIe0 minimal host/CPU DMA path | Merged [#60](https://github.com/r987r/xezim-hello-world/pull/60), [CI 42134213227](https://github.com/r987r/xezim-hello-world/actions/runs/42134213227) passed real TLP/AXI host BAR to PCIe SRAM with CPU C/iDMA transfer to modeled DDR and return readback | No actual PCIe-host read of an Ethernet-generated packet/CQ in the same simulation yet; no physical PCIe link/PHY or outbound host-memory DMA (#76). |
| HBM/DDR controllers and PHYs | **Opt-in `chip-ddr4-real`: real pinned LiteDRAM controller RTL, 16-KiB Config NoC CSR init, real PicoRV32/PULP iDMA SRAM↔DDR and matched AXI/DFI/BankModel evidence** ([CI](https://github.com/r987r/xezim-hello-world/actions/runs/42217902632), [artifact](https://github.com/r987r/xezim-hello-world/actions/runs/42217902632/artifacts/13503312198)) | Default chip/PCIe/Ethernet modes still use AXI RAM; LiteDRAM DFI PHY and bank are behavioral; HBM controller/physical PHY, real-controller interoperability and full-chip negative-aperture closure remain outstanding |
| Chip boot `soc_top` | `make dv-chip`: real CPUs cold-boot and coordinate INIT/RUN/CHECK; `chip-cpu-dma` runs compiled C on PicoRV32 and validates SRAM/DDR/HBM roundtrips through iDMA ([CI 41933332567](https://github.com/r987r/xezim-hello-world/actions/runs/41933332567)) | CPU ISR, mixed-engine concurrent firmware and physical controller/PHY integration remain pending |

See [super-NoC verification](supernoc-verification.md) for the exact traffic
checks, local evidence, test commands and known limitations. See
[simulator compatibility](simulator-compatibility.md) for diagnostics.
The generic FlooNoC backend registry is not a universal arbitrary-SoC plugin; dedicated generated chip and BFM emitters exist.
Optional real iDMA wiring passes full-chip RTL traffic regression ([CI 41885417960](https://github.com/r987r/xezim-hello-world/actions/runs/41885417960)).
CPU C-DMA execution is verified, including the opt-in LiteDRAM controller with behavioral DFI; interrupt-service firmware, HBM controller and physical PHYs remain pending.

## Independent global NoC concurrency regression

The historical upstream `NoBResponseIdQueue` assertion at 227.52 µs (CI #42145885829) was fixed and regression-tested in [merged PR #78](https://github.com/r987r/xezim-hello-world/pull/78) on `main` `b91e3d3`. Ethernet PR #73 includes that fix and [exact-head CI 42162107273](https://github.com/r987r/xezim-hello-world/actions/runs/42162107273) is all green. Generic stress/performance limits still require their own qualification.

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
