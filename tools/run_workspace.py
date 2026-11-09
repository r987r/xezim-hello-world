"""One safe canonical run-directory allocator built on existing test_identity.

This is a migration foundation for #139. Existing regress.py and legacy
scratch paths are intentionally unchanged until each producer is migrated.
Never mirror or relabel archived output, and never infer PASS from a path.
"""
from __future__ import annotations

import os
from pathlib import Path

from tools.test_identity import (
    IdentityError, relative_path, save, validate,
)


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
    from tools.test_identity import load
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
