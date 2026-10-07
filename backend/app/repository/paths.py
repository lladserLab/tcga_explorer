from __future__ import annotations

import os
from pathlib import Path
import re

from app.repository.storage import safe_bundle_path


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_LEGACY_ABSOLUTE_ROOTS = (Path("/repo"), Path("/repository"))
_LEGACY_RELATIVE_ROOTS = (Path("external_repository"),)
_MANIFEST_NAME = "manifest.json"


def _identifier(value: str, label: str) -> str:
    normalized = str(value or "").strip()
    if (
        len(normalized) > 128
        or not _IDENTIFIER_PATTERN.fullmatch(normalized)
    ):
        raise ValueError(f"Unsafe repository {label}: {value!r}.")
    return normalized


def _lexical_path(value: str | Path, label: str) -> Path:
    raw = str(value or "").strip()
    if not raw or "\x00" in raw:
        raise ValueError(f"Repository {label} is empty or invalid.")
    path = Path(raw)
    if ".." in path.parts:
        raise ValueError(f"Repository {label} contains path traversal.")
    return Path(os.path.normpath(raw))


def _release_suffix(dataset_id: str, release_id: str) -> Path:
    return Path("studies") / dataset_id / "releases" / release_id


def _allowed_stored_release_paths(
    repository_root: Path,
    suffix: Path,
    *,
    allow_legacy: bool,
) -> tuple[Path, ...]:
    configured = Path(repository_root)
    roots = {
        configured,
        configured.absolute(),
        configured.resolve(strict=False),
    }
    allowed = {root / suffix for root in roots}
    if allow_legacy:
        allowed.update(root / suffix for root in _LEGACY_ABSOLUTE_ROOTS)
        allowed.update(root / suffix for root in _LEGACY_RELATIVE_ROOTS)
    return tuple(allowed)


def resolve_repository_release_path(
    repository_root: Path,
    *,
    dataset_id: str,
    release_id: str,
    stored_path: str | Path,
    allow_legacy: bool = True,
) -> Path:
    """Resolve a stored release location onto the configured repository mount.

    Historical database rows may name one of TRACE's former mount points, or
    may point at the release manifest instead of its directory. The stored path
    is used only to verify exact release ownership; bytes are always read from
    the configured repository root.
    """

    dataset = _identifier(dataset_id, "dataset ID")
    release = _identifier(release_id, "release ID")
    suffix = _release_suffix(dataset, release)
    stored = _lexical_path(stored_path, "release path")
    if stored.name == _MANIFEST_NAME:
        stored = stored.parent
    allowed = _allowed_stored_release_paths(
        repository_root,
        suffix,
        allow_legacy=allow_legacy,
    )
    if stored not in allowed:
        raise ValueError(
            "Stored repository path is not the configured release path or a "
            f"recognized TRACE legacy path for {dataset}/{release}."
        )

    root = Path(repository_root).resolve(strict=False)
    if not root.is_dir():
        raise FileNotFoundError(
            f"Configured cancer repository root is unavailable: {root}."
        )
    candidate = (root / suffix).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            "Canonical repository release path escapes the configured root."
        ) from exc
    if not candidate.is_dir():
        raise FileNotFoundError(
            f"Canonical repository release directory is unavailable: {candidate}."
        )
    manifest = candidate / _MANIFEST_NAME
    if not manifest.is_file():
        raise FileNotFoundError(
            f"Canonical repository release manifest is unavailable: {manifest}."
        )
    return candidate


def resolve_repository_artifact_path(
    repository_root: Path,
    *,
    dataset_id: str,
    release_id: str,
    stored_release_path: str | Path,
    stored_artifact_path: str | Path,
    allow_legacy: bool = True,
) -> Path:
    """Rebase a release-owned artifact onto the configured repository mount."""

    dataset = _identifier(dataset_id, "dataset ID")
    release = _identifier(release_id, "release ID")
    suffix = _release_suffix(dataset, release)
    release_path = resolve_repository_release_path(
        repository_root,
        dataset_id=dataset,
        release_id=release,
        stored_path=stored_release_path,
        allow_legacy=allow_legacy,
    )
    stored_artifact = _lexical_path(
        stored_artifact_path, "artifact path"
    )
    relative: Path | None = None
    for allowed_release in _allowed_stored_release_paths(
        repository_root,
        suffix,
        allow_legacy=allow_legacy,
    ):
        try:
            candidate_relative = stored_artifact.relative_to(allowed_release)
        except ValueError:
            continue
        if candidate_relative.parts:
            relative = candidate_relative
            break
    if relative is None:
        raise ValueError(
            "Stored repository artifact is not owned by the configured release "
            "or a recognized TRACE legacy release path."
        )
    candidate = safe_bundle_path(release_path, relative.as_posix())
    if not candidate.is_file():
        raise FileNotFoundError(
            f"Canonical repository artifact is unavailable: {candidate}."
        )
    return candidate
