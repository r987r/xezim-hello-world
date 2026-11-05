# Slang RTL lint inventory (report-only rollout)

CI workflow: [Slang RTL lint and elaboration inventory](../.github/workflows/slang-lint.yml).

This independent job uses checksum-pinned official slang **v12.1** (see
[version lock](../toolchains/slang.env)), the repository's existing
Bender filelist resolver and the same upstream FlooNoC/iDMA source pins as
regression. The lint inventory is independent of the Xezim simulator.

## Policy

- Initial **report-only** policy applies to RTL diagnostics. Existing design
  errors are recorded in artifacts and PR annotations. They do not prevent
  a separate cleanup PR from progressing.
- A missing tool, missing source plan, broken/unknown diagnostics JSON,
  crash or timeout **fails** the lint workflow.
- Once the baseline is investigated, activate the optional `--enforce`
  switch to gate on design errors. Warning policy can later become stricter
  through reviewed waivers/baselines.
- Both slang `--lint-only` (translation-unit lint) and normal full
  elaboration are run for each positive regression profile. Lint-only alone
  does **not** prove hierarchy connectivity.
- Do not conflate a successful lint job with zero RTL errors. Read
  `.tools/lint/summary.json` and the individual reports.

## Profiles and reproducible commands

The profile inventory comes from `config/regression.yaml`: positive,
elaboratable NoC/chip targets with full test top names. Current set includes
`supernoc`, `dma-rtl`, `chip-dma`, and `chip-boot`. Newly registered
positive profiles become available automatically.

~~~sh
python3 tools/lint_rtl.py --list

# With pinned Bender, generator dependencies and slang installed:
python3 tools/regress.py supernoc dma-rtl chip-dma chip-boot --stage files
python3 tools/lint_rtl.py --slang .tools/bin/slang
python3 tools/lint_rtl.py --slang .tools/bin/slang --enforce
~~~

Each profile produces `lint.raw.json`, `lint.log`, `elaborate.raw.json`,
`elaborate.log`, and `report.json`; the overall inventory is
`summary.json`. Each finding records severity, code, message, source
location, symbol path when available, and whether its source is within
vendor RTL or project RTL. The artifact also retains `sources.f` and
`plan.json` so a cleanup PR can reproduce problems exactly.

## Parallel issue cleanup

Start with **project RTL errors**, then generator bugs, then upstream RTL
diagnostics, each grouped by code and source file. Prefer correct fixes,
not broad suppression. Keep warning waivers precise and documented. After
the inventory is reviewed and stable, switch the lint job to enforce
errors on every changed positive test profile.

This job is a **separate PR-only/manual workflow** and does not alter the
existing `full-chip`, `floonoc-elab`, or main-only Pages publication
scheduling. Its artifacts are not automatically published as a separate
Pages branch site.
