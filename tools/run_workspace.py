"""One safe canonical run-directory allocator built on existing test_identity.

Migrated producers use one immutable workspace. Legacy producers retain their
existing paths until their consumers move. Never mirror or relabel archived
output, and never infer PASS from a path.
"""
from __future__ import annotations

import os
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from .ddr_split_workspace import eligible as uses_canonical_ddr_split
    from .ddr_split_workspace import eligible_combined
    from .test_identity import (IdentityError, bind_filelist, config_target, load, neutral_testname,
                                relative_path, save, simulator, slug, validate)
except ImportError:
    from ddr_split_workspace import eligible as uses_canonical_ddr_split
    from ddr_split_workspace import eligible_combined
    from test_identity import (IdentityError, bind_filelist, config_target, load, neutral_testname,
                               relative_path, save, simulator, slug, validate)


def uses_canonical_ethernet_workspace(name, test):
    """The two existing Ethernet consumers share the dynamic variant producer."""
    if (test.get('engine') != 'cocotb-verilator' or test.get('sources') != 'noc'
            or any(test.get(key) for key in ('memory_config', 'boot_relocate', 'flow_plan'))):
        return False
    actual = (test.get('firmware_mode'), test.get('top'), test.get('bender_targets'))
    return ((name == 'chip-ethernet'
             and actual == ('ethernet_mvp', 'full_chip_dma_tb', ['chip_boot', 'dma', 'chip_dma']))
            or (name == 'chip-ethernet-cpu'
                and actual == ('ethernet_cpu', 'full_chip_tb', ['chip_boot', 'dma'])))


def uses_canonical_cpu_firmware_workspace(name, test):
    """Only the existing CPU-DMA and two separately qualified PCIe cases."""
    mode = {'chip-cpu-dma': 'cpu_dma', 'chip-pcie-host': 'pcie_dma_host',
            'chip-pcie-outbound': 'pcie_outbound'}.get(name)
    return (mode is not None and test.get('firmware_mode') == mode
            and test.get('engine') == 'cocotb-verilator' and test.get('sources') == 'noc'
            and test.get('top') == 'full_chip_tb'
            and test.get('bender_targets') == ['chip_boot', 'dma']
            and not any(test.get(key) for key in ('memory_config', 'boot_relocate', 'flow_plan')))


def uses_canonical_scenario_workspace(name, test):
    """Move only the established CPU/BFM replay pair together."""
    if (test.get('engine') != 'cocotb-verilator' or test.get('sources') != 'noc'
            or not test.get('flow_plan')
            or any(test.get(key) for key in ('memory_config', 'boot_relocate'))):
        return False
    actual = (test.get('firmware_mode'), test.get('top'), test.get('bender_targets'))
    return ((name == 'chip-cpu-scenario'
             and actual == ('cpu_dma_scenario', 'full_chip_tb', ['chip_boot', 'dma']))
            or (name == 'chip-dma-scenario'
                and actual == ('scenario_bfm', 'full_chip_dma_tb', ['chip_boot', 'dma', 'chip_dma'])))


def uses_canonical_peakrdl_reset_workspace(name, test):
    """Only the existing source-selected full-chip CSR cold-boot proof."""
    return (name == 'chip-peakrdl-reset' and test.get('logical_test') == 'reset-ack-register-access'
            and test.get('firmware_mode') == 'peakrdl_reset'
            and test.get('engine') == 'cocotb-verilator' and test.get('sources') == 'noc'
            and test.get('top') == 'full_chip_tb' and test.get('bender_targets') == ['chip_boot']
            and not any(test.get(key) for key in ('memory_config', 'boot_relocate', 'flow_plan')))


def uses_canonical_generated_firmware_workspace(name, test):
    return (uses_canonical_ethernet_workspace(name, test)
            or uses_canonical_cpu_firmware_workspace(name, test)
            or uses_canonical_scenario_workspace(name, test)
            or uses_canonical_peakrdl_reset_workspace(name, test)
            or uses_canonical_ddr_split(name, test))


