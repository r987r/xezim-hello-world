# Agent instructions: Xezim SoC RTL and verification

Read this file before changing any RTL, configuration, generator, boot logic,
documentation, CI workflow, or generated diagram.

## Mission and non-negotiable boundaries

Build a **config-driven, hierarchical SoC** from reusable upstream RTL.
Prefer existing public AXI, SRAM, DMA, NoC, CPU, BFM and controller IP. Add
only small, explicit, reviewed glue needed for a real protocol boundary.
Never invent a custom bus fabric, SRAM or AXI VIP simply because it is easy.

**Do not claim the full SoC is running from a scoped NoC BFM pass**: `fabrics.global_data.backend: floonoc`
in `config/soc.yaml` denotes selected architecture only. The current
`tools/noc_backends.py` has `floonoc.executable=False` and likewise
`pulp_axi.executable=False`. `gen/chip/soc_top.sv` is now an actual **chip boot configuration** with
real CPUs, the shared NoCs, upstream AXI adapters, SRAM, reset registers
and AXI memory stand-ins. Real iDMA/CSRs and physical controllers remain
unintegrated. The generic backend flag still does not describe a complete
arbitrary-configuration SoC emitter. Legacy memory/boot benches remain
independent executable scopes. Read [implementation-status](docs/implementation-status.md)
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
   `tools/noc_diagrams.py`, `tools/diagram_svg.py`,
   `tools/generate.py`: boot, neutral graphs and diagrams.
   `tools/noc_diagrams.py` reads **actual generated** FlooGen YAML and
   manifest for every mesh; it produces one complete SoC/FlooNoC SVG preview, one Mermaid source, and Diagram-gen-style JSON
   (`gen/diagrams/noc-topology.json`). The local router-router/NI
   edges are **generated structural RTL**; the shared `gen/supernoc/soc_noc.sv` connects the networks.
   `gen/chip/soc_top.sv` adds real CPU/SRAM/reset attachments and a target
   crossbar with AXI memory stand-ins. iDMA/CSR and physical-controller
   links remain planned. `make dv-supernoc` is the independent BFM gate;
   `make dv-chip` proves the CPU boot configuration.
   FlooNoC does not directly render Diagram-gen; use our generated
   Diagram-gen-style instance/connection/group metadata, and avoid
   inventing router positions or claiming a 3D viewer integration test
   that has not actually run.
   Do not fabricate topology in the diagram generator; do not edit
   generated outputs manually.
5. Every local/global data/config FlooNoC is GENERATED into tracked
   `gen/noc/floonoc/{instance}/` from `config/soc.yaml` and the
   `config/interface_contracts.yaml` native hardware parameter budget.
   `tools/floonoc_gen.py` emits upstream FlooGen profiles, structural
   Verilog tops, package files and a manifest; no custom router RTL. The
   upstream Bender dependency graph supplies implementation modules.
   `make gen` requires pinned upstream FlooGen installed first (see below).
   Source files in `config/floogen/` were removed to avoid duplicate
   manually maintained topology.
6. `gen/` is exclusively generator-owned and has a protective
   `.generated-root` marker. `make gen` replaces its complete tree,
   including deletions of stale diagram files. Never edit files under
   `gen/` manually. `README.md` contains one generated section between
   `BEGIN GENERATED SOC` and `END GENERATED SOC` comments. Edit the
   generator for content in that section.
7. **Exactly one generated architectural SVG:** `gen/diagrams/noc-hierarchy.svg`.
   Its Mermaid source and detailed router/endpoint JSON are retained for
   machines; **do not generate** separate per-mesh, boot, verification, CPU,
   memory or RTL-connectivity pictures. FlooGen's checked-in YAML/SV already
   provides drill-down. When the YAML changes, run `make gen`, confirm
   `gen/diagrams/` contains one SVG, and commit deletion of stale outputs.
   Review internal mesh router links as structural RTL. The single picture
   describes full-SoC endpoint integration; the NoC BFM wrapper and its
   route manifest provide separate executable cross-network wiring.
