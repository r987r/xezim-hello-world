# DDR controller register catalog (CSR-DDR, #98)

This is part of the existing [SoC address-map explorer](https://r987r.github.io/xezim-hello-world/address-map.html), not a second DDR verification site. **Merged DDR-B #74 provides an opt-in real LiteDRAM controller**, while the default configuration still uses fast AXI RAM. A DDR data aperture is not itself a CSR bank.

## Source ownership and address spaces

- `config/soc.yaml`: default 1 GiB `memory0.ddr0` **data-plane** architectural aperture at `0x140000000`, but only 64 KiB of default AXI RAM modeled backing. Default `memory0.ctrl` **configuration-plane** aperture is 4 KiB, reserved for a controller not active in this build.
- `tools/ddr_chip.py`: deterministic real-DDR test variant enlarges `memory0.ctrl` to **16 KiB** at `0x40030000`, uses the original independent configuration NoCs, and substitutes real upstream LiteDRAM and low 32 MiB of DFI/BankModel backing.
- `.tools/ddr4/litedram_sim/csr.json`: actual **pinned upstream LiteDRAM/LiteX generated CSR register definitions**, including addresses, word sizes and software RO/RW access. Do **not** regenerate the vendor RTL from our PeakRDL files.
- `.tools/regression/chip-ddr4-real/ddr_noc/ddr4_init_script.json`: exact derived Wishbone-byte-address translation from LiteDRAM to SoC Config NoC. Relative address = native Wishbone register address minus the validated `generated_wb_base`. Physical address = `0x40030000 + relative address`.
- `tools/ddr_csr_catalog.py` emits `.tools/regression/chip-ddr4-real/ddr-native-csr-map.json` with the exact variant/config/CSR/translation hashes. Multiword registers are represented as distinct **32-bit CSR words**. Registers outside the physical 16 KiB translated window are identified as unmapped in the metadata, **not** falsely presented as reachable.
- No field names, reset values, read-clear or W1C behavior are invented where upstream `csr.json` lacks such information.

## Real run report and released Pages

The real `chip-ddr4-real` test's existing `report.html` and `axi-transactions.json` now contain `sections.address_map` with **14 SoC apertures**, the native `memory0.ctrl` CSR words and 32 MiB backed `memory0.ddr0` data aperture. Register observations count only actual completed, passive AXI Config-NoC transactions. A declared register is **not** counted as tested if no such transactions were captured.

The GitHub Pages **Address Map** page has a `SoC build / register provider` selector. It defaults to the baseline architectural map (no fake DDR registers), and adds independent `Real LiteDRAM` choices only when a successful DDR run and its provenance-verified `axi-transactions.json` were included in the site's collected CI evidence. That selector links back to the corresponding actual run report, preserving the source SHA and workflow ID. If those artifacts are missing or expired, the page states that the verified DDR CSR view is unavailable rather than fabricating register details.

## Verification and commands

The focused tests are:

```sh
python3 -m unittest tests.test_ddr_csr_catalog tests.test_ddr_csr_pages -v
```

The existing `.github/workflows/ddr4-fullchip.yml` builds pinned LiteDRAM, regenerates the exact native catalog, runs the real CPU/iDMA/DFII scenario and asserts 16 KiB / 32 MiB variant metadata, native register word count, tested register addresses and passive Config-NoC read/write traffic. The regular Pages and CSR workflows run the lightweight catalog and publication tests.

This work is orthogonal to #79 stimulus, #39 SRAM/DDR/HBM back-door providers and #90 generated custom firmware C headers. Importing vendor metadata is not replacing LiteDRAM, making a new CSR bus, or proving a physical DDR PHY.
