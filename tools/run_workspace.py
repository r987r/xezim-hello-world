"""One safe canonical run-directory allocator built on existing test_identity.

This is a migration foundation for #139. Existing regress.py and legacy
scratch paths are intentionally unchanged until each producer is migrated.
Never mirror or relabel archived output, and never infer PASS from a path.
"""
from __future__ import annotations

import os
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from .test_identity import IdentityError, relative_path, save, validate
except ImportError:
    from test_identity import IdentityError, relative_path, save, validate


def _existing_ancestors_safe(path: Path) -> None:
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            raise IdentityError("symlink ancestor in canonical run workspace")


def reserve_run(root: Path, identity: dict, *, plan: dict | None = None) -> Path:
    """Atomically reserve a new immutable run ID; fail on duplicates or aliases.

    Caller must provide an existing immutable identity from test_identity.selected.
    No creation of another run ID or source of configuration names occurs here.
    """
    identity = validate(identity, plan=plan)
    root = Path(root)
    if not root.is_absolute() or root.is_symlink():
        raise IdentityError("canonical root must be absolute and not a symlink")
    _existing_ancestors_safe(root)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / relative_path(identity)
    if directory.is_symlink():
        raise IdentityError("canonical run path may not be a symlink")
    _existing_ancestors_safe(directory.parent)
    directory.parent.mkdir(parents=True, exist_ok=True)
    # mkdir is exclusive and atomic. A retry/second writer must use a new run_id.
    try:
        directory.mkdir()
    except FileExistsError as exc:
        raise IdentityError("duplicate canonical run identity or concurrent writer") from exc
    try:
        save(directory / "identity.json", identity)
    except Exception:
        # Ownership was just acquired; no historical result is being removed.
        (directory / "identity.json").unlink(missing_ok=True)
        directory.rmdir()
        raise
    return directory


def verify_run(directory: Path, identity: dict, *, plan: dict | None = None) -> Path:
    """Verify a *real* canonical workspace without creating or modifying it."""
    identity = validate(identity, plan=plan)
    directory = Path(directory)
    expected = relative_path(identity)
    if not directory.is_dir() or directory.is_symlink():
        raise IdentityError("canonical run directory missing or unsafe")
    _existing_ancestors_safe(directory)
    if tuple(directory.parts[-4:]) != expected.parts:
        raise IdentityError("run folder does not match immutable selected identity")
    try:
        from .test_identity import load
    except ImportError:
        from test_identity import load
    recorded = load(directory / "identity.json",
                    target=identity["legacy_target"], plan=plan)
    if recorded != identity:
        raise IdentityError("stored run identity differs from selected run")
    return directory


def canonical_artifact(directory: Path, name: str) -> Path:
    """Guard relative report paths; never create aliases or legacy mirrors."""
    directory = Path(directory)
    if (not directory.is_dir() or directory.is_symlink()
            or not isinstance(name, str) or not name or "\\" in name):
        raise IdentityError("invalid canonical artifact directory or name")
    _existing_ancestors_safe(directory)
    relative = Path(name)
    if relative.is_absolute() or any(p in (".", "..") for p in relative.parts):
        raise IdentityError("artifact must be a safe workspace-relative filename")
    target = directory / relative
    if target.exists() or target.is_symlink():
        raise IdentityError("refusing to overwrite canonical run artifact")
    _existing_ancestors_safe(target.parent)
    # Parent directories remain explicitly owned by this run.
    target.parent.mkdir(parents=True, exist_ok=True)
    return target

def verify_artifact_inventory(directory: Path, identity: dict, names: list[str],
                              *, plan: dict | None = None) -> dict:
    """Record exact bytes of an *already written* canonical run, never a PASS.

    A partial, escaped, unbound, or duplicated artifact set fails closed.
    Does not migrate legacy paths and does not mirror files.
    """
    directory = verify_run(directory, identity, plan=plan)
    if (not isinstance(names, list) or not names
            or len(set(names)) != len(names)):
        raise IdentityError("missing or duplicate canonical artifact names")
    records = []
    for name in names:
        if not isinstance(name, str) or not name or "\\" in name:
            raise IdentityError("invalid canonical artifact name")
        relative = Path(name)
        if (relative.is_absolute() or ".." in relative.parts
                or "." in relative.parts or len(relative.parts) < 1):
            raise IdentityError("invalid canonical artifact path")
        path = directory / relative
        _existing_ancestors_safe(path)
        if not path.is_file() or path.is_symlink():
            raise IdentityError("missing canonical run artifact: " + name)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append({"path": relative.as_posix(), "sha256": digest,
                        "bytes": path.stat().st_size})
    return {"schema_version": 1, "identity_sha256": identity["identity_sha256"],
            "status": "artifact_bytes_verified_not_execution_proof",
            "artifacts": sorted(records, key=lambda item: item["path"])}

