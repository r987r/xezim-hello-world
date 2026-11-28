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

**Qualification boundary:** This CLI stages and compares actual selected
sources; it neither runs a simulation nor writes the tracked `gen/projects`
tree. It requires pinned Bender, FlooGen, clang/LLVM and upstream IP. For
independent replay of the tracked combined variant and separate real combined
simulation, see the [combined CI workflow](../.github/workflows/dv-combined34.yml)
and the generator target below. Do not copy a one-time CI snapshot into `gen/`.

## Tracked CPU/iDMA review reference (#163)

The [CPU/iDMA reference](../config/selected-rtl-reference/cpu-dma/) shows the
actual selected top, bench and metadata for review, alongside the ordered
compiler input coordinates and hashes. These files are not runtime inputs.
The existing source generator still selects its own immutable workspace.

With the existing CPU/iDMA CI toolchain installed, run from a clean checkout:

```sh
python3 tools/build_hardware_variant.py --profile chip-cpu-dma --check-tracked
python3 tools/build_hardware_variant.py --profile chip-cpu-dma --check
```

The first command compares all tracked bytes to a fresh files-only run.
It removes the checkout prefix only from verified include/source coordinates
and substitutes placeholders for the five known run-local image references.
All other generated contents, input digests, flags and ordering still
participate in the comparison. The second command independently rebuilds
the original selection in another run directory. Neither command runs the
simulator or rewrites the tracked reference.

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

This is a **named selected variant publisher**, not a second SV generator.
Normal `make gen` and `make check-generated` do not install or run the
heavy opt-in pinned controller/PCIe toolchain. If the named subtree is
present, they verify its ownership, config, file inventory and hashes
before preserving it during default generation. To create or independently
rebuild the named subtree, use the combined targets above. CI compares the
tracked bytes to a fresh selected-source replay without rewriting or
pushing files, independently elaborates the portable tree, then runs
the original combined transaction checker against its selected inputs.
Source replay and elaboration are not bit-level proof or issue closure.

The original 312-source compiler-input SHA in the selected run archive
can include checkout-absolute compiler/include paths, so it is **not**
copied as a supposedly cross-machine-stable generated manifest digest.
The portable generated manifest instead fingerprints the relative ordered
312-entry filelist, all actual pinned source/header SHA values, generated
bytes, defines and source configuration. The original absolute-path
fingerprint remains in the original verified run attestation; older references
retain their historical path coordinates.
A test regenerates the same source under two different checkout directories
and requires exact portable manifest and compiler filelist bytes. The
portable copy is separately elaborated by Verilator in the existing CI, but
this alone is not bit-level interconnect proof (#46).
