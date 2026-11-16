#!/usr/bin/env python3
"""Adapt pinned OpenPCIe's existing PHY TLP/DLLP monitor to shared evidence.

No PHY sampler, packet decoder, completion generator or second monitoring
framework is implemented here. Input events are original pipe_monitor_bfm
callbacks with genuine Cocotb ps timestamps. This runs post-simulation,
including on failed CI jobs, and NEVER upgrades a failing Cocotb test to PASS.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

# Direct 'python3 tools/...' execution still resolves shared repo-root DV.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dv.common.protocol_trace import ProtocolTrace
from tools import protocol_report

SOURCE = "pcie0.pipe.ep_tx"
PROVIDER = "openpcie_native_pipe_monitor"
FRAME = re.compile(
    r"^PCIE_UPSTREAM_PIPE_MON_(TLP|DLLP): direction=EP_TO_RC "
    r"time_ps=([0-9]+) bytes=([0-9]+) raw=([0-9a-f]+)$"
)
# Only these original pyuvm result summaries are authoritative for test PASS.
RESULT = re.compile(r"\bTESTS=([0-9]+) PASS=([0-9]+) FAIL=([0-9]+) SKIP=([0-9]+)\b")


def source_catalog():
    return {SOURCE: {
        "protocol": "pcie", "role": "link",
        "clock_domain": "openpcie_core_clk",
        "implementation": PROVIDER,
        "modeling": "behavioral_digital_phy",
    }}


def capture(log_text: str, output: Path, *, max_events: int = 100000) -> dict:
    """Capture original monitor callbacks, not a prediction of host delivery."""
    summaries = RESULT.findall(log_text)
    if not summaries:
        raise ValueError("original upstream Cocotb result table missing")
    summary = tuple(map(int, summaries[-1]))
    if summary[0] < 1 or summary[0] != sum(summary[1:]):
        raise ValueError("invalid original upstream Cocotb test summary")
    test_pass = summary[1] == summary[0] and summary[2] == summary[3] == 0
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    capture_path = output / "protocol-events.jsonl"
    trace = ProtocolTrace(capture_path, source_catalog(), max_events=max_events)
    counts = {"tlp": 0, "dllp": 0}
    try:
        for index, full_line in enumerate(log_text.splitlines(), 1):
            # GitHub Actions prepends a wall-clock UTC prefix. The original
            # monitor itself supplies the *simulation* timestamp, in ps.
            line = full_line[full_line.index("PCIE_UPSTREAM_PIPE_MON_"):] \
                if "PCIE_UPSTREAM_PIPE_MON_" in full_line else ""
            if not line:
                continue
            match = FRAME.fullmatch(line)
            if not match:
                raise ValueError(f"malformed native PIPE monitor event line {index}")
            kind, stamp, size, hex_bytes = match.groups()
            if len(hex_bytes) != 2 * int(size) or not size or int(size) == 0:
                raise ValueError(f"native PIPE byte count mismatch line {index}")
            if int(size) > 65536:
                raise ValueError("oversized native PIPE frame")
            # Validate rather than reinterpret original bytes. Keep all
            # repeats/replays and unknown TLP/DLLP fields unchanged.
            raw = bytes.fromhex(hex_bytes)
            kind = kind.lower()
            counts[kind] += 1
            trace.event(SOURCE, kind + "_frame", int(stamp), {
                "direction": "ep_to_rc",
                "boundary": "openpcie_phy_txdata_k_decoder",
                "data_hex": raw.hex(), "length_bytes": len(raw),
                "provider": PROVIDER, "rc_receipt": "not_measured",
                "source_log_line": index,
            })
        if not all(counts.values()):
            raise ValueError("missing original native TLP/DLLP monitor capture")
        trace.close("pass")  # Capture integrity only, NOT original test PASS.
    except BaseException as exc:
        if not trace.closed:
            trace.close("fail", exc)
        raise

    plan = {
        "target": "pcie-openpcie-original-selftest-capture-only",
        "engine": "verilator",
        "report": {"protocols": {
            "sources": source_catalog(), "max_events": max_events,
        }},
    }
    report = protocol_report.build(output, plan)
    if report is None or not report["capture_complete"]:
        raise ValueError("shared protocol exporter failed to validate native capture")
    # The original source test may fail while its packet monitor yields valid
    # diagnostics. Recording its failure is mandatory; never create result.json.
    report["run"]["test_status"] = "pass" if test_pass else "fail"
    report["run"]["qualification"] = "capture_only_original_upstream"
    report["run"]["original_cocotb_tests"] = {
        "total": summary[0], "pass": summary[1],
        "fail": summary[2], "skip": summary[3],
    }
    report["run"]["source_monitor"] = PROVIDER
    report["run"]["link_scope"] = "endpoint_tx_only_rc_receipt_not_measured"
    (output / "protocol-transactions.json").write_text(
        json.dumps(report, indent=2) + "\n")
    protocol_report.render(report, output / "protocols.html")
    return {"counts": counts, "original_test_pass": test_pass,
            "capture_complete": True, "source": SOURCE}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = capture(args.log.read_text(errors="replace"), args.out)
    print("PCIE_NATIVE_PIPE_CAPTURE: " + json.dumps(result, sort_keys=True))
    # The original upstream Cocotb required gate is enforced by
    # ci_require_cocotb.py; this tool never changes that result.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
