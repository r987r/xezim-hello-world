# Declarative build and regression

`Bender.yml` is the ordered RTL source definition. `config/regression.yaml`
selects tests, simulators, configuration variants, timeouts, acceptance
markers and suites. `tools/regress.py` is the single entry point used by
Make and CI. Per-test shell runners have been removed.
The connected NoC tests use explicit cocotb seed `1`, recorded in each plan/XML.

## Upstream conventions reviewed

| Project/tool | Existing convention | Decision here |
| --- | --- | --- |
| [Bender](https://pulp-platform.github.io/bender/workflow/scripts.html), [FlooNoC](https://github.com/pulp-platform/FlooNoC/blob/05368bdff914f91a48b47c4ceddfc6ff266c6b3a/Bender.yml) | YAML source groups and targets; ordered filelists with includes/defines; dependency lock | Use standard Bender manifests and `flist-plus` for both simulators |
| [Xezim CLI](https://github.com/aionhw/xezim/blob/main/docs/command-line.md), [Xezim CI](https://github.com/aionhw/xezim/blob/main/.github/workflows/test.yml) | Native `-f` filelists; simulator implementation regressions run through Cargo | Use the released simulator and native filelists; do not copy simulator-development tests or rebuild Rust |
| [Ibex/RISC-V DV](https://github.com/lowRISC/ibex/blob/master/dv/uvm/core_ibex/riscv_dv_extension/testlist.yaml) | Readable YAML test lists, shared options, named tests | Adopt declarative tests/suites and YAML anchors; no UVM or ISA-randomization claim |
| [FuseSoC CAPI2](https://fusesoc.readthedocs.io/en/stable/user/build_system/core_files.html), [Edalize tools](https://edalize.readthedocs.io/en/latest/edam/api.html) | YAML reusable cores/filesets/targets and multi-tool flows | Useful future synthesis/platform option. The reviewed tool list has no Xezim backend; introducing one and a second dependency resolver is unnecessary for the current scopes |

The regression YAML is a **small project-specific schema**, not a Bender,
FuseSoC or Xezim standard. Python only translates resolved targets into
native Xezim/Verilator commands and invokes upstream cocotb. Protocol
agents, routers, compiler and dependency resolution stay upstream.

## Setup and commands

Install Python dependencies, the pinned Xezim release (see AGENTS.md),
[Bender 0.32.1](https://github.com/pulp-platform/bender/releases/tag/v0.32.1)
and Verilator 5.020. Put Bender at `.tools/bin/bender`, set `BENDER_BIN`,
or use PATH. Verify the release archive's supplied SHA-256 before extraction;
the shared CI action `.github/actions/setup-bender/action.yml` does this.

```bash
python3 -m pip install -r requirements.txt
python3 tools/ip_fetch.py floonoc
python3 -m pip install -e .tools/floonoc
python3 -m pip install 'cocotb==1.9.2' 'cocotbext-axi==0.1.24'
make gen
make test-list
make test                    # unit/drift checks + every declared simulation/probe
make test-xezim              # all memory profiles, SERV, SRAM, default/relocated boot
make test-noc                # all configured meshes + connected traffic + corruption
python3 tools/regress.py compatibility  # Xezim structural NoC compilation only
```

Individual targets retain existing Make aliases, such as `make dv-boot`
and `make dv-memory`. `AXI_CONFIG=... make dv-memory` still selects an
additional memory profile. `make dv-cpu` is a request-only diagnostic;
it and the arithmetic smoke are included in `full` and CI diagnostics,
without substituting for real CPU execution.

| Suite | Declared work |
| --- | --- |
| `xezim` | Memory default/full/sparse, named memory corruption failure, SRAM with/without `SYNTHESIS`, SERV execution, cold boot default/relocated |
| `noc` | Verilator elaboration of every configured network, one connected-NoC traffic test, named routed corruption failure |
| `compatibility` | Xezim compile-only probe of every configured network |
| `diagnostics` | CPU fetch request activity and arithmetic simulator smoke |
| `chip` | CPU-coordinated boot and AXI model readback, held-secondary negative, Xezim chip structural compilation |
| `full` | All suites above; schema validation rejects an uncovered declared test |

Every invocation checks generated-file drift before resolving RTL. The
root Bender source sets refer to IP fetched at `config/ip.lock.yaml` pins.
FlooNoC is resolved separately using its immutable upstream Bender lock.
Its standalone NoC source exclusions are explicit in regression YAML;
they exclude uninstantiated SoC blocks and unsupported vendor pads.
The planned SoC PULP AXI revision is not mixed into that graph.

## Inspect filelists, build, then run

```bash
python3 tools/regress.py boot --stage files
python3 tools/regress.py noc-xezim --stage files
python3 tools/regress.py noc-verilator --network global_data
python3 tools/regress.py supernoc --stage build
python3 tools/regress.py supernoc --stage run
python3 tools/regress.py supernoc-negative
```

`--stage files` fetches/resolves sources without invoking a simulator.
Structural NoC probes emit a complete filelist for each network. The
network set and native chimney checks derive from the architecture and
generated manifest, without a hardcoded count of eight.

For Xezim, `--stage build` checks elaboration with `--compile`; normal
execution compiles and simulates in one invocation. Run-only is explicitly
unsupported for Xezim. Cocotb supports separate build/run stages. Reusing
its Verilator executable requires a matching fingerprint of ordered
sources, headers, defines, options, simulator/cocotb versions, and the
built executable's hash. Changed RTL or a missing build is rejected.
Python stimulus can be rerun without rebuilding unchanged RTL.

Results live in `.tools/regression/<target>/`: `sources.f`, per-network
filelists, `plan.json`, transcripts, `result.json`, cocotb `results.xml`,
separate cocotb `build.log`/`simulation.log`, and generated variant inputs/
firmware where relevant. Each attempt replaces
that target's previous outputs. CI retains these artifacts on success
and failure; preparation failures are failures even if no result is written.

The NoC/chip cocotb targets also enable passive AXI capture through their
YAML `report.axi` settings. Each produces a self-contained HTML explorer,
raw JSONL events and versioned transaction JSON, including negative runs.
See [AXI run reports](axi-run-reports.md) for completion timing, ID scope,
filters, capture coverage and downloadable CI artifacts.

Positive simulations require zero exit and an explicit final PASS marker.
Negative tests require a positive nonzero exit, the exact expected mismatch,
and no positive PASS marker. Compile errors, signals and wall-clock timeouts
cannot count as an expected failure. Cocotb additionally rejects empty,
skipped, failed or errored results. Each simulator subprocess has a finite wall-clock
timeout; the process group is killed on expiry.

The local `full` suite requires both simulators and fails on a compatibility
probe failure. CI keeps the Xezim NoC compile probe separately nonblocking
while its width warnings/functional compatibility remain under review;
the Verilator connected traffic, Xezim CPU/memory and full-chip workflow
are blocking. The full-chip workflow's Xezim chip compile target is required;
its status is distinct from the optional per-mesh NoC compatibility step.
Simulation success does not establish synthesis or full-SoC integration.
The SRAM registered-read guard fix is checked by `sram-synthesis`, which
runs the existing bench with `-D SYNTHESIS`; no technology synthesis is claimed.

## Add or scale work

Add ordered sources under a standard Bender target, then add a test entry
and suite membership in regression YAML. Reuse YAML anchors for profiles
with common source sets/options. No new shell script, CI test list or
Python test-name branch is needed for another existing-engine target.
New SoC meshes are discovered from generated manifests and checked against
the configuration. New simulator engines require a reviewed adapter.

Chip source lists use the `chip_boot` Bender target alongside the locked
NoC provider. `bender_targets` composes ordered root source sets after
generated NoC packages/tops; it replaces hardcoded wrapper paths.
`mode: compile` explicitly marks the Xezim chip structural target.
See [chip boot](full-chip-boot.md).

## Pinned PULP iDMA RTL bring-up

The `dma` suite is a separate **real Verilator/cocotb RTL** scope, not
software-only descriptor-vector validation and not a claim of full-chip DMA
integration. `make dv-dma` invokes the upstream-generated desc64 frontend and
`rw_axi` backend with PULP AXI join/mux against cocotbext-axi memory targets.
One 100-descriptor DDR transfer and one single-descriptor HBM transfer check
payload data, descriptor writeback, final interrupt and idle-before-reclaim.
The test's completion IRQ is combinational to AXI B-channel handshake and is
sampled once at a stable clock phase to avoid double-counting VPI edges.

`tools/idma_rtl.py` fetches only the pinned iDMA commit and uses upstream
MARIO + PeakRDL tools to generate the RTL into ignored `.tools/pulp_idma/target/rtl`.
The root Bender `dma` target lists those upstream sources in dependency order;
FlooNoC's pinned AXI/APB versions provide shared bus types. Existing `gen/`
NoC and cold-boot artifacts remain unchanged. Run the dedicated
`.github/workflows/dma.yml` action for complete compiler and simulation logs;
[successful 2026-11-04 head](https://github.com/r987r/xezim-hello-world/actions/runs/41860245485).
