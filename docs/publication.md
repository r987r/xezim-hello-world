# GitHub Pages verification hub

The repository publishes its current README, documentation, canonical topology,
generated RTL/configuration, regression catalog and verified CI results
through `.github/workflows/pages.yml`. The deployed URL is recorded by the
`github-pages` environment in that workflow. GitHub Pages uses the **GitHub
Actions** publishing source; `tools/publish_site.py --ensure-pages` selects it
for an already enabled site using the deployment job's `pages: write` token.

## What is published

- Overview: implementation limits, latest workflow status and the same generated
  `gen/diagrams/noc-hierarchy.svg` used by the README. No second architecture
  diagram is maintained.
- Fabric Explorer: address-accurate initiator-to-target route table, AXI port inventory with planned outstanding budgets and physically generated XY router/link paths. Controlled one-beat RTL timings attach only to clean, complete serial traces from the exact published SHA, an identical verified Git tree, or verified identical RTL/simulation execution inputs from trusted CI. They decompose observed AXI mesh boundaries into request/return deltas and combined terminal service; internal router cycles and isolated HBM/DDR controller latency remain unmeasured. Older or stressed observations retain their original SHA and end-to-end-only scope.
- Mobile Fabric Explorer: at viewport widths up to 820 px, replace the wide
  route table with vertical source → target cards; their headers show total
  one-beat read/write min/average/max simulation cycles and sample counts.
  Expand a card to compare the local/global NoC and target-facing AXI stages
  with separate read/write values, then open the full XY router path and
  original CI evidence. Plane/search filters apply to both views, unreachable
  routes are hidden by default on mobile and can be included explicitly,
  and the interface inventory, address map and route detail tables become
  stacked labeled rows. Desktop retains the full comparative table.
  The responsive view is presentation-only and consumes the same publication
  dataset; it never changes latency calculations, source verification,
  generated RTL or simulator runs.
- Wide latency comparison: one source/destination row per route, with dynamic
  per-plane NoC columns (compute0, compute1, global, memory0 when present),
  terminal AXI read/write service and end-to-end read/write columns.
  Measured cells show **min / arithmetic average / max** in cycles of the
  **measured simulation reference clock period**, with sample count and
  exact CI-run SHA. Read and write remain separate even if they share a mesh
  cell. A dash means absent/not permitted; "unmeasured" means the route is
  present but lacks clean same-source or cryptographically verified identical-tree serial-baseline evidence. The 10 ns
  testbench clock is common across the current scopes, but the RTL hardware
  frequency is not configured or claimed. Underlying AXI captures retain each sample's raw picosecond
  timestamps for future clock-domain normalization.
  Even with one outstanding transaction, observed per-stage latencies can
  vary with response-ready phase, endpoint pipeline behavior and traffic
  conditions; min/avg/max describe measured samples, never a guarantee.
  The terminal service includes downstream memory crossbar/model delay,
  not standalone controller or physical memory timing.
  Stage minima and maxima are calculated independently and generally **do not
  sum** to end-to-end minima or maxima; paired-sample arithmetic means are
  additive. Each displayed n and tested SHA can be inspected in the original
  AXI trace. A temporary PR merge SHA can differ from the real main merge SHA;
  the publisher compares their exact Git tree objects and validates that the
  PR's tested commit was a genuine merged-PR head before treating measurements
  as equivalent. It never reattributes the original tested SHA.
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

## Current-RTL latency evidence and clock reference

The verified RTL equivalence fingerprint is derived from Git-authenticated blob IDs of every checked-in execution input (SoC config, generated NoC/AXI RTL and manifests, RTL models, BFM/AXI capture and clock code, simulator orchestration, pinned tool/dependency files and job execution steps). Documentation, report rendering and scheduling-only workflow updates do not invalidate measured RTL timing. A changed execution input invalidates reuse immediately. Exact tested SHAs, CI run IDs, raw ps timestamps and measured 10 ns simulation periods are preserved; a reused capture is labeled **verified current RTL inputs**, not portrayed as a newly executed test. This is a current-RTL functional equivalence check for the existing scope, not a proof about fabricated hardware or CDC. Relevant fabric report changes trigger the real super-NoC verification gate on PRs to main.

