#!/usr/bin/env python3
"""Find the first rising or falling edge of a signal in a VCD file.

Usage:
    python3 scripts/vcd/vcd_find_edge.py <vcd_file> <signal_name> [--edge rising|falling|any]

Examples:
    python3 scripts/vcd/vcd_find_edge.py run/axis_single/trace.vcd tb_top.dut.pipe_valid[0] --edge rising
    python3 scripts/vcd/vcd_find_edge.py run/axis_single/trace.vcd tb_top.axis_in.tvalid
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def parse_vcd_signals(vcd_path: Path) -> dict[str, str]:
    """Parse VCD header and return {hierarchical_name: vcd_id} mapping."""
    signals: dict[str, str] = {}
    scope_stack: list[str] = []

    with vcd_path.open() as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("$scope"):
                parts = line.split()
                if len(parts) >= 3:
                    scope_stack.append(parts[2])
            elif line.startswith("$upscope"):
                if scope_stack:
                    scope_stack.pop()
            elif line.startswith("$var"):
                parts = line.split()
                if len(parts) >= 5:
                    vcd_id = parts[3]
                    name = parts[4]
                    full_name = ".".join(scope_stack + [name])
                    signals[full_name] = vcd_id
            elif line.startswith("$enddefinitions"):
                break

    return signals


def find_edge(
    vcd_path: Path,
    signal_name: str,
    edge: str = "rising",
) -> tuple[int | None, str | None, str | None]:
    """Find the first edge of the given signal.

    Returns (time_ps, old_value, new_value) or (None, None, None) if not found.
    """
    signals = parse_vcd_signals(vcd_path)

    # Find matching signal (support partial match)
    target_id = None
    matched_name = None
    for name, vid in signals.items():
        if name == signal_name or name.endswith("." + signal_name):
            target_id = vid
            matched_name = name
            break

    if target_id is None:
        # Try substring match
        candidates = [n for n in signals if signal_name in n]
        if len(candidates) == 1:
            matched_name = candidates[0]
            target_id = signals[matched_name]
        elif len(candidates) > 1:
            print(f"Ambiguous signal '{signal_name}'. Candidates:", file=sys.stderr)
            for c in sorted(candidates)[:20]:
                print(f"  {c}", file=sys.stderr)
            return None, None, None
        else:
            print(f"Signal '{signal_name}' not found in VCD.", file=sys.stderr)
            return None, None, None

    # Parse value changes
    current_time = 0
    prev_value: str | None = None

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
                continue

            # Single-bit value change: 0id or 1id or xid
            if len(line) >= 2 and line[0] in "01xzXZ":
                val = line[0]
                vid = line[1:]
                if vid == target_id:
                    if prev_value is not None:
                        is_rising = prev_value in ("0", "x", "X", "z", "Z") and val == "1"
                        is_falling = prev_value == "1" and val in ("0", "x", "X", "z", "Z")
                        if (edge == "rising" and is_rising) or \
                           (edge == "falling" and is_falling) or \
                           (edge == "any" and (is_rising or is_falling)):
                            return current_time, prev_value, val
                    prev_value = val

            # Multi-bit value change: b<bits> <id>
            if line.startswith("b") or line.startswith("B"):
                parts = line.split()
                if len(parts) == 2 and parts[1] == target_id:
                    val = parts[0][1:]  # strip leading 'b'
                    if prev_value is not None and val != prev_value:
                        if edge == "any":
                            return current_time, prev_value, val
                        # For multi-bit, "rising" means went from 0 to non-0
                        all_zero_prev = all(c in "0xXzZ" for c in prev_value)
                        has_one_now = any(c == "1" for c in val)
                        if edge == "rising" and all_zero_prev and has_one_now:
                            return current_time, prev_value, val
                        all_zero_now = all(c in "0xXzZ" for c in val)
                        if edge == "falling" and not all_zero_prev and all_zero_now:
                            return current_time, prev_value, val
                    prev_value = val

    return None, None, None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find the first edge of a signal in a VCD file."
    )
    parser.add_argument("vcd_file", type=Path, help="Path to VCD file")
    parser.add_argument("signal", nargs="?", default=None,
                        help="Signal name (hierarchical or partial match)")
    parser.add_argument(
        "--edge",
        choices=["rising", "falling", "any"],
        default="rising",
        help="Edge type to find (default: rising)",
    )
    parser.add_argument(
        "--list-signals",
        action="store_true",
        help="List all signals in the VCD and exit",
    )
    args = parser.parse_args()

    if not args.vcd_file.exists():
        print(f"VCD file not found: {args.vcd_file}", file=sys.stderr)
        raise SystemExit(1)

    if args.list_signals:
        signals = parse_vcd_signals(args.vcd_file)
        for name in sorted(signals):
            print(name)
        return

    if args.signal is None:
        parser.error("signal is required unless --list-signals is used")

    time_ps, old_val, new_val = find_edge(args.vcd_file, args.signal, args.edge)
    if time_ps is None:
        print(f"No {args.edge} edge found for signal '{args.signal}'")
        raise SystemExit(1)

    time_ns = time_ps / 1000.0
    print(f"First {args.edge} edge of '{args.signal}':")
    print(f"  Time: {time_ps} ps ({time_ns:.3f} ns)")
    print(f"  Value: {old_val} → {new_val}")


if __name__ == "__main__":
    main()
