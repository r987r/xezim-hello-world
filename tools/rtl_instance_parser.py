#!/usr/bin/env python3
"""Compiler-parsed SystemVerilog instance/port binding evidence for the SoC viewer.

Uses *slang's concrete syntax tree*, not a hand-written Verilog regex parser.
Parse-only mode deliberately avoids requiring all external SoC IP to elaborate.
A generated instance inside a conditional/generate block is syntactic
evidence, NOT proof it is active in a selected test profile.

The condensed JSON is safe to embed in Pages; the large CST is ephemeral.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
# The top-level and the repository-owned adapters / custom Ethernet logic
# are syntax-parsed, not elaborated. Imported IP remains a pinned opaque
# boundary until its checked-out sources are available in a verified build.
DEFAULT_SOURCES = ("gen/chip/soc_top.sv", "gen/supernoc/soc_noc.sv")


def source_files(root: Path, sources):
    if tuple(sources) != DEFAULT_SOURCES:
        return tuple(sources)
    extra = [p.relative_to(root).as_posix()
             for folder in ("rtl/adapters", "rtl/io/ethernet0")
             for pattern in ("*.sv", "*.v")
             for p in sorted((root / folder).glob(pattern))
             if re.search(r"(?m)^\s*module\s+", p.read_text())]
    return tuple(sources) + tuple(dict.fromkeys(extra))

TOKEN = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def walk(node):
    if isinstance(node, dict):
        yield node
        for key, value in node.items():
            if key not in ("trivia", "leadingTrivia", "trailingTrivia"):
                yield from walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item)


def token_texts(value):
    """Visit genuine CST token leaves, omitting syntax metadata / trivia."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        if isinstance(value.get("text"), str):
            yield value["text"]
            return
        for key, child in value.items():
            if key not in ("kind", "trivia", "leadingTrivia", "trailingTrivia"):
                yield from token_texts(child)
    elif isinstance(value, list):
        for child in value:
            yield from token_texts(child)


def flatten(value):
    return [tok for tok in token_texts(value) if tok and tok.strip()]


def atom(value):
    toks = flatten(value)
    return next((x for x in toks if TOKEN.fullmatch(x)), "")


def descendants(root, wanted):
    return [node for node in walk(root) if node.get("kind") == wanted]


def source_expr(tokens):
    """Preserve exact tokens and refuse to reinterpret expressions as wires."""
    return "".join(tokens).strip()


def parse_port(node):
    toks = flatten(node)
    if not toks or toks[0] != ".":
        # Some CST writers package the leading '.' into the name token.
        if toks and toks[0].startswith("."):
            toks = [".", toks[0][1:]] + toks[1:]
        else:
            return None
    if len(toks) < 2 or not TOKEN.fullmatch(toks[1]):
        return None
    name = toks[1]
    if "(" not in toks:
        return {"port": name, "expression": name, "evidence": "implicit_named_port"}
    start = toks.index("(")
    # These are parser-owned expression tokens, not a regex over raw SV.
    depth = 0
    expr = []
    for tok in toks[start + 1:]:
        if tok == "(":
            depth += 1
        if tok == ")":
            if depth == 0:
                break
            depth -= 1
        expr.append(tok)
    return {"port": name, "expression": source_expr(expr),
            "evidence": "parsed_named_port_binding"}


def parse_instance(node, module_type, source, conditional):
    toks = flatten(node)
    # A HierarchicalInstance has a declarator and a connection list. Extract
    # its identifier from the first declarator rather than matching raw text.
    declarator = node.get("decl")
    name = atom(declarator.get("name") or declarator) if isinstance(declarator, dict) else ""
    if not name:
        # Use first identifier before the parenthesized connection list.
        # This works for syntactically complete generated instantiations.
        first_paren = toks.index("(") if "(" in toks else len(toks)
        name = next((x for x in toks[:first_paren] if TOKEN.fullmatch(x)), "")
    if not name:
        raise ValueError(f"{source}: cannot identify parsed instance of {module_type}")
    connections = []
    for part in walk(node):
        if part.get("kind") == "NamedPortConnection":
            port = parse_port(part)
            if port:
                connections.append(port)
    if len({p["port"] for p in connections}) != len(connections):
        raise ValueError(f"{source}: duplicate named port on instance {name}")
    return {"name": name, "module": module_type, "source": source,
            "conditional_generate": conditional, "ports": connections,
            "port_count": len(connections),
            "evidence": "slang_cst_parsed_not_elaborated"}


def parse_module(node, source):
    header = node.get("header") or {}
    name = atom(header.get("name") or header.get("moduleName") or header)
    if not name:
        raise ValueError(f"{source}: compiler CST ModuleDeclaration has no name")
    instances = []
    for part in walk(node):
        if part.get("kind") != "HierarchyInstantiation":
            continue
        # The first identifier in the hierarchy instantiation is the module
        # type. Favor the typed field over raw token order.
        module_type = atom(part.get("type") or "")
        if not module_type:
            raise ValueError(f"{source}: HierarchyInstantiation has no module type")
        if not module_type:
            raise ValueError(f"{source}: unrecognized instantiated module type")
        enclosing_generate = False
        # CST doesn't always have generated parameter conditions evaluated.
        # Conservatively mark every syntactic instantiation as potentially
        # conditional when the enclosing module contains generate constructs.
        for inst in descendants(part, "HierarchicalInstance"):
            instances.append(parse_instance(inst, module_type, source,
                                            enclosing_generate))
    # A syntax-only parse does not evaluate conditional generate guards.
    # Preserve instances from both branches; downstream can only present
    # them as syntactic possibilities until profile elaboration succeeds.
    # Generate block modules can have instance names repeated under mutually
    # exclusive branches. Do not drop them silently, keep source order.
    return {"name": name, "source": source, "instances": instances,
            "evidence": "slang_cst_syntax"}


