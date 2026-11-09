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
