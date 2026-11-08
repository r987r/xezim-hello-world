#!/usr/bin/env python3
"""Fast generated SuperNoC wrapper contract; runs in existing lint CI.

This checks GENERATED SOURCE declarations and direct named instantiation
bindings only. It does not claim compiler-elaborated data-flow or internal
FlooNoC route/protocol correctness; those remain functional RTL evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = Path("gen/supernoc/supernoc_tb.sv")
CORE = Path("gen/supernoc/soc_noc.sv")
PORT = re.compile(r"^\s*(input|output)\s+logic(?:\s+\[(\d+):(\d+)\])?\s+([A-Za-z_]\w*)\s*,?\s*$")
BIND = re.compile(r"^\s*\.([A-Za-z_]\w*)\(([A-Za-z_]\w*)\)\s*,?\s*$")
REQUIRED = (
    "clk_i", "rst_ni", "m_compute0_local_data_cpu_awid",
    "m_ethernet0_local_data_packet_dma_awvalid",
    "m_pcie0_local_data_host_awvalid",
    "s_memory0_local_data_target_crossbar_awvalid",
)


class InterfaceContractError(ValueError):
    """A generated interface declaration/binding is incomplete or inconsistent."""


def _body(text: str, pattern: str, label: str) -> str:
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        raise InterfaceContractError(f"{label}: missing or ambiguous declaration/instance")
    start = matches[0].end()
    end = text.find(");", start)
    if end < 0:
        raise InterfaceContractError(f"{label}: unterminated ports")
    return text[start:end]


def _declarations(text: str, module: str) -> dict[str, tuple[str, int]]:
    body = _body(text, rf"\bmodule\s+{re.escape(module)}\s*\(", module)
    result = {}
    for line in body.splitlines():
        if not line.strip():
            continue
        match = PORT.fullmatch(line.strip())
        if match is None:
            raise InterfaceContractError(f"{module}: unrecognized generated port declaration {line!r}")
        direction, msb, lsb, name = match.groups()
        if name in result:
            raise InterfaceContractError(f"{module}: duplicate port {name}")
        result[name] = (direction, abs(int(msb) - int(lsb)) + 1 if msb else 1)
    if not result:
        raise InterfaceContractError(f"{module}: empty interface")
    return result


def _bindings(text: str) -> dict[str, str]:
    body = _body(text, r"\bsoc_noc\s+u_noc\s*\(", "soc_noc u_noc")
    result = {}
    for line in body.splitlines():
        if not line.strip():
            continue
        match = BIND.fullmatch(line.strip())
        if match is None:
            raise InterfaceContractError(f"u_noc: non-direct/unsupported binding {line!r}")
        name, signal = match.groups()
        if name in result:
            raise InterfaceContractError(f"u_noc: duplicate binding {name}")
        result[name] = signal
    return result


def verify(wrapper: str, core: str) -> dict:
    outer = _declarations(wrapper, "supernoc_tb")
    inner = _declarations(core, "soc_noc")
    binding = _bindings(wrapper)
    if set(outer) != set(inner) or set(inner) != set(binding):
        missing_core = sorted(set(outer) - set(inner))
        missing_wrapper = sorted(set(inner) - set(outer))
        unbound = sorted(set(inner) - set(binding))
        extra_bindings = sorted(set(binding) - set(inner))
        raise InterfaceContractError(
            f"source port inventory mismatch (core missing={missing_core[:6]}, "
            f"wrapper missing={missing_wrapper[:6]}, "
            f"unbound={unbound[:6]}, unknown bindings={extra_bindings[:6]})")
    for name, (direction, width) in inner.items():
        if outer[name] != (direction, width):
            raise InterfaceContractError(f"{name}: source port width/direction mismatch")
        if binding[name] != name:
            raise InterfaceContractError(f"{name}: source binding is {binding[name]}, not {name}")
    for name in REQUIRED:
        if name not in inner:
            raise InterfaceContractError(f"missing critical generated boundary: {name}")
    if inner["clk_i"] != ("input", 1) or inner["rst_ni"] != ("input", 1):
        raise InterfaceContractError("clock/reset must be single-bit inputs")
    return {
        "schema_version": 1,
        "evidence": "generated_source_port_binding_consistency_only",
        "ports_compared": len(inner),
        "declared_port_bits_compared": sum(width for _, width in inner.values()),
        "critical_boundaries_present": list(REQUIRED),
        "compiler_elaboration_proven": False,
        "internal_floonoc_routes_proven": False,
        "runtime_axi_transactions_proven": False,
    }


def check(root: Path = ROOT) -> dict:
    root = root.resolve()
    wrapper = (root / WRAPPER).read_bytes()
    core = (root / CORE).read_bytes()
    result = verify(wrapper.decode("utf-8"), core.decode("utf-8"))
    result["source_sha256"] = {
        WRAPPER.as_posix(): hashlib.sha256(wrapper).hexdigest(),
        CORE.as_posix(): hashlib.sha256(core).hexdigest(),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = check(args.root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"Generated SuperNoC interface: {report['ports_compared']} source port "
          f"bindings / {report['declared_port_bits_compared']} declared bits match; "
          "no elaborated or runtime proof claimed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