def uses_canonical_workspace(name, test, *, stage=None):
    """Select migrated families; combined source-only consumers retain their exact replay."""
    if stage in ('all', 'build', 'run') and eligible_combined(name, test):
        return True
    if name == 'dma-rtl':
        return True
    # The existing static SuperNoC runs share a compiled executable, but
    # their reports have independent identities and never use the build path.
    supernoc_logical_test = {
        'supernoc': 'axi-noc-routing',
        'supernoc-negative': 'axi-noc-route-errors',
        'supernoc-latency': 'axi-noc-latency-baseline',
    }.get(name)
    if (supernoc_logical_test is not None and test.get('logical_test') == supernoc_logical_test
            and test.get('engine') == 'cocotb-verilator'
            and test.get('sources') == 'noc' and test.get('top') == 'supernoc_tb'
            and test.get('bender_targets') == ['supernoc']
            and not any(test.get(key) for key in
                        ('memory_config', 'boot_relocate', 'firmware_mode', 'flow_plan'))):
        return True
    return (test.get('engine') in {'xezim', 'xezim-compile', 'verilator-lint'}
            # Only Xezim memory materialization has a migrated producer.
            and (test.get('sources') != 'memory' or test['engine'] == 'xezim')
            and (not test.get('memory_config') or test.get('sources') == 'memory')
            and not test.get('firmware_mode')
            and (not test.get('boot_relocate')
                 or (test['engine'] == 'xezim' and test.get('sources') == 'boot'))) or (
        # Static full-chip cases keep their source-keyed simulators. Firmware,
        # memory and scenario variants retain their existing consumers.
        test.get('engine') == 'cocotb-verilator' and test.get('sources') == 'noc'
        and not any(test.get(key) for key in ('memory_config', 'boot_relocate', 'firmware_mode'))
        and (
            (test.get('top') == 'full_chip_tb'
             and test.get('bender_targets') == ['chip_boot'])
            or (name == 'chip-dma' and test.get('logical_test') == 'dma-fabric-roundtrip'
                and test.get('top') == 'full_chip_dma_tb'
                and test.get('bender_targets') == ['chip_boot', 'dma', 'chip_dma']
                and not test.get('flow_plan'))
        )
    ) or uses_canonical_generated_firmware_workspace(name, test)


def _run_identity_files(checkout: Path, target: str, plan: dict) -> list[Path]:
    legacy = checkout / ".tools/regression" / target
    if legacy.exists() or legacy.is_symlink():
        raise IdentityError(f"legacy {target} mirror forbidden after canonical migration")
    parent = (checkout / ".tools/runs" / simulator(plan) / config_target(plan)
              / neutral_testname(plan["logical_test"]))
    _existing_ancestors_safe(parent)
    return sorted(parent.glob("*/identity.json"))


def snapshot_run_ids(checkout: Path, target: str, plan: dict) -> frozenset[str]:
    """Record earlier identities before a replay starts; no time/order guesses."""
    slug(target, "legacy target")
    if not uses_canonical_workspace(target, plan):
        raise IdentityError("run snapshot needs a canonical target")
    return frozenset(path.parent.name for path in
                     _run_identity_files(Path(checkout).resolve(), target, plan))


def selected_run_folder(checkout: Path, target: str, plan: dict, *,
                        stage=None, prior_run_ids=frozenset()) -> Path | None:
    """Resolve one selected workspace, optionally only one new invocation."""
    checkout = Path(checkout).resolve()
    slug(target, "legacy target")
    if not uses_canonical_workspace(target, plan):
        if prior_run_ids:
            raise IdentityError("run snapshot needs a canonical target")
        return checkout / ".tools/regression" / target
    candidates = [path for path in _run_identity_files(checkout, target, plan)
                  if path.parent.name not in prior_run_ids]
    if stage is not None:
        if stage not in ('files', 'build', 'run', 'all'):
            raise IdentityError("invalid selected run stage")
        scoped = []
        for file in candidates:
            stored = load(file, target=target, plan=plan)
            workspace = verify_run(file.parent, stored, plan=plan)
            plan_file = workspace / "plan.json"
            if plan_file.is_symlink():
                raise IdentityError("selected run plan symlink is forbidden")
            if not plan_file.is_file():
                continue  # No phase was dispatched for this reservation.
            snapshot = json.loads(plan_file.read_text())
            if not isinstance(snapshot, dict) or snapshot.get("identity") != stored:
                raise IdentityError("selected stage plan does not match run identity")
            if snapshot.get("stage") == stage:
                scoped.append(file)
        candidates = scoped
    if not candidates:
        return None
    if len(candidates) != 1:
        raise IdentityError(f"{target} requires exactly one selected canonical run")
    identity = load(candidates[0], target=target, plan=plan)
    return verify_run(candidates[0].parent, identity, plan=plan)


