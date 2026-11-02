# Agent instructions: Xezim SoC RTL and verification

Read this file before changing any RTL, configuration, generator, boot logic,
documentation, CI workflow, or generated diagram.

## Mission and non-negotiable boundaries

Build a **config-driven, hierarchical SoC** from reusable upstream RTL.
Prefer existing public AXI, SRAM, DMA, NoC, CPU, BFM and controller IP. Add
only small, explicit, reviewed glue needed for a real protocol boundary.
Never invent a custom bus fabric, SRAM or AXI VIP simply because it is easy.

**Do not claim FlooNoC is running**: `fabrics.global_data.backend: floonoc`
in `config/soc.yaml` denotes selected architecture only. The current
`tools/noc_backends.py` has `floonoc.executable=False` and likewise
`pulp_axi.executable=False`. There is **no full-chip soc_top**. The
Verilog-AXI crossbar testbench and two-core boot testbench are separate,
real executable *scopes*. Read [implementation-status](docs/implementation-status.md)
before describing progress.

Keep boot cold: CPU0 must really read ROM/flash, write **uninitialized**
SRAM over its bus, release CPU1 via MMIO, and both CPUs must execute code
from SRAM. Do not use $readmemh/backdoor SRAM preload in the cold-boot test.
Do not reintroduce Xezim 0.11.3 SERV part-select shims: the issue was
resolved in pinned Xezim 0.11.4 and the historical bug reproducer was removed from this SoC repo.

## Source of truth, generation, diagrams

1. `config/soc.yaml`: authoritative architecture, addresses, subsystem
   instances, fabric backend selections, verification scopes and boot policy.
   Examples under `config/examples/` are opt-in **DV variants**, not
   automatically part of the full-chip architecture.
2. `config/ip.lock.yaml`: immutable, licensed upstream commits. Never
   replace these with unpinned source files or silent third-party forks.
3. `tools/socgen.py`, `tools/noc_backends.py`, `tools/fabric_config.py`:
   config validation, actual RTL generation and backend capabilities.
4. `tools/bootgen.py`, `tools/diagram_gen.py`,
   `tools/diagram_svg.py`, `tools/generate.py`: boot, neutral graphs and
   diagrams. Change their input/config logic, **not** generated outputs.
5. `gen/` is exclusively generator-owned and has a protective
   `.generated-root` marker. `make gen` replaces its complete tree,
   including deletions of stale diagram files. Never edit files under
   `gen/` manually. `README.md` contains one generated section between
   `BEGIN GENERATED SOC` and `END GENERATED SOC` comments. Edit the
   generator for content in that section.
6. Every change affecting architecture, mapping, generator, or diagram
   content needs `make gen` and a review of ALL generated views:
   `architecture`, `rtl-connectivity`, `boot`, `verification`,
   `subsystems/compute0`, `subsystems/compute1`,
   `subsystems/memory0`. Additional subsystem diagrams must appear
   automatically; removed ones must disappear. SVG, Mermaid and graph JSON
   must agree with the emitted RTL and whether each link is *planned* or
   *actually exercised*.
7. `make check-generated` is a nonmutating exact file-name/content/drift
   check, not a substitute for regenerating files. Keep generated `gen/`
   and the marked README section committed with a config/generator change.

## Run locally (no Rust rebuild)

Prerequisites: Python 3, git, GitHub CLI authenticated for this repo (or
an already downloaded simulator), compatible Linux x86_64 host.

```bash
python3 -m pip install -r requirements.txt
source toolchains/xezim.env
mkdir -p .tools/bin
gh release download "$XEZIM_RELEASE_TAG" --repo r987r/xezim-hello-world \
  --pattern "$XEZIM_ASSET_NAME" \
  --pattern "$XEZIM_ASSET_NAME.sha256" --dir .tools/bin
(cd .tools/bin && sha256sum -c "$XEZIM_ASSET_NAME.sha256")
chmod +x ".tools/bin/$XEZIM_ASSET_NAME"
export XEZIM_BIN="$PWD/.tools/bin/$XEZIM_ASSET_NAME"

make gen
make check-generated
make check-config
make dv-memory
AXI_CONFIG=config/examples/memory-fabric-connectivity.yaml make dv-memory
AXI_CONFIG=config/examples/memory-fabric-sparse.yaml make dv-memory
make dv-memory-negative
make dv-sram
make dv-serv
BOOT_WAVE=1 BOOT_TRACE=1 make dv-boot
make test
```

`make test` is the tracked default config suite. The two
`AXI_CONFIG=...` variants are extra required runs for fabric changes:
the first proves all ingress-target pairs; the second proves allowed
pairs and denied read/write responses (AXI DECERR). A green unit-test
suite by itself **does not** prove new RTL integration.

`scripts/common.sh` resolves `XEZIM_BIN` or a cached binary.
`scripts/ip_fetch.py` fetches pinned third-party RTL on demand to
ignored `.tools/`. No `cargo build` or recompilation of Xezim for
normal RTL edits. Simulator releases are built separately in
`.github/workflows/publish-xezim.yml`.

## CI and debugging

- `.github/workflows/dv-soc.yml` runs on pushes and pull requests,
  installs dependencies, checks generator drift, downloads the pinned
  checksum-verified Xezim release, then runs the RTL suites including
  sparse/no-access checks and cold boot. A completed green GitHub
  Actions **SHA** is needed before merging; do not infer a pass from a
  started workflow.
- On errors, inspect the exact failing job/log and retained artifacts.
  `docs/boot-debug.md` gives SERV bring-up and VCD tools copied from
  the patterns of `r987r/Sv-test`.
- When local git network access is unavailable, use the GitHub
  integration to edit a feature branch and verify actual Actions logs.
  A green workflow for an *older* commit does not validate the current
  head. Do not claim an unavailable local simulation succeeded.
- For any new configured backend, first prove it emits *real upstream
  instantiated RTL*, compile/elaborate it, and run meaningful
  transactions across its inputs/outputs. Set `executable` only after
  that. No placeholder fabric or model pretending to be FlooNoC.
- Maintain independent scoreboards, negative tests, bounded timeouts,
  address/ID/order assertions, and route-coverage including denied paths.
  Distinguish RTL protocol simulation from real DDR/HBM controllers/PHY.

## Working style

Use a feature branch/PR, review source/verification contracts, test the
smallest isolated DUT first, run the full suite, and merge only a green
head. Keep the README's **planned vs actual** wording precise.
For schema extension, inherit type defaults -> subsystem defaults ->
instance overrides; validate every named port, width, direction, memory
window, source-ID budget and downstream reachability. Follow the
`r987r/Sv-test` YAML interface/UVC/provider ideas without copying
unnecessary custom verification RTL.

Primary verification scopes: compute0, compute1, memory0, global_data NoC, global_config NoC, soc_top. Avoid adding separate bridge/SRAM/router/logic unit TBs; retain existing smoke/boot/memory diagnostics only as regression gates. See docs/subsystem-verification.md and the pinned upstream FlooGen CI generator workflow.\n\nNext actual integration work: FlooGen real global data NoC, then PULP AXI compute-local emitter, tested
CPU-to-local-fabric/SRAM path, upstream iDMA frontend and 64-bit AXI
datapath, then FlooNoC through FlooGen. Real HBM/DDR controller/PHY
simulation is a **separate** integration stage.
