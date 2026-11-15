# Add another SoC project

This workflow scales source selection, CI and Pages without adding
project IDs to the publisher, CI YAML matrix or a second simulator
framework. Begin with an already-supported architectural shape; the
current hardware composer is **not** a general automatic RTL generator
for every arbitrary subsystem, clock or IP combination.

## Author a new configuration

1. Copy an existing supported `soc.yaml` into
   `config/projects/<new-id>/soc.yaml` and give the
   source's `name` the same unique identifier.
2. Adjust subsystems, memory targets, addresses, boot and FlooNoC links.
   Keep address windows unique and every initiator/target routed. Use
   supported CPU/IP and NoC adapters only; fail closed on unsupported IPs.
3. Add one entry in `config/projects/catalog.yaml`:
   `id`, human title, subtitle, config path, and
   `qualification: source_contract_only`. Do not give
   a source-only design an imaginary generated top path.
4. Run catalog source validation and negative topology tests.
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

## Report and webpage policy

Project pages should show architecture and actual results, with no
project-specific branch logic in shared HTML templates. The file page
links checked-in selected RTL directly; for CI-generated RTL it points
to source-qualified GitHub Actions artifacts with the selected top,
NoC wrapper, filelist and compiler logs. Never reuse the original
project's pass/fail counts for a new design.

See [multi-project platform](multi-project-pages.md),
[repository map](repository-map.md), and [publication provenance](publication.md).
