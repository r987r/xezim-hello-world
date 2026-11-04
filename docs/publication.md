# GitHub Pages verification hub

The repository publishes its current README, documentation, canonical topology,
generated RTL/configuration, regression catalog and actual main-branch CI results
through `.github/workflows/pages.yml`. The deployed URL is recorded by the
`github-pages` environment in that workflow. GitHub Pages uses the **GitHub
Actions** publishing source; `tools/publish_site.py --ensure-pages` selects it
for an already enabled site using the deployment job's `pages: write` token.

## What is published

- Overview: implementation limits, latest workflow status and the same generated
  `gen/diagrams/noc-hierarchy.svg` used by the README. No second architecture
  diagram is maintained.
- Topology: all generated local/global meshes, router/endpoint counts, upstream
  FlooGen YAML/SV and all distinct AXI observation boundaries.
- Test runs: recorded acceptance result, engine, tested SHA, workflow ID/attempt,
  logs, original build plan/filelists and cocotb XML where available. Positive,
  failed and required-negative results remain distinct.
- AXI reports: self-contained transaction table and completion timeline plus
  original transaction JSON and raw event JSONL. The current presentation template
  can render older data; no traffic or intent annotations are invented for it.
- Documentation and source data: every current repository Markdown document,
  generated source tree, architecture/regression/publication YAML and dependency
  locks. Implementation source links point to the site's immutable source SHA.

The current source SHA and every test's tested SHA are separate. A passing older
run never means newer source passed. A failed workflow without target artifacts
still appears in workflow history. Unavailable/expired evidence is reported as
missing, never converted into a pass. Reports show the regression's acceptance
result: a required-negative test passes only when its exact named failure occurs.

## Collection, retention and reproducibility

`config/publication.yaml` selects trusted producer workflows and artifact names,
history depth and archive size limits. Publication runs on main pushes, manual
dispatch and completion of the configured main workflows, including failures.
It collects up to four recent runs per workflow from the newest 500 repository
runs. Only artifacts from main are ingested. No pull-request source or artifact
is executed or deployed by a `workflow_run` event. PRs build an offline preview
and validate the publisher/report semantics without deployment privileges.

Artifacts retain their original workflow and attempt. Available SHA-256 archive
digests are checked; unsafe ZIP paths and symlinks are rejected. AXI report
commit, clean-worktree flag and workflow ID/attempt must match their CI run.
Only the explicit evidence file types are republished, not compiler object
directories. Pages history is rebuilt from still-available Actions artifacts;
it is **bounded history, not permanent archival storage**. Increase artifact
retention/history limits deliberately if long-term evidence is needed.

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest tests.test_publication tests.test_axi_report -v
python3 tools/publish_site.py                       # docs + offline preview
GH_TOKEN=... python3 tools/publish_site.py --collect # actual main CI evidence
python3 -m http.server --directory .tools/pages-site 8000
```

The generated site is ignored under `.tools/pages-site/`. `gen/` remains
generator-owned; publication copies it without changing it. Site links are
relative so project Pages URLs and nested report/document paths work.

## DMA names and expected errors

There are **zero active DMA engines in the default cold-boot mode**
(`DmaEnable=0`). The chip test temporarily drives compute0's otherwise
inactive DMA manager with the upstream verification BFM after CPU coordination.
A separate explicit `DmaEnable=1, DmaTestMode=1` configuration generates real
DMA engines and CSR bridges for both SS0 and SS1, and substitutes **CPU0 AXI BFM (data)** and **CPU0 AXI BFM (config)**
on CPU0's data/config NoC managers while the CPUs are held reset.
These are simulation initiators, never a PCIe host. Actor
metadata distinguishes these two test modes; a DMA simulation should
never be counted as a cold-boot or CPU-driver test.

Normal CPU boot expects OKAY. SLVERR checks are deliberate verification stimuli:
24 write/read pairs at injected faulty NoC targets, and four out-of-capacity
transactions across the two chip memory models. Each chip model implements only
64 KiB of its much larger architecture address window. The test declares the
exact initiator, address, operation and expected response **before** issuing it.
The report consumes that expectation once; any undeclared initiator error or
response mismatch fails monitored capture validation. Downstream error observations
remain observations because global IDs are remapped; they are not guessed to be
new expected or unexpected initiator requests. Legacy unannotated captures are
labeled as such and never retroactively classified as expected.

## Generated dual-DMA full-chip test scope

The `chip-dma` target uses the same generated NoC core and monitor catalog
as CPU boot, but runs with CPUs held in reset and a real PULP iDMA instance
at every compute DMA endpoint. **CPU0 AXI BFMs** use the CPU0 data/config AXI
interfaces only for memory preparation and CSR submission (not PCIe). The event table,
timing chart, result and source SHA are published from the full-chip CI
artifact when that regression actually executes. This is NOT evidence of
CPU-launched DMA firmware or physical DDR/HBM controller integration.
