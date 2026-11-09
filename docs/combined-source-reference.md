# Qualified combined SoC selected-source reference (#184)

The checked-in file `config/selected-rtl-reference/ethernet-ddr-pcie.json`
records **historical source SHA anchors** from [the successful real combined
RTL/DV Actions run](https://github.com/r987r/xezim-hello-world/actions/runs/42561215396)
on [merged PR #194](https://github.com/r987r/xezim-hello-world/pull/194)
(exact PR head `190793b0b943cf3bfd44aedb8ca22f81ff1e0374`).
The archived `soc_top.sv` was 134,133 bytes with SHA256
`022d75416267777e6fcf3be8f5823dbe838116c46b722e27b8cd7f065700d3c4`.
This is **not** a manually copied replacement for an SoC generator output.

The source-reference test locks the actually selected combined top, boot ROM
and CPU flash images, the combined global NoC, representative local/global
FlooNoC data/config source files, and the pinned LiteDRAM simulation backend.
All source and include files, compiler flags and the filelist are independently
verified by the existing `verify_selected_archive` implementation: a small set
of historical SHA anchors is intentionally *not* misrepresented as a complete
second 312-file lockfile. The reference is checked **after** exact selected
source preparation, archival verification and independent regeneration.
The original run-specific `identity_sha256` is not a hardware change.

Local selected source preparation (with locked Bender/FlooGen/LiteDRAM/LLVM):

```sh
python3 tools/regress.py chip-ethernet-ddr-pcie --stage files --fail-fast
python3 tools/stage_selected_rtl.py --profile chip-ethernet-ddr-pcie
python3 tools/build_hardware_variant.py --profile chip-ethernet-ddr-pcie --check
python3 tools/selected_source_reference.py --profile chip-ethernet-ddr-pcie
python3 -m unittest tests.test_selected_source_reference -v
```

A source anchor mismatch is a real **review-required change**. It must fail CI,
not be overwritten with the latest passing build without investigating the
source/RTL/firmware changes and independently qualifying the changed hardware.
The fast unit workflow tests failures on selected top, NoC, firmware, DDR,
missing compiler inputs and provenance. The existing combined RTL workflow
then exercises the actual checked selected hardware.

## Not satisfied yet

- This historical source lock is **not** the generator-owned
  `gen/projects/xezim_soc_dv/variants/ethernet-ddr-pcie/` output promised in
  #184. That requires changing the one atomic `tools/generate.py` pipeline to
  produce the actual selected generated RTL and complete source closure
  deterministically, with `make gen` / `make check-generated` and stale
  cleanup on the same output. Do not commit a snapshot from this CI artifact.
- The absolute `.tools/regression/.../variant/flash.hex` and `bootrom.hex`
  references inside the selected SystemVerilog are still build-scoped.
  A generator-owned review copy must specify a deterministic, supported
  image path transformation and compile-byte equivalence; renaming a file
  without checking SystemVerilog references is not valid.
- A passing selected source SHA check is **not** selected netlist/port-bit
  connectivity (#46), physical DDR/PCIe PHY evidence, accepted passive protocol
  transfer, or a new test-independent generic IP/SoC emitter (#165/#166).
  The prior combined-chip simulation passed independently on PR #194, not
  by virtue of this source-reference lock.
