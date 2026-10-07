from pathlib import Path

import pytest

from app.repository.paths import (
    resolve_repository_artifact_path,
    resolve_repository_release_path,
)


DATASET_ID = "fixture-study"
RELEASE_ID = "fixture-release-v1"


def canonical_release(repository_root: Path) -> Path:
    release = (
        repository_root
        / "studies"
        / DATASET_ID
        / "releases"
        / RELEASE_ID
    )
    (release / "derived").mkdir(parents=True)
    (release / "manifest.json").write_text("{}", encoding="utf-8")
    (release / "derived/expression.bin").write_bytes(b"matrix")
    return release


@pytest.mark.parametrize(
    "stored",
    [
        "/repo/studies/fixture-study/releases/fixture-release-v1",
        "/repo/studies/fixture-study/releases/fixture-release-v1/manifest.json",
        "/repository/studies/fixture-study/releases/fixture-release-v1",
        "external_repository/studies/fixture-study/releases/fixture-release-v1",
    ],
)
def test_release_resolver_rebases_only_known_legacy_paths(
    tmp_path: Path, stored: str
):
    repository_root = tmp_path / "repository"
    expected = canonical_release(repository_root)

    resolved = resolve_repository_release_path(
        repository_root,
        dataset_id=DATASET_ID,
        release_id=RELEASE_ID,
        stored_path=stored,
    )

    assert resolved == expected


def test_release_resolver_accepts_configured_directory_or_manifest(
    tmp_path: Path,
):
    repository_root = tmp_path / "repository"
    expected = canonical_release(repository_root)

    for stored in (expected, expected / "manifest.json"):
        assert (
            resolve_repository_release_path(
                repository_root,
                dataset_id=DATASET_ID,
                release_id=RELEASE_ID,
                stored_path=stored,
            )
            == expected
        )


@pytest.mark.parametrize(
    "stored",
    [
        "/tmp/studies/fixture-study/releases/fixture-release-v1",
        "studies/fixture-study/releases/fixture-release-v1",
        "/repo/studies/another-study/releases/fixture-release-v1",
        "/repo/studies/fixture-study/releases/another-release",
        "/repo/../repo/studies/fixture-study/releases/fixture-release-v1",
    ],
)
def test_release_resolver_rejects_unknown_or_mismatched_paths(
    tmp_path: Path, stored: str
):
    repository_root = tmp_path / "repository"
    canonical_release(repository_root)

    with pytest.raises(ValueError):
        resolve_repository_release_path(
            repository_root,
            dataset_id=DATASET_ID,
            release_id=RELEASE_ID,
            stored_path=stored,
        )


def test_artifact_resolver_rebases_legacy_artifact_without_reading_it(
    tmp_path: Path,
):
    repository_root = tmp_path / "repository"
    release = canonical_release(repository_root)

    resolved = resolve_repository_artifact_path(
        repository_root,
        dataset_id=DATASET_ID,
        release_id=RELEASE_ID,
        stored_release_path=(
            "/repo/studies/fixture-study/releases/"
            "fixture-release-v1/manifest.json"
        ),
        stored_artifact_path=(
            "/repo/studies/fixture-study/releases/"
            "fixture-release-v1/derived/expression.bin"
        ),
    )

    assert resolved == release / "derived/expression.bin"


def test_artifact_resolver_rejects_unknown_root_and_traversal(
    tmp_path: Path,
):
    repository_root = tmp_path / "repository"
    canonical_release(repository_root)
    common = {
        "repository_root": repository_root,
        "dataset_id": DATASET_ID,
        "release_id": RELEASE_ID,
        "stored_release_path": (
            "/repo/studies/fixture-study/releases/fixture-release-v1"
        ),
    }

    with pytest.raises(ValueError):
        resolve_repository_artifact_path(
            **common,
            stored_artifact_path=(
                "/tmp/studies/fixture-study/releases/"
                "fixture-release-v1/derived/expression.bin"
            ),
        )
    with pytest.raises(ValueError, match="traversal"):
        resolve_repository_artifact_path(
            **common,
            stored_artifact_path=(
                "/repo/studies/fixture-study/releases/fixture-release-v1/"
                "derived/../manifest.json"
            ),
        )
