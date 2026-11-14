# Rebuild a selected hardware variant using the existing generator

The full-chip Ethernet+DDR+PCIe hardware variant is **not** the tracked
default `gen/chip/soc_top.sv`. This tool invokes the **real**
`tools/regress.py --stage files` path, which composes selected generated
DDR NoCs, real CPU0 firmware, Ethernet packet engines and PCIe source
dependencies. It does not duplicate those RTL emitters or bypass pinned
compiler inputs.

```sh
python3 tools/build_hardware_variant.py --profile chip-ethernet-ddr-pcie
python3 tools/build_hardware_variant.py --profile chip-ethernet-ddr-pcie --check
```

The first command resolves and regenerates selected source inputs, then
calls the exact archive verifier and stages the selected files under
`.tools/rtl-review-staging/<project>/<variant>/`. The second command
regenerates to a **separate temporary review stage** and compares
the selected `soc_top.sv` digest and full compiler-input/source-closure
digests against the existing baseline without overwriting it. Each captured
manifest is verified for tampering first. The source manifest's full document
SHA and the staged manifest's self-SHA can legitimately change because a new
run has a distinct `identity_sha256`; those two *provenance-document hashes*
are excluded from the source-equivalence comparison, while the original
per-run SHA records stay available for audit. All source, filelist, header,
selected RTL, firmware, configuration, and generated-file digests remain
strictly compared, with bounded changed-path diagnostics on failure.

A compiler source, filelist, pinned include, firmware image or generated
RTL change must be resolved and reviewed explicitly; it cannot be silently
renamed the same hardware build.

**Qualification boundary:** This script is actual selected source
*generation*, not simulation, validated bit connectivity, or generator-owned
checked-in `gen/projects` output. It depends on pinned Bender, FlooGen,
clang/LLVM and upstream IP being installed. CI currently verifies the
CLI's scheduling/reproduction/rejection logic with mocked runner calls;
a real default/combined source rebuild + passive simulation acceptance
must still be qualified before #184 can close. Do not copy a one-time CI
snapshot into `gen/`; issue #184 tracks canonical generator integration.

## Generator-owned combined RTL (P0 #184)

The canonical generator now has an **opt-in** publication target, built from
the same live `regress.py chip-ethernet-ddr-pcie --stage files` source
selection rather than from a downloaded CI archive:

```sh
# After the existing dv-combined34 pinned Bender/FlooGen/LiteDRAM/C tools
# have been installed and real LiteDRAM Verilog generated:
make gen-combined
make check-generated-combined
```

Both commands **re-run** the source-selected emitter, independently verify
the original selected-source archive, and check exact per-file SHA values.
The generated source-review tree is
`gen/projects/xezim_soc_dv/variants/ethernet-ddr-pcie/`. It contains
the actual selected top, real local/global DDR FlooNoC RTL, CPU firmware
and ROM images, compiled CPU ELF, selected testbench sources, pinned
LiteDRAM controller Verilog, plus the original full compiler source-hash
inventory. The published top, testbench and firmware metadata use stable
`gen/projects/` image paths instead of the previous ephemeral
`.tools/regression/` references. These are the *only* source text edits
to the selected original top and testbench; both raw and published SHA values
are recorded. A missing image, extra temporary reference, unknown emitted
source category, 312-source closure change or modified checked-in file
fails without passing.

This is the first reproducible **named selected variant publisher**, not a
second SV generator. Normal `make gen` and `make check-generated` still
cover the lightweight default variant and do not install or run the heavy
opt-in pinned controller/PCIe toolchain. Therefore, **the combined variant
is not fully integrated with the default atomic generator lifecycle yet**:
a later default `make gen` can still replace `gen/` and remove the
combined subtree. Before #184 closes, combine these into one coordinated
atomic `make gen`/check-generation publication and commit actual bytes
produced by final-head CI; prove the portable generated RTL elaborates and
passes the existing real combined transaction checker. Do not treat an
artifact upload or this opt-in generator as issue closure.

The original 312-source compiler-input SHA in the selected run archive
can include checkout-absolute compiler/include paths, so it is **not**
copied as a supposedly cross-machine-stable generated manifest digest.
The portable generated manifest instead fingerprints the relative ordered
312-entry filelist, all actual pinned source/header SHA values, generated
bytes, defines and source configuration. The original absolute-path
fingerprint remains in the verified `.tools/regression/` run attestation.
A test regenerates the same source under two different checkout directories
and requires exact portable manifest and compiler filelist bytes. The
portable copy is separately elaborated by Verilator in the existing CI, but
this alone is not bit-level interconnect proof (#46).
