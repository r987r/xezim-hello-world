"""Fail-closed audit of compiler CST named-port bindings.

This audit flags missing/malformed bindings before agents do actual slang-netlist
bit-level elaboration. It NEVER upgrades CST evidence to proven wiring.
"""
import re

SIMPLE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*(\[[^]]+\])?$")


def audit(parsed, required_bindings):
    """Return a list of diagnostic rows for required module.instance.port paths.

    parsed: output from tools/rtl_instance_parser.py (possibly module list).
    required_bindings: {(module_name, instance_name): {"clk_i","rst_ni",...}}
    """
    modules = parsed.get("modules") if isinstance(parsed, dict) else parsed
    if not isinstance(modules, list) or not isinstance(required_bindings, dict):
        raise ValueError("invalid parser inventory or required port specification")
    index = {}
    for module in modules:
        for inst in module.get("instances", []):
            key = module["name"], inst["name"]
            if key in index:
                raise ValueError(f"ambiguous syntax-only instance: {key}")
            index[key] = inst
    findings = []
    for key, required in sorted(required_bindings.items()):
        if not isinstance(key, tuple) or len(key) != 2 or not isinstance(required, (list,tuple,set)):
            raise ValueError("invalid required binding")
        inst = index.get(key)
        if inst is None:
            findings.append({"kind": "missing_instance", "instance": key})
            continue
        ports = inst.get("ports", [])
        seen = {}
        for p in ports:
            name = p.get("port")
            if name in seen:
                raise ValueError("duplicate named port in parsed source")
            seen[name] = p
        for name in sorted(required):
            if name not in seen:
                findings.append({"kind": "missing_required_port", "instance": key,
                                 "port": name})
            elif not str(seen[name].get("expression", "")).strip():
                findings.append({"kind": "unconnected_required_port", "instance": key,
                                 "port": name})
    return {"evidence": "slang_cst_syntax_only_not_bit_level",
            "bindings_examined": sum(len(x) for x in required_bindings.values()),
            "findings": findings, "pass": not findings}


def require_clean(report):
    if report["findings"]:
        raise ValueError(f"missing parsed RTL port bindings: {report['findings']}")
    return report
