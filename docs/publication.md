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

## Collection, retention and reproducibility

`config/publication.yaml` selects trusted producer workflows and artifact names,
history depth and archive size limits. Every PR targeting `main` builds an
offline preview. After a PR merges, a minimally privileged PR-close job dispatches
one new Pages workflow on the actual `main` ref, so the GitHub Pages environment
permits deployment; that main-ref run builds and publishes the trusted `main`
checkout. Manual dispatch on `main` publishes as well; a manual feature-branch
dispatch builds a preview without deployment. No automatic branch push or
CI-completion triggers remain.

The collector searches the latest 500 Actions runs and keeps up to four runs
per configured producer. It accepts main-branch results and completed PR results
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
Only the explicit evidence file types are republished, not compiler object
directories. Pages history is rebuilt from still-available Actions artifacts;
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

There are **zero instantiated DMA engines** in the chip boot configuration.
`dma` and `dma_regs` are reserved architecture endpoint names, not evidence of
integration. The chip test temporarily drives compute0's reserved initiator
with upstream `cocotbext-axi` verification BFM traffic after the real CPUs finish
coordination. Compute1's DMA boundary remains idle. Generated actor metadata and
new reports explicitly distinguish real CPUs, BFMs, idle ports and error responders.

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
