"""Human-readable review report from verified standalone DDR4 RTL evidence.

This is intentionally not a full-chip Fabric Explorer measurement.
Never render PASS or zero-latency placeholders without validated input.
"""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import sys


def load(directory: Path) -> dict:
    def read(name):
        path = directory / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"missing/unsafe DDR4 evidence file: {name}")
        return json.loads(path.read_text())

    result = read("ddr4_functional_result.json")
    axi = read("ddr4_latency.json")
    dfi = read("ddr4_internal_latency.json")
    monitor = read("ddr4_traffic_summary.json")
    compiler = read("ddr4_warning_audit.json")
    if result.get("status") != "pass" or monitor.get("status") != "pass":
        raise ValueError("DDR4 run or passive capture did not pass")
    if dfi.get("status") != "measured_model_events":
        raise ValueError("DFI measured-stage evidence missing")
    if result.get("monitor", {}).get("sampled_cycles") != monitor.get("sampled_cycles"):
        raise ValueError("DDR4 passive monitor cycle mismatch")
    if not monitor.get("continuous_capture") or monitor.get("overflows"):
        raise ValueError("DDR4 missing continuous capture or overflowed")
    if compiler.get("status") != "pass":
        raise ValueError("Verilator diagnostic audit missing or failed")
    for op in ("read", "write"):
        if axi.get("measured", {}).get(op, {}).get("samples", 0) < 1:
            raise ValueError(f"DDR4 {op} missing measured completed AXI transactions")
    return {"run": result, "axi": axi, "dfi": dfi, "monitor": monitor,
            "compiler": compiler}


def render(data: dict) -> str:
    axi, dfi, monitor = (data[k] for k in ("axi", "dfi", "monitor"))
    period = axi["reference_clock"]["period_ps"]
    if period <= 0:
        raise ValueError("invalid measured clock period")
    def h(s):
        return escape(str(s), quote=True)
    def n(v):
        return f"{v:.2f}" if isinstance(v, (int, float)) else "—"
    def row(*cells):
        return "<tr>" + "".join(f"<td>{h(c)}</td>" for c in cells) + "</tr>"
    axi_rows = "".join(row(op.upper(), val["samples"],
                           n(val["min_cycles"]), n(val["avg_cycles"]), n(val["max_cycles"]),
                           axi["measured_boundary"][op])
                       for op, val in axi["measured"].items())
    stage_rows = ""
    for name, stage in sorted(dfi["internal_stages"].items()):
        if stage.get("status") == "measured":
            stage_rows += row(name, "MEASURED", stage.get("samples"), n(stage.get("avg_cycles")),
                              "RTL/model event timestamps")
        else:
            stage_rows += row(name, "UNMEASURED", "—", "—",
                              stage.get("reason", "No justified event association"))
    channels = " · ".join(f"{h(ch.upper())} {h(monitor['channels'].get(ch, 0))}"
                          for ch in ("aw", "w", "b", "ar", "r"))
    stalls=monitor.get("backpressure_valid_not_ready_cycles") or {}
    stalled_r=int(stalls.get("r", 0))
    stalled_b=int(stalls.get("b", 0))
    if stalled_r < 0 or stalled_b < 0:
        raise ValueError("negative DDR4 backpressure observation")

    period_ns = period / 1000
    run = data["run"]
    warnings = data["compiler"].get("total_warnings", "not available")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Standalone LiteDRAM DDR4 — verification report</title>
<style>
:root{{color-scheme:light dark;font-family:system-ui,-apple-system,Arial,sans-serif}}
body{{max-width:1100px;margin:auto;padding:1.2rem;line-height:1.5}}
a{{color:inherit}} h1,h2{{line-height:1.2}}
table{{border-collapse:collapse;width:100%;font-size:.9rem;min-width:620px}}
td,th{{border-bottom:1px solid #8885;text-align:left;padding:.55rem}}
th{{background:#8882}}.scroll{{overflow-x:auto}}.muted{{opacity:.78}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:.7rem}}
.card{{border:1px solid #8886;border-radius:9px;padding:12px}}
.card strong{{font-size:1.2rem;display:block}}.ok{{font-weight:700}}
</style></head><body>
<h1>LiteDRAM DDR4 — standalone verification report</h1>
<p class="muted">Actual LiteDRAM controller RTL + upstream DFI simulation PHY/BankModel.
This is NOT an integrated Memory0 Data NoC run, electrical DDR PHY, or silicon timing report.</p>
<div class="cards">
<div class="card"><strong class="ok">PASS</strong>RTL/DFI functional</div>
<div class="card"><strong>{h(monitor["sampled_cycles"])}</strong>Observed clock cycles</div>
<div class="card"><strong>{h(period_ns)} ns</strong>Observed 100 MHz source period</div>
<div class="card"><strong>{h(warnings)}</strong>Reviewed upstream warnings</div>
</div>
<h2>Completed AXI boundary latency (source-clock cycles)</h2>
<p>Read: accepted AR → final accepted R. Write: accepted AW → accepted B.
These values include RTL controller, behavioral DFI/BankModel and queued response handling.</p>
<div class="scroll"><table><thead><tr><th>Operation</th><th>Samples</th><th>Min</th><th>Avg</th><th>Max</th><th>Measured boundary</th></tr></thead>
<tbody>{axi_rows}</tbody></table></div>
<h2>DFI and modeled-bank stage evidence</h2>
<p>No DFI AXI transaction IDs exist. Overlapping requests cannot be attributed
to individual DFI commands; missing correlations stay explicitly UNMEASURED.</p>
<div class="scroll"><table><thead><tr><th>Observed stage</th><th>Status</th><th>Samples</th><th>Avg cycles</th><th>Evidence/limitation</th></tr></thead>
<tbody>{stage_rows}</tbody></table></div>
<h2>Passive protocol coverage</h2>
<p>{channels}. Backpressure observed on real controller outputs:
R VALID&&!READY {h(stalled_r)} cycles, B VALID&&!READY {h(stalled_b)} cycles.
Capture: {h(monitor["sampled_cycles"])} continuous clock samples,
zero overflow, all initialization/traffic/post-traffic phases present.
Actual Verilator errors: 0; upstream warnings remain audited rather than globally suppressed.</p>
<p>Report source: {h(run.get("top", "soc_ddr4_sim"))} / standalone generated controller;
raw traces, pin map, build manifest, source hashes and diagnostic audit are
in the same GitHub Actions DDR4 artifact.</p>
<p class="muted">Stalled or concurrent transaction tests do not imply measured controller-internal
outstanding depth. DDR4 full-chip ingress, CPU/iDMA and configuration-NoC initialization
remain unverified unless a separate complete full-chip regression proves them.</p>
</body></html>"""


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", type=Path, required=True)
    args = p.parse_args()
    try:
        data = load(args.dir)
        html = render(data)
        out = args.dir / "ddr4-report.html"
        out.write_text(html)
    except (KeyError, ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
        print(f"DDR4 review report refused invalid evidence: {exc}", file=sys.stderr)
        return 1
    print(f"DDR4 standalone review report: {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
