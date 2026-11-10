# DMA CSR firmware registration contract (issue #90)

The existing SoC-owned `rtl/adapters/soc_dma_regs.sv` implements a 4-word CSR shim behind PULP AXI4-to-AXI-Lite infrastructure. The existing RTL remains authoritative for runtime side effects (submission and IRQ acknowledgement). `csr/rdl/soc_dma_shim.rdl` is its **software register description**, not generated replacement RTL.

## Inputs and reproducible outputs

- `config/soc.yaml`: per-instance absolute `compute*.dma` bases and apertures.
- `csr/rdl/soc_dma_shim.rdl`: per-IP offsets, field names and SW access permissions.
- `tools/csr_dma_headers.py`: produces `soc_dma_shim_regs.h` with namespaced offsets/bit masks plus compatibility aliases `SOC_DMA_*`, and `soc_dma_shim_map.json` with source/config fingerprints and instance absolute addresses.
- `python3 tools/csr_dma_headers.py --out .tools/csr-dma && python3 tools/csr_dma_headers.py --out .tools/csr-dma --check` is idempotent. Tests reject ABI drift and check legacy aliases against current code. Do not hand-edit generated files.

## Production C header migration (PR milestone)

The default real `sw/dma/dma.h` now consumes checked-in
`sw/dma/generated/soc_dma_shim_regs.h`. Its exact content is regenerated from
the existing SystemRDL by `tools/csr_dma_headers.py` and byte-compared to the
tracked production header in dedicated CI. Firmware builds do not need an
optional SystemRDL Python package installed merely to include the generated
header; source consistency is enforced by CI. An explicitly named
`SOC_USE_LEGACY_DMA_CSR` comparison switch retains old constants **only for
ABI negative and legacy binary equivalence checks**, not production builds.
Actual RV32I firmware, standalone driver translation units and linked images
are qualified in both modes, with the generated source header SHA carried in
the firmware manifest. DMA descriptors, vendor RTL and MMIO side effects
remain untouched.

**Per-variant SoC CSR bases:** the real CPU firmware compiler now consumes `soc_variant_csr_bases.h` built using the existing `tools/csrgen.py` header emitter from `config/soc.yaml`. It replaces duplicated `-DSOC_DMA0_CSR` physical addresses and, for supported opt-in builds, `SOC_PCIE_CTRL` / `SOC_ETH_CTRL`. A generated-header SHA is placed in the selected CPU firmware manifest; old-vs-new compiled binary comparison and missing CSR-window negatives are run by the dedicated CSR firmware CI. The legacy macro mode remains test-selectable for exact RV32I comparison. Generated constants do not create physical RTL or qualify AXI transactions.

**Still required for full #90 closure:** regenerate and validate project-owned
reset and Ethernet per-IP C headers, prove actual upstream iDMA/LiteDRAM
register ABI metadata and record linked RV32I ELF size, nm/section garbage
collection and real AXI parity across required variants. Production DMA **shim**
register constants no longer duplicate the RDL offsets; this milestone is not
equivalent to full per-IP register migration or independent MMIO acceptance.

DMA descriptor, completion and packet layouts remain outside the CSR map. The external PULP iDMA register bank and other vendor IPs retain upstream-generated RTL. Do not conflate our shim map with the native iDMA register definition.
