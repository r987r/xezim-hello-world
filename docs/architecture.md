# Architecture and IP contracts

This document specifies **logical connectivity separately from RTL implementation**. `config/soc.yaml` is authoritative; nothing under `gen/` is hand-edited. All generated outputs (including real upstream-generated FlooNoC RTL, one whole-chip SoC image, and machine-readable router/endpoint graph) are checked into `gen/`. `make gen` replaces the tree and deletes stale files; `make check-generated` verifies exact output bytes and names without changing the repository.

The [README](../README.md) embeds **one canonical whole-chip diagram**. Detailed connections are retained in JSON and in FlooGen's checked-in generated RTL/YAML, not additional images. Connectivity metadata follows the explicit instances/connections model in the owner's `Diagram-gen` and `Sv-diagrams` repositories; verification scopes follow `Sv-test`. There is no 3D viewer dependency.

## Boot and SRAM loading

CPU0 (PicoRV32) is the primary boot core. CPU1 (SERV) stays in reset until CPU0 has copied both firmware images from the read-only flash model into blank SRAM, then writes the reset-control MMIO register. The older standalone boot scope remains independent. The new chip boot configuration runs the same ROM-copy policy through real local/global NoCs; the flash transport is still a model. Read [boot.md](boot.md) for the exact address map, bus transactions, limitations and next steps. A controller configuration aperture at 0x40030000 is reserved in the generated global/local config NoCs; real controller CSR RTL remains absent.

## Structure

- Compute 0 instantiates `picorv32` (AXI4-Lite CPU interface), SRAM and local data/config NoCs in the boot configuration. Its selected `pulp_idma` is instantiated when `DmaEnable=1` (the default cold boot disables it).
- Compute 1 instantiates `serv` (Wishbone-style instruction/data interfaces), SRAM and local data/config NoCs. Its selected `pulp_idma` is likewise generated and instantiated when enabled.
- Memory 0 contains independently generated local data and configuration FlooNoCs and one HBM + one DDR behavioral model. The chip attaches a 1×2 Verilog-AXI crossbar at the single local-NoC target endpoint. The older independent 2×2 crossbar test still checks both inputs against both targets.
- Global data and global configuration FlooNoC meshes are independent. The config NoC uses AXI4 wire transport. Upstream AXI4-Lite adapters are selected for CSR boundaries but are not attached in the BFM test. Both compute SRAM destinations are used by chip-level CPU0-to-CPU1 cold boot.

## Stable contract vs backend

The generator first validates an abstract graph of **initiators, targets, boundaries, address windows, and NoC ports**. It produces `gen/noc/fabric_ir.json`. The pinned upstream FlooGen generator now emits real structural module/package pairs under `gen/noc/floonoc/` for every local/global network, and `tools/full_chip_gen.py` assembles the CPU boot configuration around the same shared NoC core. General iDMA/controller integration remains pending. The separate connected NoC BFM test does run real routed RTL traffic.

| Network | Backend | Actual status |
| --- | --- | --- |
| Memory target crossbar | `verilog_axi` | Chip boot: 1×2 under Verilator; independent memory stress scope: 2×2 under Xezim |
| Compute0 local data + config | `floonoc` | BFM scope plus CPU/SRAM/reset boot-configuration wiring; real iDMA/CSRs generated behind DmaEnable (new full-chip regression) |
| Compute1 local data + config | `floonoc` | BFM scope plus CPU/SRAM/reset boot-configuration wiring; real iDMA/CSRs generated behind DmaEnable (new full-chip regression) |
| Memory0 local data + config | `floonoc` | BFM scope plus attached chip target crossbar/AXI memory stand-ins |
| Global data | `floonoc` | Six-router XY mesh; routed SRAM/memory-window traffic passes in the connected BFM scope |
| Global config | `floonoc` | BFM scope plus upstream CPU/reset AXI-Lite adapters in chip boot |

All eight structural tops/packages, generated upstream FlooGen YAML inputs,
and native MaxTxns/MaxUniqueIds/read/write RoB bindings are tracked in
[the NoC manifest](../gen/noc/floonoc/manifest.json). For AXI-Lite
control traffic follow [the no-custom-bridge upstream reuse guide](axi-lite-over-floonoc.md).
**Generated SystemVerilog is not proof of independent elaboration, IP
integration, or successful AXI transactions.**