The shared single-clock simulation drives `clk_i`; the captured period is 10,000 ps (10 ns), corresponding to a **100 MHz simulation reference clock**. This value is measured in the AXI capture and displayed alongside min/average/max cycles, with original ps durations retained. No physical device clock frequency is asserted. When multiple clock domains are introduced, route timing must be normalized using the relevant observed period or common timebase before comparing path cycles.

### IP composition drill-down

Chip architecture blocks open the compiler-parsed RTL instance hierarchy, including repository-owned Ethernet datapath modules and CPU/DMA adapters. Nested parsed modules can be opened without generating a new static diagram. Pinned third-party IP and inactive opt-in variants appear as opaque/reserved boundaries unless their actual module sources were parsed; syntax presence alone does not prove elaborated or active hardware. Published source paths and test profile overlays remain independent of structural evidence.

## Collection, retention and reproducibility

The collector automatically discovers CI workflows that upload canonical `.tools/regression/` artifacts and their declared artifact names; new test targets require no publication allowlist edits. `config/regression.yaml` supplies the test catalog, while `config/publication.yaml` only sets retention and archive size limits. Every PR targeting `main` builds an
offline preview. After a PR merges, a minimally privileged PR-close job dispatches
one new Pages workflow on the actual `main` ref, so the GitHub Pages environment
permits deployment; that main-ref run builds and publishes the trusted `main`
checkout. Manual dispatch on `main` publishes as well; a manual feature-branch
dispatch builds a preview without deployment. No automatic branch push or
CI-completion triggers remain.

The collector discovers regression-producing workflows and standalone CI test
jobs from their checked-in GitHub Actions YAML. Tests without canonical
regression artifacts are represented as workflow-only evidence rather than
fabricated per-target PASS results. It independently paginates each workflow's run history,
retaining up to four trusted runs per producer by default. An explicit page
limit prevents unbounded history scans and reports any truncation; bursty
activity in other workflows cannot crowd out Ethernet, PCIe or DDR evidence. It accepts main-branch results and completed PR results
only when GitHub's merged-PR metadata matches **the exact tested source head SHA
and source branch**. GitHub may clear a workflow run's PR association after merge,
so the source SHA is checked against the merged PR directly. PR builds run on
GitHub's temporary merge commit, which differs from the PR head; for AXI
artifacts the publisher verifies the captured merge commit through GitHub's
commit API, requiring the exact PR head as its second parent, and retains the
actual tested merge SHA separately from the PR-head SHA. Unverifiable captures
are excluded with explicit notes, never silently accepted or promoted to PASS.
Unmerged branch artifacts are never published. Deployed code always comes from
`main`.

Artifacts retain their original workflow and attempt. Available SHA-256 archive
digests are checked; unsafe ZIP paths and symlinks are rejected. AXI report
commit, clean-worktree flag and workflow ID/attempt must match their CI run.
Only explicitly allowed result, trace, plan, log and filelist types are
extracted and republished; compiler object and precompiled-header files
are never imported from CI artifacts. The collector verifies full ZIP digests
and checks **every** member for unsafe paths/symlinks before selecting evidence.
A capped legacy ZIP allowance accommodates historical PCIe regression archives
that included huge reproducible Verilator build products. Future PCIe CI
archives upload only the canonical regression target directory. Expanded
limits are checked against selected files, without loosening source-SHA or
protocol provenance validation.