8. `make check-generated` is a nonmutating exact file-name/content/drift
   check, not a substitute for regenerating files. Keep generated `gen/`
   and the marked README section committed with a config/generator change.

## Reuse upstream config network IP

For both local/global configuration FlooNoCs, **AXI4 is the network's
physical transport and AXI4-Lite remains the CSR-facing protocol**.
Use pinned PULP `axi_lite_to_axi` and `axi_to_axi_lite` upstream
adapters, never a custom bridge. See
[docs/axi-lite-over-floonoc.md](docs/axi-lite-over-floonoc.md) and the
upstream PULP AXI bridge tests. For every NoC, review checked-in
`gen/noc/floonoc/manifest.json`, `floogen.yaml`,
`floo_xezim_*_noc.sv` and `*_pkg.sv` rather than a CI-only archive.
Commit generated outputs alongside their input config. A checked-in
NoC is **structural RTL** until actual upstream dependency compilation,
elaboration and request/response traffic pass; the evidence must remain scope-specific. The generic backend stays
non-executable until a general complete SoC emitter exists; the scoped
NoC and chip boot tests already execute real traffic.

## Linkable interface sizing gate

Run `python3 tools/interface_contracts.py` and
`python3 -m unittest tests.test_interface_contracts -v` when editing
AXI ports, FlooGen routing, local PULP AXI crossbars, DMA requests, or
outstanding transaction limits. `config/interface_contracts.yaml`
tracks planned per-fabric and per-subsystem read/write budgets, native
PULP/FlooNoC/Verilog AXI parameter targets, and per-port overrides.
FlooNoC chimney transaction caps are bound to generated RTL. The connected
BFM traffic baseline is verified; maximum configured capacities and every
parameter combination are not. CPU/reset hookups exist in the chip boot scope; real iDMA/CSRs remain pending.
Check that configured compute local output ID width is input ID width
plus ceil(log2(CPU/DMA initiator count)), and that global FlooGen input IDs agree.
Never mistake planned quotas for implemented capacity or FlooGen emission
for simulated NoC traffic.

## Run locally (no Rust rebuild)

Prerequisites: Python 3, git, GitHub CLI authenticated for this repo (or
an already downloaded simulator), compatible Linux x86_64 host.

```bash
python3 -m pip install -r requirements.txt
python3 tools/ip_fetch.py floonoc
python3 -m pip install -e .tools/floonoc
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
make dv-chip
BOOT_WAVE=1 BOOT_TRACE=1 make dv-boot
make test
```

`make test` runs all tests declared in `config/regression.yaml`, including
full/sparse memory profiles, relocated cold boot, diagnostics and both
simulator paths. It requires Bender 0.32.1, Verilator and pinned cocotb
libraries as described in [docs/regression.md](docs/regression.md).
`make test-xezim` and `make test-noc` select the blocking CI scopes. A green
unit-test suite by itself **does not** prove new RTL integration.

`tools/regress.py` resolves `XEZIM_BIN` or a cached binary and standard
Bender source sets. `Bender.yml` owns source ordering;
`config/regression.yaml` owns tests/variants/suites and acceptance rules.
`tools/ip_fetch.py` fetches pinned third-party RTL on demand to
ignored `.tools/`. No `cargo build` or recompilation of Xezim for
normal RTL edits. Simulator releases are built separately in
`.github/workflows/publish-xezim.yml`.

## Two-simulator strategy

