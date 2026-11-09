# Stage exact selected combined RTL for review (#184)

The compiler's real Ethernet+DDR+PCIe SoC top is **not** the default
\`gen/chip/soc_top.sv\`. This tool reuses the *existing selected archive* and
verifies each source and archived generated artifact before copying into a
review area under \`.tools/\`, **never** into generator-owned \`gen/\`.

\`\`\`sh
python3 tools/regress.py chip-ethernet-ddr-pcie --stage files
python3 tools/regress.py chip-ethernet-ddr-pcie --explain
python3 tools/stage_selected_rtl.py --profile chip-ethernet-ddr-pcie
\`\`\`

The command writes
\`.tools/rtl-review-staging/xezim_soc_dv/soc-ethernet-ddr-pcie/\`.
The manifest records the exact selected RTL SHA, complete compiler-input
source hashes, selected generated top, copied generated files and original
compiler filelist. It explicitly says \`generator_reproducible: false\`,
\`bit_connectivity_proven: false\` and
\`protocol_traffic_observed: false\`.

**Staging is not promotion.** It is a fail-closed review artifact. The
subsequent #184 milestone must re-generate this variant from authoritative
project/IP configuration, compare identical byte/source hashes, emit it
under \`gen/projects/...\` via generator-owned outputs and run the real
slang/combined acceptance gates. A CI run's one-time copied result is
insufficient for \`make check-generated\` and must not be checked in as such.

## Tamper-evident staged metadata

The staged `manifest.json` now includes a canonical `manifest_sha256`
for its *own* metadata, separate from the original `selected-rtl-manifest.json`
source attestation. Rechecking the stage fails on a changed source profile,
selected source hash, compiler filelist SHA, selected top, or stale/corrupt
manifest—even if the SV bytes themselves are untouched. `--replace`
requires the existing stage to verify before it can be overwritten.
This is a deterministic self-integrity check, **not a digital signature or
proof the compiler generated correct hardware**. The real source archive
must still be verified against the selected regression plan.
