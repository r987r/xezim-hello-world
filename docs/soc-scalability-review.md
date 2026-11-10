# Review a SoC hardware variant and its executable tests

This is an **inspection and reproduction guide**, not a duplicate generator or progress tracker. The parent [scalability epic #162](https://github.com/r987r/xezim-hello-world/issues/162) and individual issues own progress. The authoritative project SoC is [config/soc.yaml](../config/soc.yaml), the test and selected backend inventory is [config/regression.yaml](../config/regression.yaml), and build identity is resolved by [tools/test_identity.py](../tools/test_identity.py).

## Find the real RTL, not a diagram

The tracked [default top](../gen/chip/soc_top.sv) and [generated NoC](../gen/supernoc/soc_noc.sv) are generated and hash-recorded under [gen/manifest.json](../gen/manifest.json). They describe the **default** configuration. They are not necessarily the top that an opt-in Ethernet, PCIe, CPU/iDMA, or LiteDRAM regression compiles. Optional tests can substitute source under `.tools/regression/<target>/variant/soc_top.sv`, which is ignored by Git.

For an existing target, inspect selection and evidence **without** compiling:

```sh
python3 tools/regress.py chip-boot --explain
python3 tools/regress.py chip-ethernet-ddr-pcie --explain
python3 tools/hardware_variants.py --out .tools/variants/catalog.json
```

The first command reports test lineage, execution category and, **if an archive already exists**, SHA-verified exact source selection. A missing archive is not a successful build. The hardware-variant catalog groups tests by the same build, but its `declared_only_not_compiled` status is intentionally unverified.

With pinned upstream tools installed (see [regression setup](regression.md)), resolve the **actual** compiler source lists and selected RTL:

```sh
python3 tools/regress.py chip-ethernet-ddr-pcie --stage files
python3 tools/regress.py chip-ethernet-ddr-pcie --explain
```

The selected input record is `.tools/regression/chip-ethernet-ddr-pcie/selected-rtl-manifest.json`; its SHA-named `selected-rtl/` archive contains generated inputs. The source filelist is `.tools/regression/chip-ethernet-ddr-pcie/sources.f`. View the exact compiler-resolved top named by `selected_soc_top` in that manifest, **not** an assumed path. The `--explain` recheck detects modified/foreign sources, missing generated files, identity drift and changed header/filelist inputs. Re-running `--stage files` selects sources; it does **not** execute a simulator or establish functional correctness.

## Rebuild the selected combined hardware source without simulating

Use the [selected variant rebuild guide](build-hardware-variant.md) to invoke
the existing Bender/FlooGen/LLVM source-selection pipeline for a named
opt-in configuration. The CLI runs `regress.py --stage files` and stages
its SHA-verified actual selected RTL; `--check` independently regenerates
the same sources into a separate temporary directory and rejects drift.
It does not overwrite the baseline and does not imply passing a simulator.

The reviewed generated **default** RTL remains checked into `gen/projects/`.
The combined RTL is still staged under `.tools/` pending the full #184
generator-owned promotion gate. Neither source hash nor pass-through test
metadata proves the actual AXI/PCIe/Ethernet/DDR hardware path.

## Compare two exact selected builds

Resolve both profiles into source archives, then use the **existing** Architecture Explorer diff utility:

```sh
python3 tools/regress.py chip-boot --stage files
python3 tools/regress.py chip-ethernet-ddr-pcie --stage files
python3 tools/design_explorer.py --selected-before chip-boot --selected-after chip-ethernet-ddr-pcie --format markdown --output .tools/selected-rtl-diff.md
```

This compares source hashes and bounded text changes of the **selected generated** SystemVerilog tops, with source-integrity checks. It does not prove every elaborated pin connection, signal width, CDC path, or accepted AXI/TLP/GMII transaction. Cross-check bit-level work in [#46](https://github.com/r987r/xezim-hello-world/issues/46); do not relabel source-only edges as verified wiring.

## Review the generated source tree in a PR

`make gen` writes the **generator-owned** default `gen/` tree; `make check-generated` verifies identical paths, bytes and README without changing tracked outputs. On the current mainline, compare [gen/chip/soc_top.sv](../gen/chip/soc_top.sv) directly. The generator-owned [default variant review top](../gen/projects/xezim_soc_dv/variants/default/rtl/soc_top.sv) and [adjacent SHA manifest](../gen/projects/xezim_soc_dv/variants/default/manifest.json) were merged in [PR #178](https://github.com/r987r/xezim-hello-world/pull/178) after 7/7 exact-head workflows passed. This is a byte-exact copy of the default generated top, not a test-selected combined variant. The selected combined Ethernet/DDR/PCIe RTL is **different** from the default top and needs a reproducible, source-verified variant-promotion step under [#163](https://github.com/r987r/xezim-hello-world/issues/163) before it may be called checked in.

The canonical IR from [tools/soc_ir.py](../tools/soc_ir.py) and typed contracts from [tools/soc_ip_compose.py](../tools/soc_ip_compose.py) are **declarative**, not yet full replacements for the legacy RTL emitters. The atomic generator's IR/IP source-consistency gate **merged in [#177](https://github.com/r987r/xezim-hello-world/pull/177)**; the default reviewable RTL **merged in [#178](https://github.com/r987r/xezim-hello-world/pull/178)**. [#193](https://github.com/r987r/xezim-hello-world/pull/193) subsequently merged IR-derived default review-artifact identity; it does **not** establish generic IR-driven RTL wiring. No generic hardware composition is established merely by generating a manifest.

## Tell planned actions from completed hardware

The canonical source-selected scenario is resolved by [tools/scenario_plan.py](../tools/scenario_plan.py). The [Python action dispatcher](../dv/common/action_runtime.py) supports typed dependencies, shared resource/retirement locks and causal event actions. The [C11 action table emitter](../tools/scenario_c.py) and [SV emitter](../tools/scenario_sv.py) reuse the same plan identity. Most multi-protocol legacy tests are **not** yet fully migrated into these handlers. A driver's `issued` or `driver_done` record is not AXI/TLP/GMII/DFI protocol acceptance, independently checked bytes, or a valid mailbox hardware event.

Consult the [runtime design and gap analysis](scalable-stimulus-runtime.md), [regression reporting](regression.md), [implementation boundaries](implementation-status.md), and [live test evidence](https://r987r.github.io/xezim-hello-world/) before calling a flow qualified. Missing or incomplete independent observations must remain **unmeasured**.
