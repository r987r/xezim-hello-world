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
and CPU flash **runtime images**, plus the combined global and local FlooNoC
SystemVerilog. Image SHA checks run against the generated-image inventory;
boot ROM and flash are **not** incorrectly required to appear in the
SystemVerilog compiler source list. This behavior is tested by exact-head CI.

Three independent successful/failed selected-source artifacts from runs
42561215396 (#194), 42616967673 (#196), and 42661261032 (#201) expose an
important LiteDRAM generator limitation: the pinned `soc_ddr4_sim.v`
output SHA varied across these runs, despite source-identical top and selected
Bender filelist, and the controller functional runs at #194/#196 passing.
The generated DDR RTL SHA is therefore **explicitly labeled unstable and
unqualified**; no equivalence between those three DDR RTL bytes is inferred.

The historical reference pins a stable compiler-input projection SHA256
`b5b8447bf223fa53af0e7226a68f94d0717f5328ce08956ec3a67347e5cc4578`,
computed from **311 selected stable source digests out of 312**, the
byte-identical Bender filelist SHA256
`d86d2bb808b2a31cb242997f2dcbca7c41acfda8f3ff39f8a74ce64f51c40a32`,
the exact config and selected-definition hashes, defines, args, include
header hashes and NoC source lists. Every source and compiler-input field
still passes the existing `verify_selected_archive` byte validation first;
any change outside the *one explicit variable DDR source* fails the pinned
projection check. The original complete compiler-input SHA from #194
`399222eb50d3fc58244885fe39502f2ce2955ed49144a7926ff8641d82c1e24f`
is preserved as a historical reference, **not** silently required to match
later, variable DDR RTL.

A separate deterministic LiteDRAM generation/equivalence gate is required
before #184 signoff. The source checker never upgrades source matching to
elaboration, real DFI transactions, or physical DDR4 PHY proof.

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
