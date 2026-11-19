# Add another SoC project

This workflow scales source selection, CI and Pages without adding
project IDs to the publisher, CI YAML matrix or a second simulator
framework. Begin with an already-supported architectural shape; the
current hardware composer is **not** a general automatic RTL generator
for every arbitrary subsystem, clock or IP combination.

## Author a new configuration

1. Start from an existing supported SoC via the source-only scaffolder:

   ```sh
   python3 tools/project_scaffold.py --id chip_third \
     --from-project xezim_ethernet_cpu_ddr_pcie \
     --title 'Third chip' --subtitle 'New chip configuration'
   ```

   This creates `config/projects/chip_third/soc.yaml` and registers it with
   `qualification: source_contract_only`. The copied shape is a starting
   point, **not** evidence of a new design or an RTL qualification.
2. Adjust subsystems, memory targets, addresses, boot and FlooNoC links.
   Keep address windows unique and every initiator/target routed. Use
   supported CPU/IP and NoC adapters only; fail closed on unsupported IPs.
3. The scaffolder adds the catalog entry; do not add project IDs to CI or
   the shared architecture viewer. Do not give a source-only design an
   imaginary generated top path.
4. Run catalog source validation and negative topology tests, including
   `python3 -m unittest tests.test_third_project_onboarding -v`.
   Verify the new chip changes actual connectivity/addresses/composition,
   not just the name of a copied configuration.
5. Generate selected boot/memory RTL, then `--full-chip` if
   the chosen composition is supported. Compile with shared pinned
   FlooGen/Bender/Verilator; only then promote its catalog qualification
   to `ci_generated_compiled`.
6. Add real project-qualified functional scenarios and passive monitor
   evidence before publishing any PASS result for that project.

Example commands (replace the ID):

```sh
python3 tools/project_catalog.py --ids
python3 tools/project_catalog.py --matrix
python3 tools/project_build.py --project new_chip --full-chip
python3 tools/project_build.py --project new_chip --full-chip --check
python3 tools/project_compile.py --project new_chip
python3 -m unittest tests.test_multi_project_site -v
```

## What scales automatically?

The catalog renders every project card and distinct architecture,
address-map, files and run views. The shared compile workflow resolves a
dynamic matrix with bounded parallel jobs; it never requires a hardcoded
two-project enumeration. Per-project `.tools/projects/<id>`
contains full source-selection logs and output hashes. Existing
`gen/` stays the default generated tree.

Unit tests use ten **source-config fixtures** to verify catalog scale,
site navigation, unique hashes, and no cross-project test evidence;
this tests metadata/platform capacity, not compiled hardware capacity.
Individual designs must still pass real selected compilation and
functional verification. A new unsupported IP/clock/CPU topology
requires work in the shared IP-composition and backend adapters,
and its own tests—not just a catalog row.

## Architecture explorer ownership

Each project owns its source hierarchy; the project picker, searchable
subsystem/IP/fabric/network tree and file browser require no hardcoded
project names. Only register `architecture_explorer: path/to/explorer.html`
when that exact project publishes a real generated topology/RTL explorer.
This URL must be unique and present in the website output. Compiled-only
projects continue using the generic searchable source hierarchy until
that source-qualified artifact exists. The original project's complete
`explorer.html` is explicitly owned by its catalog entry, not reused for
another chip.

## Report and webpage policy

Project pages should show architecture and actual results, with no
project-specific branch logic in shared HTML templates. The file page
links checked-in selected RTL directly; for CI-generated RTL it points
to source-qualified GitHub Actions artifacts with the selected top,
NoC wrapper, filelist and compiler logs. Never reuse the original
project's pass/fail counts for a new design.

See [multi-project platform](multi-project-pages.md),
[repository map](repository-map.md), and [publication provenance](publication.md).

## Third-design scalability gate

The shared source-IR workflow loops over **every** catalog ID for source-selected
boot/memory generation and exact regeneration checks; it no longer enumerates
the two originals. The website's same topology and nested composition viewer
is reused for a structurally different third-source fixture (five direct
neighbor links rather than four, and a different region layout). The compiled
RTL matrix remains gated by qualification and must not silently count a
source-only third project as compiled or functionally passed.

This does **not** remove the current hardware boundaries: one memory subsystem,
supported PicoRV32/SERV boot shapes, pinned peripheral adapters, and supported
NoC protocols. Extending the configuration to a new hardware shape must update
and test the relevant shared generator. The source-only browser test is not
Verilator, real AXI routing, or traffic qualification.
