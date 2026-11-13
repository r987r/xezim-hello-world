# GitHub Pages verification hub

The [verification hub](https://r987r.github.io/xezim-hello-world/) publishes the **current main-source** README, documentation, one generated topology and source-qualified CI evidence. `.github/workflows/pages.yml` builds/collects and deploys using GitHub Actions Pages; PRs get offline previews, while trusted merge-to-main or manual `main` dispatches deploy. The GitHub Pages environment records the deployed source SHA.

## What is published

- **Architecture:** source-generated Data/Config FlooNoC links, address map, discovered RTL instance hierarchy and source provenance. A drawn/declared edge is **not** an elaborated port or accepted packet.
- **Test Runs:** selected regression catalog (including never-run tests), original tested source/attempt, result/negative acceptance, logs, original plan/filelists, scenario/step evidence, and actual AXI/TLP/GMII/DFI observations when available. Historical archives remain explicitly historical.
- **Fabric Explorer:** source-derived route/NI/XY path inventory, outstanding budgets, read/write comparisons and original captures. Actual latency requires complete, clean, source-compatible **serial one-beat** AXI observations at each stated boundary. A route without suitable evidence is **unmeasured**, not zero.
- **Address Map/CSR:** SoC physical apertures and source-owned register definitions, with selected real-DDR CSR layouts where qualified. DDR4 MR0–MR6 are labeled device-command definitions, not CPU-addressable registers. Executed register accesses and DDR MRS observations remain in test-specific reports.

Each test has an original **tested SHA** distinct from the currently deployed site SHA. A green old workflow or copied JSON is not proof the same RTL ran on today's main. The site presents genuine expected-negative, failed, and missing evidence without changing PASS semantics.

## Published page responsibilities

The public site is an architecture and verification review surface, not an engineering decision log. Pages follow a consistent content model:

| Page | Primary presentation | Detailed references |
| --- | --- | --- |
| Overview | Canonical architecture image, design facts, verification snapshot | README, implementation boundaries |
| Topology | Network structure, peripheral attachment inventory, FlooNoC source links | Architecture contracts, network manifests |
| Chip architecture | Interactive subsystem/IP/router hierarchy and connectivity | RTL bindings and signal inventory |
| Fabric routes | Reachability, router path, interface parameters, qualified latency | Timing methodology and per-run evidence |
| Address map | Memory/CSR windows, register definitions, DDR4 device MR field catalog | Source RDL, CSR generation and firmware ABI |
| Test runs | Test intent, actual acceptance, observed transactions, logs and DDR MRS command values | Per-test reports and original CI artifacts |
| Documentation | Searchable, subject-grouped engineering guides | Source-linked original Markdown |
| Source data | Downloadable architecture, generated RTL and regression configuration | Raw JSON, Bender and pinned source inputs |

Present **what exists and what is measured** directly in diagrams and tables. Move design decisions, unsupported-case explanations and procedure details to engineering docs. Keep brief, precise scope distinctions visible when a source/model view could otherwise be mistaken for verified hardware. Never copy historical measurements, simulation traffic or PASS/FAIL evidence into an architecture summary.

## Source-verified standalone protocol captures

Any test workflow uploading a versioned `protocol-transactions.json` is
auto-discovered alongside canonical regression archives. This applies to
PCIe configuration/enumeration, DDR/DFI mode-register commands, Ethernet
frames and future protocols with no new page-specific code. Real observations
appear in **Test runs → Observed protocol transactions**, including their
original monitor, operation, source SHA, CI attempt and native fields.

A standalone link or controller capture with no authentic `result.json`
is labeled **OBSERVED — isolated capture only**. It must not be displayed as
a passed full-chip integration test, fabricated memory completion or a
source-verified latency across independent clocks. Every accepted trace is
validated against its exact CI run/attempt, clean checkout and trusted
main/merged-PR source; mismatches are quarantined with a visible note.
Unmerged PR observations remain in the GitHub Actions artifacts until a
trusted `main` publication exists. New protocol support must include
producer, workflow-artifact, collector, unified-view and negative-evidence
tests; a parser-only implementation is not complete.

## Timing and evidence boundaries

The AXI baseline records 10,000 ps (10 ns) simulation reference clocks where captured, **not** a physical device clock frequency. Raw ps timestamps, source SHA and per-route sample counts accompany measured min/average/max cycles. Read/write remain separate and dynamic per-plane stage columns show observed local/global/target boundaries. Router-internal cycles, standalone-controller timing and unavailable packet paths remain **unmeasured**. Individually computed minima/maxima generally do **not** add up to path minima/maxima; paired sample arithmetic means may.

A temporary PR merge SHA need not equal final squash-merge SHA. The collector authenticates tested PR-head ancestry and Git tree, and where supported fingerprints relevant RTL/configuration, Bender and simulation execution inputs. A documentation-only update may retain verified **execution-input-identical** measurements while preserving the original capture SHA; any changed execution input invalidates reuse. Never transplant a measurement from merely similar variants or substitute expected route budget for observed latency. Clock-domain normalization will require actual per-domain periods if asynchronous fabrics are added.

## CI collection and safety

The collector reads the **existing** regression/workflow catalogs, not an artifact-maintained allowlist. It accepts completed main CI or authenticated merged-PR runs, verifies exact tested run/attempt, clean source checkout, selected original plans, captured source hashes and the PR temporary-merge parent when applicable. Unmerged/unverifiable branches and expired captures are **not** promoted to PASS. It validates ZIP paths/symlinks, selected member limits and file digests, and republishes only known report/trace/filelist types. It **re-renders** HTML from trusted templates, never executes artifact-supplied HTML or trusts a fabricated result.

Source history is bounded by `config/publication.yaml` and provider artifact retention; Pages is **not archival storage**. A workflow with no target artifacts is workflow-only evidence. All new public report paths use
`runs/<simulator>/<config_target>/<testname>/<run_id>/report.html`; immutable old captures retain original historical URLs for comparison. [#139](https://github.com/r987r/xezim-hello-world/issues/139) owns eventual retirement of private legacy scratch/CI paths.

## Local preview and deployment

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest tests.test_publication tests.test_axi_report tests.test_fabric_report -v
python3 tools/publish_site.py                     # source-only offline preview
GH_TOKEN=... python3 tools/publish_site.py --collect  # authenticated CI artifacts
python3 -m http.server --directory .tools/pages-site 8000
```

Only the `main` deployment job has `pages:write` and runs live public HTTP post-deploy tests. A successful build/upload without a successful deployment or public checks is **not** a release PASS. The site is ignored under `.tools/pages-site/`, and the publication job copies `gen/` without editing it. For protocol-specific interpretation see [AXI reports](axi-run-reports.md), [protocol reports](protocol-run-reports.md) and [test flow](test-flow.md).
