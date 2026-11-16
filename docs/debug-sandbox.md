# Reproducible interactive RTL debugging (Vercel + GitHub CI)

**Status:** shared exploratory workflow; final qualification remains with the
original repository-owned CI, simulator and unmodified test scoreboard. Related
PCIe investigation: [draft PR #232](https://github.com/r987r/xezim-hello-world/pull/232)
and [issue #76](https://github.com/r987r/xezim-hello-world/issues/76). The
shared debug implementation was merged via [PR #250](https://github.com/r987r/xezim-hello-world/pull/250);
exact simulator parity and real RTL recipe onboarding are tracked in
[issue #251](https://github.com/r987r/xezim-hello-world/issues/251).
This guide does **not** claim the standalone PCIe fix is wired into the full SoC.

## Required debugging loop

1. **Capture failing evidence from CI:** exact commit, selected source/config,
   original failing assertion, command, tool versions, seed if the test provided
   one, original waveform and protocol-monitor report.
2. **Run in an isolated disposable sandbox:** use the exact repository checkout,
   pinned IP revisions and recipe; do not replace real RTL with stubs or alter the
   scoreboard. For expensive full RTL use the same simulator build as CI.
3. **Find the first disagreement:** add *passive* handshake/credit/packet probes.
   Track accepted AXI-Stream beats (`tvalid && tready`), then correlate with
   native PIPE TLP/DLLP, AXI and event traces. For clock-domain comparisons,
   normalize timestamps using the recorded clock source.
4. **One hypothesis per experiment:** keep baseline, changed file/diff,
   command, source SHA, logs and pass/fail truth. Test a patch both with and
   without unrelated experimental instrumentation.
5. **Commit only reviewed fixes and regression coverage** on an isolated branch
   or the issue's active PR. Independent GitHub Actions CI is the final gate.
   Do not infer full-chip signoff from a standalone upstream Cocotb result.
6. **Stop the sandbox** and retain a reproducible snapshot only if needed.
   Track snapshot lifetime and cost; do not rely on a VM remaining alive.

## Repository-owned debug recipes

`config/debug.yaml` is a small **debug-only** set of argv recipes. It does not
introduce a second test engine and does not replace `config/regression.yaml`,
`tools/regress.py` or canonical test result artifacts. To add a subsystem,
reference its existing command; do not duplicate stimulus generation.

```bash
python3 -m pip install PyYAML==6.0.3
python3 tools/debug_repro.py --audit
python3 tools/debug_repro.py --profile regression-unit \
  --out .tools/debug-runs/regression-audit-001
```

The runner rejects modified tracked source by default, requires an explicit
`--allow-dirty` for controlled A/B experiments, refuses to overwrite existing
run evidence, enforces timeouts (including termination of spawned POSIX
process groups), and retains `run.json` plus combined
`stdout-stderr.log`. It records exact commit, branch, dirty flag, command,
UTC timestamps, tool versions and `SEED` as a value only when actually supplied
(otherwise `seed: null`). Tool versions are **observed**, not yet required to
match CI; simulator parity enforcement belongs to #251.
A child failure remains a failure; even a zero exit is marked
`qualification: exploratory_only`. The original Cocotb/scoreboard gate must
still be evaluated by the existing CI procedure.

The CLI accepts **only** the checked-in `config/debug.yaml` recipes (no
arbitrary command or external config file). The `chip-pcie-host` debug profile runs the **existing real RTL**
`python3 tools/regress.py chip-pcie-host` unchanged: it includes actual CPU,
PCIe TLP/AXI bridge, FlooNoC and SRAM with a modeled host link, **not**
the independent Gen1 digital PIPE on PR #232. Run it with:

```bash
python3 tools/debug_repro.py --profile chip-pcie-host \\
  --out .tools/debug-runs/pcie-host-001
```

The canonical regression still owns simulator PASS/FAIL and keeps its existing
per-test traces/reports in `.tools/regression/chip-pcie-host/`; the debug
wrapper keeps its separate source-stamped transcript and run metadata.
On-demand real Gen1 PIPE, DDR and Ethernet recipe onboarding remains #251.
No new simulator, stimulus dispatcher, or reporting format is introduced. The runner does not collect an
IP-overlay diff or waveform automatically; preserve and attach those from the
original test infrastructure when relevant. An `--allow-dirty` run records
that tracked files changed but does not itself capture their content/diff.

All evidence is local and ignored beneath `.tools/debug-runs/`.
If a run is worth preserving for a PR, attach the raw run directory to the
existing workflow's **artifact/report** path with its source SHA and CI link;
never substitute a new success flag or synthesize unobserved protocol events.

## Vercel Sandbox contract

A Vercel Sandbox is a real Linux VM and is useful for live compile/execute,
log inspection and repeated A/B edits. A saved named sandbox can be resumed
from a filesystem snapshot; **processes do not survive**. Use a 2-vCPU/4-GB
profile for light triage or 4-vCPU/8-GB for large Verilator builds on Hobby;
sessions have a 45-minute plan limit. The snapshots are per-VM caches, not
source-of-truth. Always stop on completion and avoid committing `.tools/`
or `build/`.

**Toolchain audit before RTL (manual until #251):**

```bash
git rev-parse HEAD
git status --short
python3 --version
verilator --version
iverilog -V | head -n 2
```

CI's PCIe job on PR #232 used YosysHQ's
`setup-oss-cad-suite@v4` **2026-11-10**, yielding Verilator **5.055 devel**.
The first Vercel VM installed Debian Verilator **5.032**: its FST trace runtime
aborted inside `verilated_fst_c.cpp`, although the same RTL ran without FST.
**Do not classify a 5.032 tracing assertion as PCIe RTL failure.** For waveform
qualification install and verify the exact CI-pinned OSS CAD Suite; disabling
runtime FST is acceptable for an explicitly marked exploratory run only.

## PCIe lesson: precise boundary tracing

In the original OpenPCIe checkout, `src/dllp/axis_user_demux.sv` reported
upstream ready from the *downstream output* of an internal AXIS skid register.
The correct accepted-beat handshake uses the skid register's **input ready**.
The upstream PHY believed it had transferred DLLP header `00041080` at
644.915 us, but the header was missing after demux; an orphaned CRC led to
receiver resynchronization and CplH credit starvation at 76/76. A
source-locked four-line demux handshake overlay passed original upstream
Cocotb readback both in Vercel and independent pinned GitHub CI, including a
valid FST on newer CI Verilator.

A/B testing also showed that the separate experimental CplD first-beat guard
was not necessary for that particular readback pass. This **does not prove
OpenPCIe bug-free**. Add randomized input/output ready/valid stress, legal
single-beat/end-of-packet cases and loss/duplication/order assertions before
integrating the repair into selected production SoC RTL.

## Audit & open gates

- **Source provenance:** frozen lockfile, applied source diff and exact
  simulator versions. The current generic wrapper records version strings,
  but does not yet enforce simulator/image parity or pin RTL provider overlays;
  those must be verified by existing source-pinned workflows until #251.
- **Test authenticity:** original driver + scoreboard, byte-for-byte readback,
  real completions, positive and negative tests. `PASS` must not come from
  a watchdog exit or elaboration alone.
- **Coverage:** directed and randomized backpressure, resets, clock domains,
  FIFO full/empty, CplH/CplD credits, host/endpoint directions, long offsets.
- **Scalability:** reuse existing protocol monitors, reports and INIT/RUN/CHECK
  executor; no duplicate PCIe decoder or action runtime.
- **Scope limits:** standalone OpenPCIe PASS is not yet real end-to-end PCIe
  host ↔ full SoC NoC ↔ memory qualification. Keep #76 and PR #232 open until
  source-selected endpoint, host, NoC and scoreboard all pass together.
- **Security/cost:** use isolated sandbox, trusted source revisions, no
  credentials committed to logs, fixed timeouts and stop after use. Recipe
  subprocess trees are killed on timeout on POSIX; sandbox sessions must also
  be stopped by their owner to end VM billing.