The Test Runs page shows every configured target in its catalog regardless of
whether a recorded result exists. A dynamically populated suite filter exposes
PCIe, Ethernet, memory, NoC, CPU/DMA and additional test families; clicking a
suite narrows recorded evidence and workflow history. A successful workflow
without a target result is workflow-only evidence, not an invented target PASS. Pages history is rebuilt from still-available Actions artifacts;
it is **bounded history, not permanent archival storage**. Increase artifact
retention/history limits deliberately if long-term evidence is needed.

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest tests.test_publication tests.test_axi_report tests.test_fabric_report -v
python3 tools/publish_site.py                       # docs + offline preview
GH_TOKEN=... python3 tools/publish_site.py --collect # actual main CI evidence
python3 -m http.server --directory .tools/pages-site 8000
```

The generated site is ignored under `.tools/pages-site/`. `gen/` remains
generator-owned; publication copies it without changing it. Site links are
relative so project Pages URLs and nested report/document paths work.

## DMA names and expected errors

The default CPU cold-boot configuration disables real DMA RTL with
`DmaEnable=0`; the separate `chip-dma` regression enables two real PULP
iDMA engines and their generated 32-bit CSR bridges. During CPU boot the
verification BFM occupies compute0's inactive DMA port after CPU coordination
and compute1's port remains idle. Separate actor maps identify those BFMs
versus active DMA RTL in the DMA-only simulation.

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
physical DDR/HBM controller integration (the separate `chip-cpu-dma` gate verifies CPU0-launched C DMA with passive AXI evidence).

Successful [isolated](https://github.com/r987r/xezim-hello-world/actions/runs/41860245485) and [full-chip](https://github.com/r987r/xezim-hello-world/actions/runs/41885417960) DMA CI evidence is associated with its tested Git SHA. The Pages collector must verify a merged PR/source before treating either as current main evidence; the prior runs do not alone validate a new merged tree.

## Address-map page and generated CSR artifacts

The verification hub has one dedicated, mobile-friendly `Address Map`
navigation page using `config/soc.yaml` for every architectural data and
configuration aperture. `data/soc-address-map.json` is the complete source
catalog; `data/soc-data-memories.rdl` is an external-memory SystemRDL view,
not memory RTL. Unassigned holes are not backed storage.

GitHub Pages CI pins SystemRDL/PeakRDL and emits the reset-control RDL
register contract and per-IP C headers, which are published as downloads.
If pinned generation fails, Pages build fails, rather than silently
publishing stale register definitions. Local preview without generation
is explicitly aperture-only. These are *definitions*, not proof that the
compiled RTL storage or frontdoor/backdoor paths match the catalog.
Individual AXI run reports remain the source for real accepted transactions.
PR preview builds do not deploy; merge-to-main dispatch is the only
Pages deployment path.


## Current CSR / DDR register-reference release gate (2026-11-06)

The **merged** Pages Address Map is a useful *human-readable aperture and
partial-register inventory*: search by region/address, filter the data/config
planes, select a known register, and inspect its source-defined metadata. It
is **not yet a completed per-IP field datasheet for all subsystems**: the
existing Inspect details use JSON, and unsourced register fields or resets
must remain absent. The [CSR ownership matrix](csr-generation.md) lists
which register sources and generated firmware integrations are qualified.

The real LiteDRAM DDR-B controller was integrated via merged PR #74, but
the **native controller CSR register view** is a distinct, still-draft
integration in [PR #100](https://github.com/r987r/xezim-hello-world/pull/100).
It imports vendor-generated `csr.json`, checks the translated 16-KiB
`memory0.ctrl` register window, and prepares a variant selector for this
same Address Map. The *default* build continues to show the 4-KiB
reserved controller window and fast AXI-RAM backing, never a fabricated
active controller. Successful CSR and Pages **PR preview** jobs do not
publish that native DDR view. The real-DDR CSR full-chip evidence has now **passed** in
[workflow 42267019604](https://github.com/r987r/xezim-hello-world/actions/runs/42267019604),
including the 16-KiB native register catalog and accepted Config-NoC CSR reads/writes.
It still requires conflict reconciliation, exact-final-head CI, merge to main,
and a successful main Pages deployment before the DDR variant can be considered live.

**Verified publication status at this review:** the main [Pages workflow
42265803416](https://github.com/r987r/xezim-hello-world/actions/runs/42265803416)
successfully built site artifacts, but its deployment was left queued and
failed with `Deployment failed, try again later`. Subsequently,
[main workflow 42271755340](https://github.com/r987r/xezim-hello-world/actions/runs/42271755340)
completed **both build and deployment successfully** for its own tested commit. Do not claim the latest main source is live solely
because its build succeeded, nor promise an old Pages release shows later
CSR changes. A new main-ref release must independently complete its deploy
job and the actual published route must be checked before declaring release.

**Provenance distinction:** a declared register is metadata, an
exact-variant RTL attachment is implementation evidence, and completed
passive Config-NoC requests/responses are observation evidence.
Back-door snapshots are not AXI frontdoor transactions. ACT/PCH/RD/WR
are DDR protocol/DFI events, not CSR register definitions. Firmware
register headers must be per-IP generated and compiled for the actual
selected CPU/test variant; opt-in generated-header image equality under
[#90](https://github.com/r987r/xezim-hello-world/issues/90) does not
prove production-wide adoption. These rules also apply to Ethernet, PCIe
and iDMA sources when their catalogs are imported.
