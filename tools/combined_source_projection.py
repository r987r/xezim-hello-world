"""Reference-coordinate comparison of the actual, immutable combined sources.

Do not publish a projection as a selected manifest or a run result. Its keys
and hashes model the fixed coordinates of the original qualified source lock;
the selected archive continues to attest the actual list and original bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import shlex
from pathlib import Path

try:
    from .selected_rtl_provenance import _canonical_sha, verify_selected_archive
except ImportError:
    from selected_rtl_provenance import _canonical_sha, verify_selected_archive

PROFILE = "chip-ethernet-ddr-pcie"
SOURCE_ROOT = f".tools/regression/{PROFILE}/"
BRIDGE = "variant/pcie/pcie_axi_master.v"
LEGACY_BRIDGE = ".tools/pcie0/normalized/pcie_axi_master.v"
IMAGES = {
    "variant/soc_top.sv": ("flash.hex", "bootrom.hex"),
    "variant/full_chip_tb.sv": ("compute0.hex", "compute1.hex"),
    "variant/manifest.json": ("flash.hex",),
}


class SourceProjectionError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class ReviewInputs:
    """Comparison data and canonical-to-reference bindings, not run evidence."""

    reference: dict
    reference_filelist: bytes
    canonical_by_reference: dict
    normalized_bytes: dict
    actual_manifest_sha256: str | None


def project(root: Path, run_dir: Path, manifest: dict, plan: dict, *, read) -> ReviewInputs:
    """Project only approved path relocations from a verified combined archive.

    `read` must return actual checkout-owned bytes matching the supplied digest.
    It is only invoked for the actual filelist and known image-containing files.
    The caller still verifies all source and copied SHA values before here.
    """
    if (not run_dir.is_relative_to(root / ".tools/runs")
            or manifest.get("profile") != PROFILE
            or manifest.get("compiled_top") != "full_chip_tb"
            or manifest.get("source_count") != 312
            or manifest.get("network_filelists") != {}):
        raise SourceProjectionError("unexpected combined reference input scope")
    current = run_dir.relative_to(root).as_posix() + "/"
    actual_bridge = current + BRIDGE
    top = current + "variant/soc_top.sv"
    if manifest.get("selected_soc_top") != top:
        raise SourceProjectionError("combined selected top is not producer-owned")
    identity = plan.get("identity", {})
    if (manifest.get("identity_sha256") != identity.get("identity_sha256")
            or manifest.get("config_sha256") != identity.get("config_sha256")
            or manifest.get("filelist_sha256") != identity.get("selection", {}).get("filelist_sha256")
            or identity.get("config_sha256") != _canonical_sha(identity.get("selection", {}))):
        raise SourceProjectionError("combined reference inputs do not belong to the actual identity")
    by_reference, rewritten = {}, {}

    def original(name):
        if name == actual_bridge:
            reference = LEGACY_BRIDGE
        elif name.startswith(current):
            reference = SOURCE_ROOT + name[len(current):]
        elif name.startswith((".tools/runs/", SOURCE_ROOT)) or name == LEGACY_BRIDGE:
            raise SourceProjectionError("combined inputs borrow a foreign run or retired producer")
        else:
            reference = name
        prior = by_reference.setdefault(reference, name)
        if prior != name:
            raise SourceProjectionError("duplicate combined reference coordinate")
        return reference

    def inventory(name, omit_bridge=False):
        selected = manifest.get(name)
        if not isinstance(selected, dict) or actual_bridge not in selected:
            raise SourceProjectionError("combined archive lacks producer-owned PCIe bridge")
        result = {}
        for actual, sha in selected.items():
            reference = original(actual)
            if omit_bridge and actual == actual_bridge:
                # It was an independent compiled input in the historical
                # projection, not a generated asset owned by that stage.
                continue
            suffix = actual.removeprefix(current)
            if actual.startswith(current) and suffix in IMAGES:
                raw = read(actual, sha)
                for image in IMAGES[suffix]:
                    actual_image = (current + "variant/" + image).encode("ascii")
                    old_image = (SOURCE_ROOT + "variant/" + image).encode("ascii")
                    if raw.count(actual_image) != 1:
                        raise SourceProjectionError("combined source must have one owned image " + image)
                    raw = raw.replace(actual_image, old_image)
                if current.encode("ascii") in raw:
                    raise SourceProjectionError("unreviewed path relocation in combined source")
                rewritten[reference] = raw
                sha = digest(raw)
            result[reference] = sha
        return result

    sources = inventory("source_sha256")
    generated = inventory("generated_sha256", omit_bridge=True)
    if len(sources) != 312 or any(
            name not in rewritten for name in (SOURCE_ROOT + suffix for suffix in IMAGES)):
        raise SourceProjectionError("combined reference closure is missing reviewed inputs")

    raw = read(current + "sources.f", manifest["filelist_sha256"])
    # Preserve original byte representation, line order, quoting, includes
    # and compiler switches; replace only each verified owned source token.
    tokens = shlex.split(raw.decode())
    expected = (["+incdir+" + p for p in plan.get("includes", [])]
                + ["+define+" + p for p in plan.get("defines", [])]
                + plan.get("sources", []))
    if tokens != expected or len(plan["sources"]) != 312:
        raise SourceProjectionError("combined compiler filelist differs from prepared selection")
    for name in plan["sources"]:
        source = Path(name)
        if not source.is_absolute() or not source.is_relative_to(root):
            raise SourceProjectionError("foreign selected combined source")
        original(source.relative_to(root).as_posix())
    bridge_raw = actual_bridge.encode("ascii")
    if raw.count(bridge_raw) != 1:
        raise SourceProjectionError("combined bridge does not have one compiler entry")
    reference_filelist = raw.replace(bridge_raw, LEGACY_BRIDGE.encode("ascii"))
    reference_filelist = reference_filelist.replace(current.encode("ascii"), SOURCE_ROOT.encode("ascii"))
    filelist_sha = digest(reference_filelist)
    selection = {k: plan[k] for k in ("engine", "top", "source_target", "firmware_mode", "includes", "defines", "args")}
    selection.update({k: manifest[k] for k in ("include_headers_sha256", "network_filelists")})
    selection.update(filelist_sha256=filelist_sha, source_sha256=sources, generated_sha256=generated,
                     config_sha256=_canonical_sha({**identity["selection"], "filelist_sha256": filelist_sha}))
    reference = {k: manifest[k] for k in (
        "schema_version", "profile", "compiled_top", "source_count", "definition_sha256",
        "include_headers_sha256", "network_filelists", "includes", "defines", "args")}
    reference.update(selected_soc_top=original(top), source_sha256=sources, generated_sha256=generated,
                     config_sha256=selection["config_sha256"], filelist_sha256=filelist_sha,
                     compiler_input_sha256=_canonical_sha(selection))
    return ReviewInputs(reference, reference_filelist, by_reference, rewritten,
                        manifest.get("manifest_sha256"))

def verified_files_archive(root: Path, directory: Path, definition: dict) -> tuple[Path, dict]:
    """Resolve and verify one explicit combined files invocation, never a mirror."""
    try:
        from .run_workspace import eligible_combined
    except ImportError:
        from run_workspace import eligible_combined
    if not eligible_combined(PROFILE, definition):
        raise SourceProjectionError("files review requires the registered combined profile")
    root = root.resolve()
    if not directory.is_absolute():
        directory = root / directory
    if '..' in directory.parts or not directory.is_relative_to(root / ".tools/runs"):
        raise SourceProjectionError("combined preflight needs a checkout-owned run path")
    mirror = root / SOURCE_ROOT
    if mirror.exists() or mirror.is_symlink():
        raise SourceProjectionError("legacy combined producer mirror forbidden; select a new files workspace")
    manifest = verify_selected_archive(root, PROFILE, definition, directory=directory)
    plan = json.loads((directory / "plan.json").read_text())
    identity = json.loads((directory / "identity.json").read_text())
    runtime_files = ("result.json", "ddr-split-build.json", "ddr-split-run.claim",
                     "results.xml", "simulation.log")
    if (plan.get("stage") != "files" or plan.get("identity") != identity
            or any((directory / name).exists() or (directory / name).is_symlink()
                   for name in runtime_files)):
        raise SourceProjectionError("combined source review needs a files-only invocation")
    return directory, manifest


def verified_inputs(root: Path, directory: Path, definition: dict) -> ReviewInputs:
    """Read an explicit files invocation; keep historical comparison separate."""
    root = root.resolve()
    directory, manifest = verified_files_archive(root, directory, definition)
    plan = json.loads((directory / "plan.json").read_text())

    def read(name, expected):
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise SourceProjectionError("unsafe projected source path")
        raw = path.read_bytes()
        if digest(raw) != expected:
            raise SourceProjectionError("projected source changed after verification")
        return raw

    return project(root, directory, manifest, plan, read=read)


def prepared_workspace(root: Path, definition: dict, prepare) -> Path:
    """Select precisely the new, verified files workspace from a preparation."""
    try:
        from .run_workspace import selected_run_folder, snapshot_run_ids
    except ImportError:
        from run_workspace import selected_run_folder, snapshot_run_ids
    scope = {"stage": "files", "canonical_combined_files": True}
    earlier = snapshot_run_ids(root, PROFILE, definition, **scope)
    prepare()
    folder = selected_run_folder(root, PROFILE, definition, prior_run_ids=earlier, **scope)
    if folder is None:
        raise SourceProjectionError("no new exact combined files-only workspace")
    return folder