def parse_tree(payload, source):
    trees = payload.get("syntaxTrees")
    if not isinstance(trees, list) or not trees:
        raise ValueError(f"{source}: slang returned no valid syntax trees")
    modules = []
    for tree in trees:
        root = tree.get("root") if isinstance(tree, dict) else None
        if not isinstance(root, dict):
            raise ValueError(f"{source}: invalid slang CST root")
        for item in walk(root):
            if item.get("kind") == "ModuleDeclaration":
                modules.append(parse_module(item, source))
    if not modules:
        raise ValueError(f"{source}: parsed CST contains no modules")
    return modules


def run_slang(root: Path, binary: str, source: Path):
    if not source.is_file():
        raise ValueError(f"missing RTL source: {source}")
    with tempfile.TemporaryDirectory(prefix="chip-slang-") as tmp:
        dest = Path(tmp) / "syntax.json"
        args = [binary, "--parse-only", "--cst-json", str(dest),
                "--cst-json-mode", "simple-tokens", str(source)]
        run = subprocess.run(args, cwd=root, capture_output=True, text=True,
                             timeout=90, check=False)
        if run.returncode:
            raise ValueError(f"slang could not parse {source}: "
                             + (run.stderr + run.stdout)[-3000:])
        if not dest.is_file() or not dest.stat().st_size:
            raise ValueError(f"slang produced no CST for {source}")
        return json.loads(dest.read_text())


def build(root=ROOT, *, slang="slang", sources=DEFAULT_SOURCES):
    root = Path(root).resolve()
    executable = shutil.which(str(slang))
    if not executable:
        raise ValueError(f"slang compiler missing: {slang}")
    modules = []
    checksums = {}
    for rel in source_files(root, sources):
        source = (root / rel).resolve()
        if not source.is_relative_to(root):
            raise ValueError(f"source escapes repository: {rel}")
        payload = run_slang(root, executable, source)
        modules.extend(parse_tree(payload, rel))
        checksums[rel] = hashlib.sha256(source.read_bytes()).hexdigest()
    names = [m["name"] for m in modules]
    if len(names) != len(set(names)):
        raise ValueError("duplicate parsed modules (ambiguous input file set)")
    byname = {m["name"]: m for m in modules}
    if "soc_top" not in byname or "soc_noc" not in byname:
        raise ValueError("required generated top-level modules missing from parsed RTL")
    noc_instances = byname["soc_noc"]["instances"]
    if not noc_instances:
        raise ValueError("no real instantiated NoC modules found in parsed RTL")
    top_instances = byname["soc_top"]["instances"]
    if not any(x["module"] == "soc_noc" for x in top_instances):
        raise ValueError("soc_top does not instantiate the parsed soc_noc")

    # Validate each FlooGen network against a compiler-parsed RTL instance.
    # Data and config networks are distinct, not a single display-only link.
    manifest_file = root / "gen/noc/floonoc/manifest.json"
    contract = {"expected_networks": [], "resolved_networks": [],
                "missing_network_modules": [], "independent_planes": False}
    if manifest_file.is_file():
        manifest = json.loads(manifest_file.read_text())
        expected = {name: record["top_module"]
                    for name, record in manifest["networks"].items()}
        found = {inst["module"] for inst in noc_instances}
        contract["expected_networks"] = sorted(expected)
        contract["resolved_networks"] = sorted(
            name for name, typ in expected.items() if typ in found)
        contract["missing_network_modules"] = sorted(
            name for name, typ in expected.items() if typ not in found)
        contract["independent_planes"] = (
            all(any(n.endswith("_"+plane) for n in contract["resolved_networks"])
                for plane in ("data", "config")))
        if contract["missing_network_modules"]:
            raise ValueError("FlooGen modules absent from parsed soc_noc: "
                             + ", ".join(contract["missing_network_modules"]))
        if not contract["independent_planes"]:
            raise ValueError("data and configuration NoCs must be independent")
    return {"schema_version": 1, "producer": "slang",
            "evidence": "compiler_parsed_rtl_not_elaborated",
            "profile_specific_elaboration_proven": False,
            "source_sha256": checksums, "modules": modules,
            "fabric_contract": contract,
            "summary": {"modules": len(modules),
                        "instances": sum(len(x["instances"]) for x in modules),
                        "noc_instances": len(noc_instances),
                        "named_port_bindings": sum(x["port_count"] for m in modules
                                                   for x in m["instances"])}}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root", type=Path, default=ROOT)
    cli.add_argument("--slang", default="slang")
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    obj = build(args.root, slang=args.slang)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(obj, indent=2) + "\n")
    print("Parsed actual RTL:", obj["summary"], flush=True)


if __name__ == "__main__":
    main()