def require_completed_xezim_run(root: Path, target: str, plan: dict) -> dict:
    """Fail closed unless a real selected Xezim producer wrote its sole PASS.

    This verifies completed runner evidence; it does not turn Xezim stdout
    into AXI/CSR/coverage evidence. The existing source provenance validator
    independently verifies original inputs and generated collateral.
    """
    try:
        from .test_identity import load
        from .selected_rtl_provenance import verify_selected_archive
    except ImportError:
        from test_identity import load
        from selected_rtl_provenance import verify_selected_archive
    root = Path(root).absolute()
    if not root.is_dir() or root.is_symlink():
        raise IdentityError("missing canonical Xezim run root")
    _existing_ancestors_safe(root)
    if plan.get("engine") != "xezim" or target not in ("smoke", "sram"):
        raise IdentityError("unexpected canonical Xezim producer selection")
    matches = []
    for identity_file in root.rglob("identity.json"):
        try:
            recorded = load(identity_file, target=target, plan=plan)
        except IdentityError:
            continue
        verify_run(identity_file.parent, recorded, plan=plan)
        matches.append((identity_file.parent, recorded))
    if len(matches) != 1:
        raise IdentityError("expected exactly one real canonical producer run")
    folder, identity = matches[0]
    expected_log = f"{target}.log"
    required = ["plan.json", "sources.f", "selected-rtl-manifest.json",
                "result.json", "runner-events.json", expected_log]
    verify_artifact_inventory(folder, identity, required, plan=plan)
    try:
        record = json.loads((folder / "result.json").read_text())
        resolved = json.loads((folder / "plan.json").read_text())
    except (OSError, ValueError) as exc:
        raise IdentityError("missing or invalid simulator result/plan") from exc
    if (record.get("target") != target or record.get("passed") is not True
            or record.get("stage") != "all"
            or record.get("identity_sha256") != identity["identity_sha256"]
            or record.get("canonical_id") != relative_path(identity).as_posix()
            or resolved.get("identity") != identity
            or len(record.get("results", [])) != 1
            or record["results"][0].get("name") != target
            or record["results"][0].get("passed") is not True
            or record["results"][0].get("exit_code") != 0):
        raise IdentityError("canonical run lacks completed selected Xezim PASS")
    if plan.get("pass") not in (folder / expected_log).read_text(errors="replace"):
        raise IdentityError("canonical simulator transcript missing original PASS marker")
    if root.name != 'runs' or root.parent.name != '.tools':
        raise IdentityError('canonical Xezim root is not the configured run root')
    verify_selected_archive(root.parent.parent, target, plan, directory=folder)
    return {"target": target, "canonical_id": relative_path(identity).as_posix(),
            "status": "runner_completed_xezim_no_protocol_coverage_claim"}


def require_completed_cocotb_run(root: Path, target: str, plan: dict) -> dict:
    """Verify actual real Cocotb/Verilator producer and original selected inputs.

    Only the first reviewed standalone iDMA producer is eligible. Do not
    infer protocol/AXI proof from a report directory, print marker, or path.
    Later migration of chip-level targets requires their own passive monitors.
    """
    try:
        from .test_identity import load
        from .selected_rtl_provenance import verify_selected_archive
    except ImportError:
        from test_identity import load
        from selected_rtl_provenance import verify_selected_archive
    root = Path(root).absolute()
    if not root.is_dir() or root.is_symlink():
        raise IdentityError("missing canonical Cocotb run root")
    _existing_ancestors_safe(root)
    if (target != "dma-rtl" or plan.get("engine") != "cocotb-verilator"
            or plan.get("top") != "dma_tb" or plan.get("module") != "dv.dma.test_dma"
            or root.name != "runs" or root.parent.name != ".tools"):
        raise IdentityError("unreviewed canonical Cocotb producer selection")
    matches = []
    for path in root.rglob("identity.json"):
        try:
            identity = load(path, target=target, plan=plan)
        except IdentityError:
            continue
        directory = verify_run(path.parent, identity, plan=plan)
        matches.append((directory, identity))
    if len(matches) != 1:
        raise IdentityError("expected exactly one real canonical Cocotb producer")
    directory, identity = matches[0]
    required = ["plan.json", "sources.f", "selected-rtl-manifest.json",
                "result.json", "runner-events.json", "dma-rtl.log",
                "simulation.log", "results.xml"]
    verify_artifact_inventory(directory, identity, required, plan=plan)
    try:
        selected_plan = json.loads((directory / "plan.json").read_text())
        result = json.loads((directory / "result.json").read_text())
        dispatch = json.loads((directory / "runner-events.json").read_text())
        tests = ET.parse(directory / "results.xml").findall(".//testcase")
    except (OSError, ValueError, ET.ParseError) as error:
        raise IdentityError("invalid original Cocotb completion evidence") from error
    if (selected_plan.get("identity") != identity
            or selected_plan.get("target") != target
            or selected_plan.get("top") != plan["top"]
            or result.get("target") != target or result.get("passed") is not True
            or result.get("stage") != "all"
            or result.get("identity_sha256") != identity["identity_sha256"]
            or result.get("canonical_id") != relative_path(identity).as_posix()
            or len(result.get("results", [])) != 1
            or result["results"][0].get("name") != target
            or result["results"][0].get("passed") is not True
            or result["results"][0].get("exit_code") != 0
            or not tests
            or any(any(case.find(tag) is not None
                       for tag in ("failure", "error", "skipped")) for case in tests)
            or not isinstance(dispatch.get("events"), list)
            or not dispatch["events"]):
        raise IdentityError("canonical Cocotb run lacks original completed PASS")
    if not any(event.get("status") == "completed" and event.get("passed") is True
               for event in dispatch["events"]):
        raise IdentityError("missing original runner success event")
    if (plan.get("pass") not in
            (directory / "simulation.log").read_text(errors="replace")):
        raise IdentityError("original simulator transcript missing declared PASS")
    verify_selected_archive(root.parent.parent, target, plan, directory=directory)
    return {"target": target, "canonical_id": relative_path(identity).as_posix(),
            "status": "real_cocotb_xml_and_runner_pass_without_fabric_axi_coverage"}
