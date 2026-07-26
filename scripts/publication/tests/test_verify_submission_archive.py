from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "verify_submission_archive.py"
SPEC = importlib.util.spec_from_file_location("verify_submission_archive", MODULE_PATH)
assert SPEC is not None
verifier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verifier
assert SPEC.loader is not None
SPEC.loader.exec_module(verifier)


def write_archive(path: Path, files: dict[str, bytes], *, prefix: str = verifier.DEFAULT_PREFIX) -> None:
    manifest_files = [
        {
            "path": name,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        for name, content in sorted(files.items())
    ]
    manifest = {
        "schema_version": "tcga-trace-review-archive-v1",
        "project_name": "TCGA-TRACE",
        "archive_prefix": prefix,
        "file_count": len(manifest_files),
        "submission_artifact_count": 45,
        "submission_artifacts_available": 45,
        "files": manifest_files,
    }
    with tarfile.open(path, "w:gz") as archive:
        for name, content in files.items():
            add_bytes(archive, f"{prefix}/{name}", content)
        add_bytes(
            archive,
            f"{prefix}/submission_archive_manifest.json",
            json.dumps(manifest, sort_keys=True).encode("utf-8"),
        )


def add_bytes(archive: tarfile.TarFile, name: str, content: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    archive.addfile(info, io.BytesIO(content))


def required_files() -> dict[str, bytes]:
    files = {
        name: f"{name}\n".encode("utf-8")
        for name in verifier.REQUIRED_ARCHIVE_PATHS
        if name not in {"submission_archive_manifest.json", verifier.REPRODUCIBILITY_SUMMARY}
    }
    analysis_id = "reconstruction-test"
    files[verifier.REPRODUCIBILITY_SUMMARY] = (
        "label,analysis_id,status\nSingle gene,reconstruction-test,passed\n"
    ).encode("utf-8")
    for filename in verifier.REPRODUCIBILITY_BUNDLE_FILES:
        files[f"artifacts/{analysis_id}/{filename}"] = f"{filename}\n".encode("utf-8")
    return files


def test_inspect_archive_accepts_required_minimal_archive(tmp_path: Path) -> None:
    archive_path = tmp_path / "review.tar.gz"
    write_archive(archive_path, required_files())

    check = verifier.inspect_archive(archive_path)

    assert check.blockers == []
    assert check.manifest["submission_artifact_count"] == 45


def test_inspect_archive_reports_missing_required_file(tmp_path: Path) -> None:
    files = required_files()
    files.pop("REVIEWER_QUICKSTART.md")
    archive_path = tmp_path / "review.tar.gz"
    write_archive(archive_path, files)

    check = verifier.inspect_archive(archive_path)

    assert "missing required archive file: REVIEWER_QUICKSTART.md" in check.blockers


def test_inspect_archive_rejects_runtime_cache_paths(tmp_path: Path) -> None:
    files = required_files()
    files["derived/rna_bulk/matrices/TCGA-KIRC/log2_tpm.float32.bin"] = b"cache"
    archive_path = tmp_path / "review.tar.gz"
    write_archive(archive_path, files)

    check = verifier.inspect_archive(archive_path)

    assert any("forbidden runtime/cache path included" in blocker for blocker in check.blockers)


def test_inspect_archive_rejects_private_key_pem(tmp_path: Path) -> None:
    files = required_files()
    files["attestation_keys/ed25519-private.pem"] = b"private key"
    archive_path = tmp_path / "review.tar.gz"
    write_archive(archive_path, files)

    check = verifier.inspect_archive(archive_path)

    assert (
        "forbidden generated file included: attestation_keys/ed25519-private.pem"
        in check.blockers
    )


def test_inspect_archive_rejects_unlisted_analysis_bundle(tmp_path: Path) -> None:
    files = required_files()
    files["artifacts/unlisted/audit_report.json"] = b"unexpected"
    archive_path = tmp_path / "review.tar.gz"
    write_archive(archive_path, files)

    check = verifier.inspect_archive(archive_path)

    assert "unexpected non-benchmark artifact included: artifacts/unlisted/audit_report.json" in check.blockers


def test_inspect_archive_requires_all_reconstruction_bundle_files(tmp_path: Path) -> None:
    files = required_files()
    files.pop("artifacts/reconstruction-test/raw_data.csv")
    archive_path = tmp_path / "review.tar.gz"
    write_archive(archive_path, files)

    check = verifier.inspect_archive(archive_path)

    assert (
        "missing reconstruction-benchmark file: "
        "artifacts/reconstruction-test/raw_data.csv"
    ) in check.blockers


def test_inspect_archive_rejects_manifest_hash_mismatch(tmp_path: Path) -> None:
    files = required_files()
    archive_path = tmp_path / "review.tar.gz"
    write_archive(archive_path, files)
    bad_path = tmp_path / "bad-review.tar.gz"
    with tarfile.open(archive_path, "r:gz") as source, tarfile.open(bad_path, "w:gz") as dest:
        for member in source.getmembers():
            content = source.extractfile(member).read() if member.isfile() else b""
            if member.name.endswith("/REVIEWER_QUICKSTART.md"):
                content = b"tampered\n"
                member.size = len(content)
            dest.addfile(member, io.BytesIO(content))

    check = verifier.inspect_archive(bad_path)

    assert any("manifest sha256 mismatch for REVIEWER_QUICKSTART.md" == blocker for blocker in check.blockers)