def _existing_ancestors_safe(path: Path) -> None:
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            raise IdentityError("symlink ancestor in canonical run workspace")


def _reserve_directory(root: Path, identity: dict, *, plan: dict | None) -> Path:
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
    return directory


def reserve_run(root: Path, identity: dict, *, plan: dict | None = None) -> Path:
    """Reserve an immutable workspace from an already selected identity."""
    directory = _reserve_directory(root, identity, plan=plan)
    try:
        save(directory / "identity.json", identity, exclusive=True)
    except Exception:
        # Ownership was just acquired; no historical result is being removed.
        (directory / "identity.json").unlink(missing_ok=True)
        directory.rmdir()
        raise
    return directory


def reserve_materialized_run(root: Path, identity: dict, materialize, *, plan=None):
    """Reserve once, generate in place, then expose only the final identity.

    Materialization writes the actual compiler filelist into the workspace.
    Failed preparation can retain diagnostics there, but an incomplete
    workspace has no identity.json or PASS evidence.
    """
    validate(identity, plan=plan)
    if identity["selection"].get("filelist_sha256") is not None:
        raise IdentityError("dynamic workspace requires an unbound filelist")
    directory = _reserve_directory(root, identity, plan=plan)
    materialize(directory)
    filelist = directory / "sources.f"
    if filelist.is_symlink() or not filelist.is_file():
        raise IdentityError("materialized compiler filelist missing or unsafe")
    complete = bind_filelist(identity, filelist.read_bytes())
    save(directory / "identity.json", complete, exclusive=True)
    return directory, complete


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
    """Fail closed unless a real selected Xezim producer met its outcome.

    For a negative target that means the original named mismatch and a
    positive nonzero simulator exit, not a simulation success marker.
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
    if (plan.get("engine") != "xezim"
            or not uses_canonical_workspace(target, plan)
            or not plan.get("pass")
            or plan.get("mode", "simulate") != "simulate"
            or (target == "serv" and
                (plan.get("top") != "serv_minimal_tb"
                 or plan.get("sources") != "serv"
                 or plan.get("logical_test") != "cpu-instruction-smoke"
                 or plan.get("mode", "simulate") != "simulate"))):
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
    expected_failure = plan.get("expect_failure")
    outcomes = record.get("results", [])
    outcome = outcomes[0] if isinstance(outcomes, list) and len(outcomes) == 1 else {}
    exit_code = outcome.get("exit_code") if isinstance(outcome, dict) else None
    expected_exit = type(exit_code) is int and (
        (exit_code > 0) if expected_failure else (exit_code == 0))
    if (record.get("target") != target or record.get("passed") is not True
            or record.get("stage") != "all"
            or record.get("identity_sha256") != identity["identity_sha256"]
            or record.get("canonical_id") != relative_path(identity).as_posix()
            or resolved.get("identity") != identity
            or not expected_exit or outcome.get("name") != target
            or outcome.get("passed") is not True):
        raise IdentityError("canonical run lacks completed selected Xezim outcome")
    transcript = (folder / expected_log).read_text(errors="replace")
    if expected_failure:
        if expected_failure not in transcript or plan["pass"] in transcript:
            raise IdentityError("canonical simulator transcript lacks the named negative outcome")
    elif plan["pass"] not in transcript:
        raise IdentityError("canonical simulator transcript missing original PASS marker")
    if root.name != 'runs' or root.parent.name != '.tools':
        raise IdentityError('canonical Xezim root is not the configured run root')
    verify_selected_archive(root.parent.parent, target, plan, directory=folder)
    return {"target": target, "canonical_id": relative_path(identity).as_posix(),
            "status": ("runner_completed_xezim_expected_negative" if expected_failure
                       else "runner_completed_xezim_no_protocol_coverage_claim")}


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
