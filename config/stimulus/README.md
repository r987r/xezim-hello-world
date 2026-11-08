# Stimulus specifications — reviewable, not generated

**Start here to understand what any test is trying to do:** [tests.yaml](tests.yaml).
This is the source-authored human-readable stimulus catalog for every test
registered by `config/regression.yaml`. To inspect it without running RTL:

```sh
python3 tools/stimulus_catalog.py
python3 tools/stimulus_catalog.py --list
python3 tools/stimulus_catalog.py --show chip-ethernet-cpu
```

## One ownership boundary for each thing

| Authority | Location | Responsibility |
| --- | --- | --- |
| RTL/build/simulator/memory/firmware selection | `config/regression.yaml` | How and where the test runs |
| Source reviewable stimulus intent | **`config/stimulus/tests.yaml`** | Why it runs, INIT/RUN/CHECK outline and execution adoption |
| Typed executable scenario DAG (today only SCN-2) | `config/scenarios/cpu-bfm-ddr-roundtrip.json` | Actual action parameters, dependencies, actors, seed |
| Adapter implementation | `dv/`, `sw/`, `tools/` | Real Python/C/SV dispatch; must follow/validate the typed plan |
| Selected run and evidence | `.tools/regression/…`, then canonical published run | Generated run-specific plan and actual passive/checker evidence |
| Generated RTL and architecture | `gen/` | Derived hardware outputs, not human-authored test stimulus |

**Do not put authored stimulus into `gen/`**: generated code can be
deleted/recreated. Test intent must survive and be reviewable in Git.

Every test has exactly one canonical `logical_test`; multiple selected
regression targets can implement the same behavior (e.g. CPU C versus BFM,
relocated boot, synthesis guard). The loader cross-checks all registered
targets, catches stale/missing/duplicate entries and verifies a test's
`logical_test` against its naming source once #137 has merged.

## Truth about migration

`scenario_native` means an actual source-resolved action DAG is executed.
`observed_milestones` means real observed checkpoints are validated, but
internal stimulus is **still not dispatched by the common scenario executor**.
`legacy_opaque` means the YAML describes the high-level *existing* bench;
the Python/C/SV code still decides the actual internal sequence.
`non_runtime` covers lint/compile-only targets and has no INIT/RUN/CHECK
stimulus. YAML descriptions are **not hardware evidence** and never create PASS.

As #119 progresses, move specific action parameters and dependencies from
opaque code into the existing SCN action runtime, then change the verified
adoption status in this one YAML. **Never** add a fake source-declared action
that claims RTL acceptance without independent AXI/TLP/GMII/DFI/checker evidence.
For randomness use the shared scenario resolver with an *explicit recorded*
seed and resolved parameters. This is directionally aligned with Accellera
PSS, OpenTitan's testplan, and riscv-dv testlists without adopting another
runtime or vendor-specific test naming scheme.

Before adding or renaming any regression test, update this file in the
same PR. The Test Runs view uses the checked-in description before simulation,
derives direct links to existing Cocotb/Python driver source paths from the
regression entrypoint (or the Bender source target and SV top for Xezim),
and archives the exact selected intent digest in each run's immutable plan.
Historical runs never borrow a newer spec as if it were their original plan.
