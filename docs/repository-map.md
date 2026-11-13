# Repository map: find tests, subsystem views, and generated RTL

This is a navigation guide, not a second regression catalog. Test, SoC, and
generated RTL ownership remains with the established sources linked below.

## Finding and reviewing a test

1. Find its target with `python3 tools/stimulus_catalog.py --list`.
2. Open `config/stimulus/tests.yaml` for the authored purpose and INIT/RUN/CHECK
   description. This is **not** auto-generated execution code.
3. Use `python3 tools/stimulus_catalog.py --show <target>` for its execution
   adoption status and Python/Cocotb driver location, when present.
4. Use `python3 tools/regress.py <target> --explain` for selected simulator,
   firmware, Bender RTL targets and actual source-selection provenance.
5. The real test sequence may live in `dv/<subsystem>/test_*.py`, SV testbenches,
   or `sw/**/tests/*.c`. The source-authored YAML is not automatically
   dispatched for legacy drivers. Only `scenario_native` targets dispatch
   their typed scenario action graph.
6. For observed results, use the [Test Runs page](https://r987r.github.io/xezim-hello-world/runs.html).
   Do not treat intended steps as observed bus activity or an executed PASS.

### Ownership table

| Purpose | Authoritative code |
| --- | --- |
| SoC/subsystems, ports and address map | `config/soc.yaml` |
| IP and interface contracts | `config/ip.lock.yaml`, `config/interface_contracts.yaml`, `Bender.yml` |
| Test selection and acceptance | `config/regression.yaml` |
| Human-readable intent for all registered tests | `config/stimulus/tests.yaml` |
| Executable typed action DAGs (adopted targets only) | `config/scenarios/` |
| Existing real stimulus/checkers | `dv/`, `sw/` and scoped `rtl/memory/ddr4/` |
| Unit/contract/browser tests of infra | `tests/` |
| Regression and provenance | `tools/regress.py`, `tools/test_identity.py`, `tools/selected_rtl_provenance.py` |
| Publishing and visualization | `tools/publish_site.py`, `tools/design_explorer.py`, `tools/templates/` |
| Generator-owned default sources | `gen/` |

## Find all generated architectural views

The [Architecture Explorer](https://r987r.github.io/xezim-hello-world/explorer.html)
exposes a directory of **all** discovered subsystem groups and each local
data/config NoC, plus global fabrics. It is generated from
`gen/diagrams/noc-topology.json`, not a separate hardcoded five-subsystem
menu. Drilldown includes architecture, subsystem composition, NoC XY routers,
network interfaces and parsed RTL modules where available.

The default SoC currently declares `compute0`, `compute1`, `memory0`,
`pcie0`, and `ethernet0` and 12 FlooNoC meshes. The view is derived from
the source topology; it does not mean every opt-in PCIe/DDR/Ethernet source
was selected and compiled in the default generated SoC. Run-local
observations remain on per-test pages.

## Why gen/projects looks small

`make gen` atomically regenerates `gen/` and checks in the default
`gen/chip/soc_top.sv`, connected `gen/supernoc/`, FlooNoC modules under
`gen/noc/floonoc/`, boot images, memory fabric, diagrams and JSON manifests.
`gen/projects/xezim_soc_dv/variants/default/rtl/soc_top.sv` currently holds
a **duplicate default review top**, not all the selectable opt-in builds.

The real combined Ethernet/DDR/PCIe selected top can instead live under
ignored `.tools/regression/<target>/`; it is only archived when actually
staged with `tools/regress.py <target> --stage files`. Issue
[#184](https://github.com/r987r/xezim-hello-world/issues/184) owns the
separate task of safely promoting reproducible selected RTL to tracked
`gen/projects/`. Never copy a passing testbench's temporary top over the
default top and call it a generic project build.

## Review useful generated changes

Before a PR, regenerate and verify the complete tracked generator tree:

```sh
make gen
make check-generated
python3 tools/generated_review.py --base origin/main
python3 tools/generated_review.py --base origin/main --format json --output .tools/generated-review.json
```

The review groups changes by chip, selected variants, FlooNoC,
connected-fabric testbench, boot, memory, diagrams and verification.
For modified JSON it lists changed field paths, including topology counts,
network parameters and manifest hashes. New/deleted paths remain explicit.

This is a **source diff**, not a simulation or elaboration result.
`make check-generated` is the exact reproducibility gate. An opt-in test
also needs `tools/regress.py <target> --stage files` and
`--explain` to inspect its real compiler sources. For hardware-semantic
variant review use the existing
`tools/design_explorer.py --selected-before ... --selected-after ...`
command after staging both targets. Do not claim physical link timing or
protocol acceptance from a generated-file hash.
