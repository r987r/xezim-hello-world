#!/usr/bin/env python3
"""Count signal transitions in a VCD file over a time window.

Usage:
    python3 tools/debug/vcd_signal_activity.py <vcd_file> <signal_name> [--start <ps>] [--end <ps>]

Examples:
    python3 tools/debug/vcd_signal_activity.py run/axis_single/trace.vcd tb_top.axis_in.tvalid
    python3 tools/debug/vcd_signal_activity.py run/axis_single/trace.vcd tb_top.dut.pipe_valid[49] --start 0 --end 5000000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from vcd_find_edge import parse_vcd_signals
except ImportError:
    from scripts.vcd_find_edge import parse_vcd_signals


def count_transitions(
    vcd_path: Path,
    signal_name: str,
    start_ps: int = 0,
    end_ps: int | None = None,
) -> dict:
    """Count transitions of a signal in the given time window.

    Returns dict with transition statistics.
    """
    signals = parse_vcd_signals(vcd_path)

    # Find matching signal
    target_id = None
    matched_name = None
    for name, vid in signals.items():
        if name == signal_name or name.endswith("." + signal_name):
            target_id = vid
            matched_name = name
            break

    if target_id is None:
        candidates = [n for n in signals if signal_name in n]
        if len(candidates) == 1:
            matched_name = candidates[0]
            target_id = signals[matched_name]
        elif len(candidates) > 1:
            print(f"Ambiguous signal '{signal_name}'. Candidates:", file=sys.stderr)
            for c in sorted(candidates)[:20]:
                print(f"  {c}", file=sys.stderr)
            return {}
        else:
            print(f"Signal '{signal_name}' not found in VCD.", file=sys.stderr)
            return {}

    # Parse value changes
    current_time = 0
    prev_value: str | None = None
    rising = 0
    falling = 0
    total_changes = 0
    first_change_time: int | None = None
    last_change_time: int | None = None
    time_high = 0
    last_high_start: int | None = None

    with vcd_path.open() as fh:
        in_defs = True
        for line in fh:
            line = line.strip()
            if in_defs:
                if line.startswith("$enddefinitions"):
                    in_defs = False
                continue

            if line.startswith("#"):
                current_time = int(line[1:])
                if end_ps is not None and current_time > end_ps:
                    break
                continue

            # Single-bit value change
            if len(line) >= 2 and line[0] in "01xzXZ":
                val = line[0]
                vid = line[1:]
                if vid == target_id and current_time >= start_ps:
                    if prev_value is not None and val != prev_value:
                        total_changes += 1
                        if first_change_time is None:
                            first_change_time = current_time
                        last_change_time = current_time

                        if val == "1" and prev_value in ("0", "x", "X", "z", "Z"):
                            rising += 1
                            last_high_start = current_time
                        elif prev_value == "1" and val in ("0", "x", "X", "z", "Z"):
                            falling += 1
                            if last_high_start is not None:
                                time_high += current_time - last_high_start
                                last_high_start = None
                    elif prev_value is None:
                        if val == "1":
                            last_high_start = current_time
                    prev_value = val

            # Multi-bit value change
            if line.startswith("b") or line.startswith("B"):
                parts = line.split()
                if len(parts) == 2 and parts[1] == target_id and current_time >= start_ps:
                    val = parts[0][1:]
                    if prev_value is not None and val != prev_value:
                        total_changes += 1
                        if first_change_time is None:
                            first_change_time = current_time
                        last_change_time = current_time
                    prev_value = val

    # Account for final high period
    if last_high_start is not None:
        final_time = end_ps if end_ps is not None else current_time
        time_high += final_time - last_high_start

    return {
        "signal": matched_name,
        "rising_edges": rising,
        "falling_edges": falling,
        "total_changes": total_changes,
        "first_change_ps": first_change_time,
        "last_change_ps": last_change_time,
        "time_high_ps": time_high,
        "window_start_ps": start_ps,
        "window_end_ps": end_ps or current_time,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count signal transitions in a VCD file."
    )
    parser.add_argument("vcd_file", type=Path, help="Path to VCD file")
    parser.add_argument("signal", help="Signal name (hierarchical or partial match)")
    parser.add_argument("--start", type=int, default=0, help="Start time in ps (default: 0)")
    parser.add_argument("--end", type=int, default=None, help="End time in ps (default: end of VCD)")
    args = parser.parse_args()

    if not args.vcd_file.exists():
        print(f"VCD file not found: {args.vcd_file}", file=sys.stderr)
        raise SystemExit(1)

    stats = count_transitions(args.vcd_file, args.signal, args.start, args.end)
    if not stats:
        raise SystemExit(1)

    print(f"Signal activity for '{stats['signal']}':")
    print(f"  Window: {stats['window_start_ps']} ps - {stats['window_end_ps']} ps")
    print(f"  Total changes:  {stats['total_changes']}")
    print(f"  Rising edges:   {stats['rising_edges']}")
    print(f"  Falling edges:  {stats['falling_edges']}")
    if stats["first_change_ps"] is not None:
        print(f"  First change:   {stats['first_change_ps']} ps ({stats['first_change_ps']/1000:.3f} ns)")
        print(f"  Last change:    {stats['last_change_ps']} ps ({stats['last_change_ps']/1000:.3f} ns)")
    if stats["time_high_ps"] > 0:
        window = stats["window_end_ps"] - stats["window_start_ps"]
        duty = (stats["time_high_ps"] / window * 100) if window > 0 else 0
        print(f"  Time high:      {stats['time_high_ps']} ps ({duty:.1f}% duty cycle)")


if __name__ == "__main__":
    main()