`tools/noc_backends.py` is an explicit backend registry. A new vendor implementation must provide port transformations, parameter translation, source resolution, ID widening or remapping, address decoding, and ordering/route checks. A vendor switch is not guaranteed safe merely because the configuration parses.

### CPU adapters

- `picorv32_cpu_adapter.sv` exposes a real PicoRV32 AXI4-Lite initiator. The chip uses upstream AXI-Lite conversion and data upsizing; 32-bit addresses zero-extend without high-address remapping.
- `serv_cpu_adapter.sv` exposes SERV's separate Wishbone-style instruction and data ports. The chip uses ZipCPU Wishbone bridges and PULP instruction/data arbitration; the old request-only smoke remains independent.
- Both CPU implementations are actual open-source RTL with immutable source pins. Firmware executes in both the older standalone cold-boot scope and the new CPU-coordinated chip boot configuration. Interrupts, caches and coherent memory remain future work.

### DMA adapter

Both compute templates select pinned `pulp_idma`. The reusable frontend/backend
passed the independent Verilator+AXI regression, and the full-chip generator
now attaches a real engine to each compute DMA port plus a CSR/doorbell
bridge at each config endpoint. The new `chip-dma` test drives both engines
through the real hierarchy but requires a green CI result to establish
end-to-end proof. The standalone NoC BFM does not instantiate DMA. The final DMA must support source/destination addresses anywhere in the global data map and both HBM/DDR targets.

### Memory adapters

The independent memory scope uses `axi_memory_target_model.sv` and public Verilog-AXI `axi_ram`; its HBM/DDR profiles differ in pipeline configuration, names and addresses. The chip boot scope uses `axi_sram_target.sv`, upstream PULP `axi_to_detailed_mem` and `tc_sram`, with a bounded 64-KiB model per target. Neither establishes HBM/DDR timing accuracy or physical controller support.

For a full DDR path, generate a LiteDRAM standalone Verilog controller with AXI access and the supported DFI SDRAM simulation PHY/model, then create an AXI adapter matching our 64-bit global interface. Keep that controller test scoped separately from the fabric regression.

HiSA HBMController's public RTL uses AMD/Xilinx HBM IP for PHY and a documented Questa/Vivado flow. Its vendor PHY is not open source. A standalone `hisa_hbm` emitter must therefore be gated on availability of that environment and should not silently fall back to a behavioral AXI RAM. Open-source HBM timing models such as DRAMsim3 may later provide *system-level timing*, but they are not interchangeable with a silicon PHY.

### Scaling invariants

- No overlapping or out-of-bounds address regions.
- Every target has an explicit address map, and configured ports have reachable destinations.
- AXI source IDs remain unique through aggregation and return correctly; same-ID ordering is preserved.
- No unbuffered combinational loops between interconnect stages.
- No implicit coherence. Explicit synchronization is required for CPU/DMA shared buffers.
- Any generated executable scope must reject an unavailable backend (never produce a pretend substitute).

## One source-derived whole-chip FlooNoC diagram

FlooGen generates the router/link modules and immutable profile YAML
for all local/global data/config networks. The **single** visual is
[full SoC connectivity](../gen/diagrams/noc-hierarchy.svg), with
[Mermaid](../gen/diagrams/noc-hierarchy.mmd) and
[Diagram-gen-style instance/connection metadata](../gen/diagrams/noc-topology.json)
for detailed inspection. There are no per-mesh/per-subsystem/boot/verification
SVG duplicates. Solid CPU/SRAM/reset/model links describe boot-configuration
wiring; solid optional iDMA/CSR links follow generated SoC RTL; dashed links denote
pending physical controllers. The BFM
and CPU boot scopes share `soc_noc`; independent memory and legacy boot
tests remain preserved. See [chip boot](full-chip-boot.md).

## Generated 2D previews

The README embeds one committed static SVG generated from upstream FlooGen mesh metadata. The corresponding Mermaid and JSON graphs live in `gen/diagrams/`. `make check-generated` verifies the exact image and README link; `make gen` deletes obsolete diagrams. The vector renderer uses only the Python standard library; GitHub/mobile clients do not need Mermaid support.
