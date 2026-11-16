# Multi-project platform: Pages, build and evidence ownership

The [verification site](https://r987r.github.io/xezim-hello-world/)
opens with a **project picker**. Each project has its own architecture,
addresses, selected top-RTL file browser, and test-result ledger.
`config/projects/catalog.yaml` is the sole project inventory.
The site and CI matrix enumerate the catalog; no project IDs or project count
are hardcoded in the navigation or matrix implementation.

## Project-owned versus shared

Every project owns a unique configuration path, SoC `name`,
source SHA-256 fingerprint, selected build output, and test-evidence identity.
Shared resources include pinned IP, FlooGen, the NoC/full-chip emitters,
Bender resolver, Verilator, common test framework, protocol monitors,
evidence validation, and the sole Pages publisher. Do **not** copy these
per project.

Pages routes are stable:
- `index.html` is the project picker.
- `projects/<id>/index.html` is that project's overview.
- `projects/<id>/architecture.html` is its searchable hierarchy entry point.
  A project may opt into its own fully generated/parsed explorer using the
  validated `architecture_explorer` catalog field. Only Project A currently
  owns the legacy `explorer.html`. All other designs use the same
  searchable, breadcrumbs-based source hierarchy; they never inherit
  another project's RTL modules, routers, or traffic data.
- `projects/<id>/address-map.html` is its address map.
- `projects/<id>/files.html` indexes top RTL, NoC, filelist,
  manifests, boot products and their real source location.
- `projects/<id>/runs.html` admits only project-qualified runs.
- `projects/<id>/data/project.json` provides source hashes, file locations
  and test provenance for tools.

The original SoC's historical `soc-overview.html`,
`topology.html`, `explorer.html`,
`fabric.html`, `address-map.html` and
`runs.html` URLs remain valid; old run-report deep links stay
available. An untagged legacy run is never assigned to a newly added project.

## Generated files: which output should I inspect?

**Default hierarchical SoC:** `make gen` writes tracked
`gen/chip/soc_top.sv`,
`gen/supernoc/soc_noc.sv`,
`gen/noc/floonoc/manifest.json` and firmware under `gen/chip/`.
The tracked `gen/projects/xezim_soc_dv/variants/default/rtl/soc_top.sv`
is an **identical review copy**, not another physical chip.
`make check-generated` requires byte-exact regeneration and removes stale
generator-owned paths on `make gen`. This canonical tree is never overwritten
by another project's generation.

**Other compiled projects:** `tools/project_build.py` emits the
selected generated RTL under `.tools/projects/<id>/`:
`chip/soc_top.sv`, `chip/full_chip_tb.sv`,
`supernoc/soc_noc.sv`,
`noc/floonoc/manifest.json`, firmware and manifests.
`tools/project_compile.py` appends `chip/sources.f`,
`chip/compile-result.json`, and `chip/compile.log`.
These paths are **build artifacts**, not tracked RTL and not copied into
static Pages. Open the project's **RTL & files** page and follow the
catalog-selected GitHub Actions compile job to retrieve the matching run's
artifact `project-compile-<id>-<run_id>`.
The files page labels published files versus archived CI artifacts.

## Generate, compile and inspect independently

```sh
python3 tools/project_catalog.py --ids
python3 tools/project_catalog.py --matrix
python3 tools/project_build.py --project xezim_soc_dv --full-chip
python3 tools/project_build.py --project xezim_soc_dv --full-chip --check
python3 tools/project_compile.py --project xezim_soc_dv
python3 tools/project_build.py --project xezim_ethernet_cpu_ddr_pcie --full-chip
python3 tools/project_build.py --project xezim_ethernet_cpu_ddr_pcie --full-chip --check
python3 tools/project_compile.py --project xezim_ethernet_cpu_ddr_pcie
```

Install pinned tools/IP as in `.github/workflows/project-compile.yml`
first. Verilator lint/elaboration **and C++ model-object build** are
required for a compile PASS, and neither implies executed RTL behavior.
The catalog-driven CI matrix uses bounded parallelism rather than an
unbounded ten-job burst. A failing project does not hide behind a passing one.

## Source/RTL/behavior qualification ladder

1. **Configuration only**: schema validated; no generated hardware claimed.
2. **CI compiled**: selected Bender filelist and actual FlooGen/CPU/SoC RTL
   generated, repeat-checked, elaborated and C++ compiled with logs.
3. **Functional PASS**: project-specific immutable run identity, actual
   executed stimuli, passive AXI/TLP/GMII/DFI observations as applicable,
   expected byte-level results, and accepted completions.
4. **Real controller/PHY qualified**: separate selected-IP regression,
   not inferred from modeled DDR or a top-level source file.

Project A has independently verified functional tests on its selected
variants. Project B is at **compiled** status; Ethernet, PCIe and DDR
active-variant integration and bytes-checked through-routing are still
pending. Its run page remains empty, not green.

To add a project, follow [project onboarding](project-onboarding.md).
Ten-project tests exercise catalog enumeration, independent source
fingerprints, page routing, and evidence isolation using ten source
fixtures. They **do not** pretend that ten hardware designs were compiled.

## CI and release

The Pages workflow builds project pages from the catalog on PRs,
runs unit and desktop/mobile browser checks, and deploys only from
a trusted `main` run. The project compile workflow derives
its matrix from the catalog with `max-parallel: 3` and
uploads each selected RTL/filelist under its own artifact.
The publisher must not infer PASS from a compiled design, a schematic,
a reused baseline capture, or an untagged historical run.

The original project retains its normal regressions. A new project
requires an explicit qualified test target/run identity before it can
populate its own Test Runs page.

## Hierarchy restoration and future projects

The original chip's **Architecture** navigation opens its complete existing
interactive `explorer.html` (subsystems → IP → NoC → routers and interfaces),
including controls, RTL bindings, signals and evidence. The reduced region
sketch was removed from the multi-project publisher. The generic
`site_project_hierarchy.html` renderer instead consumes each project's
own `soc.yaml` subsystem, IP, fabric, network/link, bus and memory contracts.
It supports search, breadcrumbs and click-through, but does not pretend to
know RTL router instances or signal bindings until an actual project-specific
compiler-parsed explorer is published.

To enable richer RTL drill-down for additional compiled projects, generate a
source-qualified explorer for *that project* and register its own relative
`architecture_explorer` URL in the catalog. The publisher rejects missing
or duplicate explorer ownership. A compiled top alone is insufficient for
router-/signal-level claims.

The per-project `--check` generation gate remains byte-exact for all
emitter-owned output; subsequent known Verilator `sources.f`, compile logs,
result metadata and `obj_dir/` files are permitted without reading their
large object-file contents or calling them stale generated RTL.

## One topology/architecture UI for every project

Every `projects/<id>/architecture.html` uses the same
`tools/templates/site_project_hierarchy.html` shell, with the shared
`site_project_topology.js` diagram. It displays subsystem cards and
data/control connections sourced from that project's validated `soc.yaml`.
The viewer can use optional `layout.regions` for column placement; without
hints it derives layers from the adjacency graph, not chip-specific names.
It has the same search, breadcrumb drill-down, zoom/fit, connection filters,
inspector and selected-file links for every catalog entry.

The existing `explorer.html` with compiler-parsed RTL/router/signal detail
is an **additional** catalog-owned drill-down, not an alternative main
Architecture page. The project-level graph remains declared connectivity
until a selected project publishes its own parsed elaboration evidence.
An unqualified design receives no other project's RTL details or traffic.

## Restored visual drill-down for every project

The same selected-project `architecture.html` draws multiple *visual*
levels: whole-chip connections and summaries; subsystem composition with
CPU/IP, DMA, mapped SRAM/memory targets and local NoCs; actual
FlooGen-declared NoC router grids and named NIs; then router/NI details.
Click a diagram block to move deeper and use its visual breadcrumbs to
return to the chip. The searchable side hierarchy uses the same component
identities and selection state, and the AXI data/control filter continues
to apply at the chip level. There are no project-name-specific layout rules.

FlooGen profiles are obtained from the shared hardware profile builder in
`tools/floonoc_gen.py` using each project's own `soc.yaml` and shared
`interface_contracts.yaml`. Physical NoC router counts and named network
interfaces are source-profile declarations, **not** proof of elaborated
RTL, connectivity through conditional generates, or simulation traffic.
The original separately parsed RTL explorer is still linked as *optional*
additional evidence only for its owning project; Project B must get its own
parser artifact before it can make identical RTL-internal claims.

Browser CI must click **chip → subsystem → FlooNoC → router** for each
cataloged project and confirm the displayed NoC and NI data belong to the
selected SoC. This prevents a future update from silently reverting to
one flat box per subsystem.

## 2026-11-16 visual visibility audit

Browser tests previously checked the existence and clickability of nested
SVG rectangles but missed basic usability: project-specific scope and search
pushed the diagram below the initial screen on desktop, and a fixed 470px
nested scroll container clipped the mobile component view. The architecture
page now renders its topology **before** source/search explanations; the
selected project qualification disclaimer follows the graph. At mobile
widths, subsystem composition expands to the full natural diagram height
and uses page scrolling, while long headings are abbreviated to the canvas
width. Going back to the chip restores standard overview sizing.

The browser gate checks that nested boxes start within the first viewport,
that mobile NoC cards and headers fit horizontally, and that the full
composition is not vertically hidden behind a nested scroll region.
Subnetwork IP-to-NoC dashed lines are name-matched source hints, **not**
port-level RTL connectivity proof. This is consistent with keeping
compiler-parsed RTL and passive AXI/TLP data evidence separately qualified.