Retain **both Xezim 0.11.4 and Verilator**, without a custom RTL clone.
The default `.github/workflows/dv-soc.yml` downloads checksum-verified
Xezim and executes the existing CPU boot, SRAM and AXI crossbar
transaction regressions. The independent
`.github/workflows/floonoc-elab.yml` downloads immutable FlooNoC
and its upstream Bender.lock dependency tree, then **elaborates all
eight FlooGen-generated local/global meshes with Verilator**, then runs
the connected super-NoC traffic and corruption checks. These are different
verification gates from Xezim CPU/memory simulation; report them separately.
**All eight generated local and global FlooNoC meshes now also
compile with pinned Xezim 0.11.4** using
`python3 tools/regress.py compatibility` and the *same upstream Bender
filelist* as the Verilator elaboration gate. The runner discovers its
tops from `gen/noc/floonoc/manifest.json` so a new subsystem scales
without editing hardcoded lists.
**Xezim reports potentially significant RoB/FIFO port width warnings
in all four DATA networks**, even though the compilation exits zero;
Verilator emits other upstream width warnings. Read and maintain
[docs/simulator-compatibility.md](docs/simulator-compatibility.md)
before making any simulator workaround. The Xezim compile stage is
separately logged and can be nonblocking until real traffic is tested.
Use both tool diagnostics to isolate simulator issues and run actual
AXI transaction tests with each simulator as their support permits.
Do not count elaboration or compilation as successful AXI traffic.
Avoid adding a new micro-testbench for every bridge or router.

## Native NoC atomic-ID reservation (critical)

The selected data/control interfaces do not issue AXI atomic operations.
`config/interface_contracts.yaml` pins `AtopSupport: false` and
`MaxAtomicTxns: 0` for **every** FlooNoC chimney through generated
native parameters, leaving MaxUniqueIds at 4 (data) and 2 (config).
Without disabling default atomic-ID reservation, real Verilator RTL
simulation fails `floo_meta_buffer.sv:142 TooFewIdBits2` at time zero.
Do not mask the assertion or shrink the outstanding-ID budgets to evade it.
Any change must maintain pinned upstream `NoAtomicTxns`,
`TooFewIdBits1`, `TooFewIdBits2` and readback regressions.
See [docs/supernoc-verification.md](docs/supernoc-verification.md).

## One unified super-NoC traffic test

`tools/supernoc_gen.py` generates shared `gen/supernoc/soc_noc.sv`
and one thin `supernoc_tb.sv` BFM wrapper from the real FlooGen profiles.
Both the BFM wrapper and chip boot top instantiate the shared core; it uses only packed AXI4
struct-to-flat-port assignments and true upstream FlooNoC modules.
`dv/supernoc/test_supernoc.py` uses mature third-party
`cocotbext-axi` `AxiMaster` and `AxiSlave` with mapped upstream
`AddressSpace`/`SparseMemoryRegion` storage rather than custom AXI BFMs or new per-router testbenches. Run `make dv-supernoc`; the shared runner performs the pinned Bender
checkout (see `.github/workflows/floonoc-elab.yml`).
**Do not claim the super-NoC is working from a compile-only result.**
A successful result must include all mapped routes, intended destination
storage, bursts/byte strobes, concurrent reused IDs, five-channel stalls,
and routed SLVERR checks with test logs. The required corruption run must
fail with its exact named mismatch. Never accept a generic compile exit
or an empty cocotb results file. Boot routing reads use seeded BFMs only;
the independent CPU cold-boot SRAM must stay uninitialized. Xezim remains the
independent structural compile and existing boot/memory simulation path.
PULP `axi_test.sv` classes were explored but Verilator 5.020 cannot
parse some upstream class/randomize constructs; do not fork them as a
workaround. For future UVM verification, evaluate pinned upstream AXI
VIP with real sequence/driver/monitor tests instead of reinventing one.

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

Primary verification scopes: compute0, compute1, memory0, global_data
NoC, global_config NoC, and soc_top. Avoid new per-bridge/SRAM/router
testbench proliferation. See docs/subsystem-verification.md.

The chip boot configuration uses the same generated NoC assembly as
the BFM scope. See [docs/full-chip-boot.md](docs/full-chip-boot.md) for the
CPU0 init/run/check mailbox contract, upstream WB/AXI bridges, AXI memory
stand-ins, negative missing-CPU check and simulator limits. Firmware must
execute on the real CPUs; the host never drives CPU result mailboxes.
Next actual integration work: real PULP iDMA/CSR/interrupt hookups, a
portable C runtime/BSP when required, and Xezim chip-level functional traffic. Preserve the existing bus-driven cold-boot proof. HBM/DDR
controller/PHY integration is a separate stage.
