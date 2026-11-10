#!/usr/bin/env python3
"""Source-selected provenance for real compiler/elaboration adapters.

This is an attestation of the exact Bender-resolved *inputs*, not evidence
that any port is connected correctly or that a transfer was observed.
Do not create a second IP, topology or interface configuration registry.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml


def selected(root: Path, profile: str) -> dict:
    root = Path(root).resolve()
    if not isinstance(profile, str) or not profile or "/" in profile or ".." in profile:
        raise ValueError("invalid regression profile")
    config = yaml.safe_load((root / "config/regression.yaml").read_text())
    test = config.get("tests", {}).get(profile)
    if not isinstance(test, dict) or not isinstance(test.get("top"), str):
        raise ValueError(f"unknown or non-elaboratable profile: {profile}")
    folder = root / ".tools/regression" / profile
    source_list, plan_file = folder / "sources.f", folder / "plan.json"
    if not source_list.is_file() or not plan_file.is_file():
        raise ValueError(f"{profile}: missing original resolved filelist/plan")
    plan = json.loads(plan_file.read_text())
    if (plan.get("target") != profile or plan.get("top") != test["top"]
            or not isinstance(plan.get("sources"), list) or not plan["sources"]
            or plan.get("source_target") != test.get("sources")):
        raise ValueError(f"{profile}: selected plan disagrees with registered source/top")
    seen = set()
    sources = {}
    for raw in plan["sources"]:
        if not isinstance(raw, str) or not raw:
            raise ValueError("invalid resolved RTL source")
        path = Path(raw)
        path = (path if path.is_absolute() else root / path).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"{profile}: selected source missing or outside repository: {raw}")
        rel = path.relative_to(root).as_posix()
        if rel in seen:
            raise ValueError(f"{profile}: duplicate selected RTL source: {rel}")
        seen.add(rel)
        sources[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    filelist_sha = hashlib.sha256(source_list.read_bytes()).hexdigest()
    identity_path = folder / "identity.json"
    if identity_path.is_file():
        identity = json.loads(identity_path.read_text())
        selection = identity.get("selection", {})
        if selection.get("filelist_sha256") != filelist_sha:
            raise ValueError(f"{profile}: selected identity/filelist SHA mismatch")
        if identity.get("legacy_target") != profile:
            raise ValueError(f"{profile}: canonical identity references different selected target")
    return {
        "schema_version": 1,
        "profile": profile,
        "top": test["top"],
        "filelist_sha256": filelist_sha,
        "plan_sha256": hashlib.sha256(plan_file.read_bytes()).hexdigest(),
        "selected_source_sha256": sources,
        "source_count": len(sources),
        "evidence": "original_selected_sources_not_elaborated_or_wired",
        "source_list": source_list,
    }


def public_fields(attestation: dict) -> dict:
    return {key:value for key,value in attestation.items() if key != "source_list"}


# Reviewable selected compiler-input snapshot. This is deliberately implemented
# beside selected(), so the runner and the slang probes share one provenance
# authority and one source-digest convention.
def _canonical_sha(value: dict) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")).hexdigest()


def _relative_checked(root: Path, raw: str) -> tuple[Path, str]:
    if not isinstance(raw, str) or not raw:
        raise ValueError("missing selected source path")
    given = Path(raw)
    if given.is_symlink():
        raise ValueError("selected source is a symlink: " + raw)
    path = (given if given.is_absolute() else root / given).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("selected source outside checkout or missing: " + raw)
    return path, path.relative_to(root).as_posix()


def archive_selected_filelist(root: Path, profile: str, definition: dict,
                              plan: dict, filelist: Path, *, directory: Path | None = None) -> dict:
    """Freeze the *actual* resolved Bender sources, defines and generated files.

    This runs after the variant substitution and before ANY simulator command.
    Contents are copied beneath the existing per-test artifact directory;
    third-party RTL is represented by hashes and pinned source locations, not
    duplicated. There is no claim of successful elaboration or a valid transfer.
    """
    import re
    import shlex
    root = Path(root).resolve()
    is_canonical_run = directory is not None
    if not isinstance(profile, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", profile):
        raise ValueError("invalid selected test profile")
    folder = Path(directory) if directory is not None else root / ".tools/regression" / profile
    if directory is not None:
        try:
            from .run_workspace import verify_run
        except ImportError:
            from run_workspace import verify_run
        verify_run(folder, plan["identity"])
        if not folder.is_relative_to(root / ".tools/runs"):
            raise ValueError("canonical artifact directory outside selected run root")
    filelist = Path(filelist)
    if filelist.resolve() != (folder / "sources.f").resolve() or filelist.is_symlink():
        raise ValueError("selected source filelist is not target-owned")
    if (plan.get("target") != profile
            or plan.get("source_target") != definition.get("sources")
            or plan.get("top") != definition.get("top")
            or plan.get("engine") != definition.get("engine")):
        raise ValueError("selected compiler inputs disagree with regression target")
    expected = (["+incdir+" + item for item in plan.get("includes", [])]
                + ["+define+" + item for item in plan.get("defines", [])]
                + plan["sources"])
    if shlex.split(filelist.read_text()) != expected:
        raise ValueError("selected Bender filelist differs from actual compiled plan")
    filelist_sha = hashlib.sha256(filelist.read_bytes()).hexdigest()
    identity = plan.get("identity")
    if (not isinstance(identity, dict)
            or identity.get("legacy_target") != profile
            or identity.get("selection", {}).get("filelist_sha256") != filelist_sha):
        raise ValueError("selected RTL filelist disagrees with canonical test identity")
    selected_sources = {}
    for raw in plan["sources"]:
        path, rel = _relative_checked(root, raw)
        if rel in selected_sources:
            raise ValueError("duplicate selected RTL file: " + rel)
        selected_sources[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    # For structural NoC compile/lint, the simulator uses one filelist per
    # network, not sources.f. Include those exact source packages and top
    # modules in the attested closure and archive their separate filelists.
    network_sets = {}
    for network, entry in sorted(plan.get("selected_networks", {}).items()):
        if (not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", network)
                or not isinstance(entry, dict) or set(entry) != {"top", "filelist"}
                or not isinstance(entry["top"], str)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", entry["top"])):
            raise ValueError("invalid selected NoC compile target")
        network_file = folder / (network + ".f")
        if (Path(entry["filelist"]).resolve() != network_file.resolve()
                or network_file.is_symlink() or not network_file.is_file()):
            raise ValueError("selected NoC filelist is missing or foreign")
        tokens = shlex.split(network_file.read_text())
        if tokens[:len(expected)] != expected or len(tokens) != len(expected) + 2:
            raise ValueError("network compiler filelist differs from selected base sources")
        extras = []
        for raw in tokens[len(expected):]:
            path, rel = _relative_checked(root, raw)
            extras.append(rel)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if rel in selected_sources and selected_sources[rel] != digest:
                raise ValueError("conflicting selected NoC RTL: " + rel)
            selected_sources[rel] = digest
        network_sets[network] = {
            "top": entry["top"],
            "source_files": extras,
            "filelist_sha256": hashlib.sha256(network_file.read_bytes()).hexdigest(),
        }
    if not selected_sources:
        raise ValueError("empty selected RTL closure")

    # Match the existing Verilator adapter's include-header fingerprint rule:
    # every .svh/.vh beneath each selected include directory contributes.
    # This is deliberately a conservative *header inventory*, not a claim of
    # true preprocessor expansion or elaborated connectivity.
    header_sources = {}
    for raw in plan.get("includes", []):
        directory = Path(raw)
        if directory.is_symlink():
            raise ValueError("unsafe selected include directory: " + raw)
        directory = (directory if directory.is_absolute() else root / directory).resolve()
        if not directory.is_relative_to(root) or not directory.is_dir():
            raise ValueError("missing/outside selected include directory: " + raw)
        for header in sorted(directory.rglob("*")):
            if header.is_file() and header.suffix in (".svh", ".vh"):
                path, rel = _relative_checked(root, str(header))
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if rel in header_sources and header_sources[rel] != digest:
                    raise ValueError("conflicting selected include header: " + rel)
                header_sources[rel] = digest

    selected_top = None
    if plan.get("top") in ("full_chip_tb", "full_chip_dma_tb"):
        matching = [p for p in selected_sources if p.endswith("/soc_top.sv")]
        if len(matching) != 1:
            raise ValueError("expected exactly one actually selected SoC RTL top")
        selected_top = matching[0]

    # Include generated runtime collateral (ROM/FLASH/CSR and variant metadata)
    # that may be consumed indirectly through plusargs or compiler includes.
    # No run logs or third-party vendor trees are copied to this small archive.
    generated = {}
    for rel, sha in {**selected_sources, **header_sources}.items():
        if rel.startswith("gen/") or rel.startswith(
                folder.relative_to(root).as_posix() + "/"):
            generated[rel] = sha
    extensions = {".sv", ".svh", ".v", ".vh", ".json", ".yaml", ".yml",
                  ".hex", ".mem", ".bin", ".elf"}
    for subdir in ("variant", "boot", "memory", "csr", "ddr", "noc"):
        directory = folder / subdir
        if not directory.exists():
            continue
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("unsafe generated collateral directory: " + subdir)
        for child in directory.rglob("*"):
            if child.is_symlink():
                raise ValueError("unsafe generated collateral symlink: " + str(child))
            if child.is_file() and child.suffix.lower() in extensions:
                path, rel = _relative_checked(root, str(child))
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if rel in generated and generated[rel] != digest:
                    raise ValueError("generated source changed during capture: " + rel)
                generated[rel] = digest

    # The fingerprint is stable across run IDs, scratch directory ordering
    # and Python dict ordering; the source paths are checkout-relative.
    selection = {
        "engine": plan["engine"], "top": plan.get("top"),
        "source_target": plan["source_target"],
        "firmware_mode": plan.get("firmware_mode"),
        "includes": list(plan.get("includes", [])),
        "defines": list(plan.get("defines", [])),
        "args": list(plan.get("args", [])),
        "source_sha256": dict(sorted(selected_sources.items())),
        "include_headers_sha256": dict(sorted(header_sources.items())),
        "filelist_sha256": filelist_sha,
        "network_filelists": network_sets,
        "config_sha256": identity.get("config_sha256"),
        "generated_sha256": dict(sorted(generated.items())),
    }
    build_sha = _canonical_sha(selection)
    archive_rel = f"{folder.relative_to(root).as_posix()}/selected-rtl/{build_sha[:20]}"
    archive_root = root / archive_rel
    if archive_root.exists():
        raise ValueError("selected compiler-input archive already exists")
    archive_root.mkdir(parents=True)
    (archive_root / "sources.f").write_bytes(filelist.read_bytes())
    for network in sorted(network_sets):
        (archive_root / (network + ".f")).write_bytes(
            (folder / (network + ".f")).read_bytes())
    for rel, expected_sha in sorted(generated.items()):
        path, _ = _relative_checked(root, rel)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected_sha:
            raise ValueError("generated RTL changed while archiving: " + rel)
        destination = archive_root / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)

    document = {
        "schema_version": 1,
        "profile": profile,
        "compiled_top": plan.get("top"),
        "selected_soc_top": selected_top,
        "definition_sha256": _canonical_sha(definition),
        "compiler_input_sha256": build_sha,
        "filelist_sha256": filelist_sha,
        "source_count": len(selected_sources),
        "source_sha256": selection["source_sha256"],
        "include_headers_sha256": selection["include_headers_sha256"],
        "network_filelists": network_sets,
        "generated_sha256": selection["generated_sha256"],
        "includes": selection["includes"],
        "defines": selection["defines"],
        "args": selection["args"],
        "config_sha256": selection["config_sha256"],
        "archive": archive_rel,
        "identity_sha256": identity["identity_sha256"],
        "evidence": "selected_filelist_and_copied_generated_inputs_not_elaborated_or_observed",
    }
    document["manifest_sha256"] = _canonical_sha(document)
    (folder / "selected-rtl-manifest.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n")
    verify_selected_archive(root, profile, definition, directory=folder if is_canonical_run else None)
    return document


def verify_selected_archive(root: Path, profile: str, definition: dict, *, directory: Path | None = None) -> dict:
    """Fail closed on stale, foreign, missing or tampered source/artifact bytes."""
    root = Path(root).resolve()
    folder = Path(directory) if directory is not None else root / ".tools/regression" / profile
    if directory is not None:
        try:
            from .run_workspace import verify_run
        except ImportError:
            from run_workspace import verify_run
        try:
            from .test_identity import load
        except ImportError:
            from test_identity import load
        verify_run(folder, load(folder / "identity.json", target=profile))
        if not folder.is_relative_to(root / ".tools/runs"):
            raise ValueError("canonical artifact directory outside selected run root")
    path = folder / "selected-rtl-manifest.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("selected compiler-input manifest missing or unsafe")
    value = json.loads(path.read_text())
    digest = value.get("manifest_sha256")
    content = {k: v for k, v in value.items() if k != "manifest_sha256"}
    if (value.get("schema_version") != 1
            or value.get("profile") != profile
            or value.get("definition_sha256") != _canonical_sha(definition)
            or not isinstance(digest, str) or _canonical_sha(content) != digest):
        raise ValueError("foreign/stale/tampered selected RTL manifest")
    plan_file = folder / "plan.json"
    identity_file = folder / "identity.json"
    if (plan_file.is_symlink() or not plan_file.is_file()
            or identity_file.is_symlink() or not identity_file.is_file()):
        raise ValueError("selected plan/identity missing or unsafe")
    plan = json.loads(plan_file.read_text())
    identity = json.loads(identity_file.read_text())
    if (plan.get("target") != profile
            or plan.get("engine") != definition.get("engine")
            or plan.get("top") != value.get("compiled_top")
            or plan.get("source_target") != definition.get("sources")
            or not isinstance(plan.get("sources"), list)
            or set(plan["sources"]) != {
                str(root / path) for path in value["source_sha256"]
                if path not in {
                    extra for net in value.get("network_filelists", {}).values()
                    for extra in net.get("source_files", [])
                }
            }
            or len(plan["sources"]) != len(set(plan["sources"]))
            or plan.get("includes", []) != value.get("includes")
            or plan.get("defines", []) != value.get("defines")
            or plan.get("args", []) != value.get("args")
            or identity.get("identity_sha256") != value.get("identity_sha256")
            or identity.get("config_sha256") != value.get("config_sha256")
            or identity.get("selection", {}).get("filelist_sha256")
               != value.get("filelist_sha256")):
        raise ValueError("selected plan/identity differs from recorded compiler inputs")
    declared_networks = plan.get("selected_networks", {})
    if set(declared_networks) != set(value.get("network_filelists", {})):
        raise ValueError("selected NoC network selection changed since archive")
    for name, info in value.get("network_filelists", {}).items():
        if declared_networks[name] != {
                "filelist": str(folder / (name + ".f")), "top": info["top"]}:
            raise ValueError("selected NoC compiler top/plan mismatch")
    source_list = folder / "sources.f"
    if (source_list.is_symlink() or not source_list.is_file()
            or hashlib.sha256(source_list.read_bytes()).hexdigest()
            != value.get("filelist_sha256")):
        raise ValueError("selected RTL filelist changed since archive")
    import shlex
    expected_tokens = (
        ["+incdir+" + raw for raw in plan.get("includes", [])]
        + ["+define+" + raw for raw in plan.get("defines", [])]
        + plan["sources"])
    if shlex.split(source_list.read_text()) != expected_tokens:
        raise ValueError("selected compiler source order/flags differ from runner plan")
    expected_archive = (f"{folder.relative_to(root).as_posix()}/selected-rtl/"
                        + value["compiler_input_sha256"][:20])
    if value.get("archive") != expected_archive:
        raise ValueError("unsafe selected RTL archive location")
    archive = root / expected_archive
    if archive.is_symlink() or not archive.is_dir():
        raise ValueError("selected RTL archive is unavailable")
    archived_list = archive / "sources.f"
    if (archived_list.is_symlink() or not archived_list.is_file()
            or archived_list.read_bytes() != source_list.read_bytes()):
        raise ValueError("archived selected Bender filelist mismatch")
    # Every selected NoC top is compiled from its own archived filelist.
    # Match both archived bytes and the source-side variant SHA.
    for name, info in value.get("network_filelists", {}).items():
        original = folder / (name + ".f")
        archived = archive / (name + ".f")
        if (original.is_symlink() or archived.is_symlink()
                or not original.is_file() or not archived.is_file()
                or hashlib.sha256(original.read_bytes()).hexdigest()
                != info["filelist_sha256"]
                or archived.read_bytes() != original.read_bytes()):
            raise ValueError("selected NoC filelist changed since archive")
    for rel, expected_sha in value.get("include_headers_sha256", {}).items():
        source, _ = _relative_checked(root, rel)
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected_sha:
            raise ValueError("selected compiler include modified since capture: " + rel)
    for rel, expected_sha in value["source_sha256"].items():
        source, _ = _relative_checked(root, rel)
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected_sha:
            raise ValueError("selected compiler RTL modified since capture: " + rel)
    for rel, expected_sha in value["generated_sha256"].items():
        source, _ = _relative_checked(root, rel)
        copy, _ = _relative_checked(root, str(archive / rel))
        if (hashlib.sha256(source.read_bytes()).hexdigest() != expected_sha
                or hashlib.sha256(copy.read_bytes()).hexdigest() != expected_sha):
            raise ValueError("archived generated RTL/collateral mismatch: " + rel)
    return value


def explain_target(root: Path, name: str, definition: dict,
                   regression_config: dict) -> dict:
    """Read-only reviewer entry point; never infer uncompiled RTL is active."""
    from stimulus_catalog import load as load_stimuli
    from runtime_contract import validate_migration_inventory
    root = Path(root).resolve()
    stimulus = load_stimuli(regression_config)[name]
    adoption = validate_migration_inventory(regression_config, root=root)[name]
    mode = definition.get("firmware_mode")
    hint = (f".tools/regression/{name}/variant/soc_top.sv" if mode
            else "gen/chip/soc_top.sv" if definition.get("top") in
            ("full_chip_tb", "full_chip_dma_tb") else None)
    detail = {
        "target": name,
        "engine": definition["engine"],
        "top": definition.get("top"),
        "sources_target": definition["sources"],
        "bender_targets": definition.get("bender_targets", []),
        "firmware_mode": mode,
        "logical_test": definition.get("logical_test"),
        "driver": {"python_module": definition.get("module"),
                   "test_dir": definition.get("test_dir"),
                   "source": stimulus["driver_source"],
                   "execution": stimulus["execution"],
                   "runtime_adapter": adoption},
        "scenario_authoring_source": definition.get("flow_plan"),
        "declared_init_run_check": (definition.get("report") or {}).get(
            "flow", {}).get("required_steps"),
        "expected_soc_top_path_hint_not_verified": hint,
        "selected_source_status": "declared_only_no_resolved_filelist",
        "resolve_without_simulation": f"python3 tools/regress.py {name} --stage files",
        "run_directory": f".tools/regression/{name}",
    }
    selected_manifest = root / ".tools/regression" / name / "selected-rtl-manifest.json"
    if selected_manifest.is_file() or selected_manifest.is_symlink():
        snapshot = verify_selected_archive(root, name, definition)
        detail["selected_source_status"] = (
            "verified_selected_filelist_and_generated_bytes_not_elaborated")
        detail["selected_inputs"] = {
            "manifest": f".tools/regression/{name}/selected-rtl-manifest.json",
            "archive": snapshot["archive"],
            "compiler_input_sha256": snapshot["compiler_input_sha256"],
            "source_count": snapshot["source_count"],
            "compiled_soc_top": snapshot["selected_soc_top"],
            "selected_generated_files": sorted(snapshot["generated_sha256"]),
            "network_filelists": snapshot.get("network_filelists", {}),
            "include_header_count": len(snapshot.get("include_headers_sha256", {})),
        }
    return detail
