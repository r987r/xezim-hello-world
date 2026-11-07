# DMA CSR firmware registration contract (issue #90)

The existing SoC-owned `rtl/adapters/soc_dma_regs.sv` implements a 4-word CSR shim behind PULP AXI4-to-AXI-Lite infrastructure. The existing RTL remains authoritative for runtime side effects (submission and IRQ acknowledgement). `csr/rdl/soc_dma_shim.rdl` is its **software register description**, not generated replacement RTL.

## Inputs and reproducible outputs

- `config/soc.yaml`: per-instance absolute `compute*.dma` bases and apertures.
- `csr/rdl/soc_dma_shim.rdl`: per-IP offsets, field names and SW access permissions.
- `tools/csr_dma_headers.py`: produces `soc_dma_shim_regs.h` with namespaced offsets/bit masks plus compatibility aliases `SOC_DMA_*`, and `soc_dma_shim_map.json` with source/config fingerprints and instance absolute addresses.
- `python3 tools/csr_dma_headers.py --out .tools/csr-dma && python3 tools/csr_dma_headers.py --out .tools/csr-dma --check` is idempotent. Tests reject ABI drift and check legacy aliases against current code. Do not hand-edit generated files.

## Opt-in production-code compilation

The real `sw/dma/dma.h` now accepts `SOC_USE_GENERATED_DMA_CSR`. With that macro and the output directory on the include path, `sw/dma/dma.c` consumes the generated definitions. Without the macro, legacy definitions remain available to existing firmware builds. Both modes are cross-compiled as freestanding RV32I in the focused CI; register layout, mask/shift and descriptor semantics must remain identical.

**Not yet complete:** runtime CPU firmware variants do not automatically define `SOC_USE_GENERATED_DMA_CSR`; that requires updating their target-specific include configuration, linked ELF size baselines, AXI tests and release manifests in a later sub-step. The generated header adds no data tables or executable code by itself; linker GC and actual linked image sizes must still be measured. Do not claim all firmware uses generated headers until those gates pass.

DMA descriptor, completion and packet layouts remain outside the CSR map. The external PULP iDMA register bank and other vendor IPs retain upstream-generated RTL. Do not conflate our shim map with the native iDMA register definition.
