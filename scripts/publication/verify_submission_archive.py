#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_PREFIX = "tcga-trace-review-package"
REPRODUCIBILITY_SUMMARY = (
    "docs/publication/benchmark/reproducibility_benchmark/summary.csv"
)
REPRODUCIBILITY_BUNDLE_FILES = (
    "audit_report.json",
    "input.json",
    "metrics.json",
    "raw_data.csv",
)

REQUIRED_ARCHIVE_PATHS = [
    "submission_archive_manifest.json",
    "REVIEWER_QUICKSTART.md",
    ".gitleaks.toml",
    ".github/workflows/ci.yml",
    ".github/workflows/release-readiness.yml",
    "backend/app/attestation.py",
    "backend/app/session_history.py",
    "backend/tests/test_attestation.py",
    "backend/tests/test_session_history.py",
    "frontend/src/sessionHistory.js",
    "frontend/src/sessionHistory.test.js",
    "manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-application-note.pdf",
    "manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-oup-preview.pdf",
    "manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-supplement.pdf",
    "manuscript/bioinformatics_app_note/figures/figure_alt_text.md",
    "manuscript/bioinformatics_app_note/figures/graphical_abstract.tex",
    "manuscript/bioinformatics_app_note/tables/feature_benchmark_diagnostic_summary.tex",
    "manuscript/bioinformatics_app_note/tables/feature_benchmark_summary.tex",
    "manuscript/bioinformatics_app_note/tables/feature_signature_definitions.tex",
    "manuscript/bioinformatics_app_note/tables/immune_pancancer_atlas_model_summary.tex",
    "manuscript/bioinformatics_app_note/tables/reproducibility_benchmark.tex",
    "manuscript/bioinformatics_app_note/tables/runtime_concurrency_benchmark.tex",
    "manuscript/bioinformatics_app_note/tables/statistical_calibration.tex",
    "manuscript/bioinformatics_app_note/tables/single_gene_benchmark_full_overview.tex",
    "manuscript/bioinformatics_app_note/submission/browser_compatibility_record.md",
    "manuscript/bioinformatics_app_note/submission/owner_metadata.template.json",
    "docs/publication/application_note_writing_blueprint.md",
    "docs/PROJECT_IDENTITY.md",
    "docs/CLI.md",
    "docs/CLI_ES.md",
    "docs/publication/benchmark/feature_benchmarks/signature_definitions.md",
    REPRODUCIBILITY_SUMMARY,
    "docs/publication/benchmark/reproducibility_benchmark/summary.md",
    "docs/publication/benchmark/server_attestation/audit_report.json",
    "docs/publication/benchmark/server_attestation/attestation_receipt.json",
    "docs/publication/benchmark/server_attestation/public_key.json",
    "docs/publication/benchmark/server_attestation/verification_results.raw.json",
    "docs/publication/benchmark/server_attestation/summary.md",
    "docs/publication/benchmark/browser_compatibility/benchmark_results.raw.json",
    "docs/publication/benchmark/browser_compatibility/manifest.json",
    "docs/publication/benchmark/browser_compatibility/summary.md",
    "docs/publication/benchmark/runtime_concurrency/benchmark_results.raw.json",
    "docs/publication/benchmark/runtime_concurrency/manifest.json",
    "docs/publication/benchmark/runtime_concurrency/summary.csv",
    "docs/publication/benchmark/runtime_concurrency/summary.md",
    "docs/publication/benchmark/statistical_calibration/calibration_design.json",
    "docs/publication/benchmark/statistical_calibration/calibration_results.raw.json",
    "docs/publication/benchmark/statistical_calibration/manifest.json",
    "docs/publication/benchmark/statistical_calibration/permutation_replicates.csv",
    "docs/publication/benchmark/statistical_calibration/simulation_replicates.csv",
    "docs/publication/benchmark/statistical_calibration/summary.csv",
    "docs/publication/benchmark/statistical_calibration/summary.md",
    "docs/publication/benchmark/lgg_emp3_os_cutpoint_benchmark/summary.md",
    "docs/publication/benchmark/lihc_cdc20_os_cutpoint_benchmark/summary.md",
    "docs/publication/benchmark/luad_birc5_os_cutpoint_benchmark/summary.md",
    "docs/publication/benchmark/skcm_sample_rule_sensitivity/README.md",
    "docs/publication/benchmark/skcm_tmem176b_os_cutpoint_benchmark/summary.md",
    "docs/publication/benchmark/skcm_tmem176b_sample_rule_sensitivity/README.md",
    "docs/publication/benchmark/uvm_bap1_dss_cutpoint_benchmark/summary.md",
    "scripts/publication/apply_submission_metadata.py",
    "scripts/publication/build_oup_preview.py",
    "scripts/publication/build_submission_archive.py",
    "scripts/publication/capture_reviewer_screenshots.py",
    "scripts/publication/check_editorial_compliance.py",
    "scripts/publication/check_project_identity.py",
    "scripts/publication/finalize_submission_package.py",
    "scripts/publication/run_reproducibility_benchmark.py",
    "scripts/publication/run_server_attestation_benchmark.py",
    "scripts/publication/run_browser_compatibility.py",
    "scripts/publication/run_runtime_benchmark.py",
    "scripts/publication/run_statistical_calibration.py",
    "scripts/publication/statistical_calibration.R",
    "scripts/publication/verify_submission_archive.py",
    "scripts/publication/write_license_template.py",
    "scripts/tcga_trace_cli.py",
    "scripts/tests/test_tcga_trace_cli.py",
    "scripts/tests/test_verify_server_attestation.py",
    "scripts/verify_server_attestation.py",
    "scripts/publication/tests/test_apply_submission_metadata.py",
    "scripts/publication/tests/test_build_oup_preview.py",
    "scripts/publication/tests/test_capture_reviewer_screenshots.py",
    "scripts/publication/tests/test_run_browser_compatibility.py",
    "scripts/publication/tests/test_run_server_attestation_benchmark.py",
    "scripts/publication/tests/test_check_editorial_compliance.py",
    "scripts/publication/tests/test_finalize_submission_package.py",
    "scripts/publication/tests/test_verify_submission_archive.py",
    "scripts/publication/tests/test_write_license_template.py",
]

FORBIDDEN_FRAGMENTS = [
    "/.git/",
    "/frontend/node_modules/",
    "/frontend/dist/",
    "/derived/rna_bulk/",
    "/postgres_data/",
    "/logs/",
]

FORBIDDEN_SUFFIXES = [
    ".pyc",
    ".zip",
    ".pem",
]

ALLOWLISTED_RUNTIME_FILES = {
    "artifacts/.gitkeep",
    "clinical/.gitkeep",
    "derived/.gitkeep",
    "jcga/.gitkeep",
}


@dataclass(frozen=True)
class ArchiveCheck:
    path: Path
    prefix: str
    names: list[str]
    manifest: dict[str, Any]
    blockers: list[str]


def main() -> int:
    args = parse_args()
    try:
        check = inspect_archive(Path(args.archive), prefix=args.prefix)
    except ArchiveError as exc:
        print(f"Submission archive verification failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report(check), indent=2, sort_keys=True))
    else:
        print_human_summary(check)
    return 1 if check.blockers else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the compact TCGA-TRACE reviewer/source archive. The check "
            "confirms required files, excludes runtime data/caches, and compares "
            "manifest SHA-256 records against tar contents."
        )
    )
    parser.add_argument("archive", help="Path to tcga-trace-review-package .tar.gz.")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="Expected top-level directory in the archive.")
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable verification report.")
    return parser.parse_args()


def inspect_archive(path: Path, *, prefix: str = DEFAULT_PREFIX) -> ArchiveCheck:
    if not path.is_file():
        raise ArchiveError(f"{path} does not exist")
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            members = archive.getmembers()
            names = sorted(member.name for member in members)
            manifest = read_manifest(archive, prefix)
            blockers = collect_blockers(archive, members, manifest, prefix)
    except (tarfile.TarError, OSError) as exc:
        raise ArchiveError(f"{path} is not a readable gzip tar archive: {exc}") from exc
    return ArchiveCheck(path=path, prefix=prefix, names=names, manifest=manifest, blockers=blockers)


def read_manifest(archive: tarfile.TarFile, prefix: str) -> dict[str, Any]:
    manifest_name = f"{prefix}/submission_archive_manifest.json"
    try:
        handle = archive.extractfile(manifest_name)
    except KeyError as exc:
        raise ArchiveError(f"missing {manifest_name}") from exc
    if handle is None:
        raise ArchiveError(f"{manifest_name} is not a regular file")
    try:
        payload = json.loads(handle.read().decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ArchiveError(f"{manifest_name} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ArchiveError(f"{manifest_name} must contain a JSON object")
    return payload


def collect_blockers(
    archive: tarfile.TarFile,
    members: list[tarfile.TarInfo],
    manifest: dict[str, Any],
    prefix: str,
) -> list[str]:
    blockers: list[str] = []
    names = [member.name for member in members]
    relative_names = sorted(strip_prefix(name, prefix) for name in names if strip_prefix(name, prefix) is not None)
    member_by_relative = {
        strip_prefix(member.name, prefix): member
        for member in members
        if strip_prefix(member.name, prefix) is not None
    }

    bundle_prefixes, bundle_blockers = reproducibility_bundle_prefixes(archive, prefix)
    blockers.extend(bundle_blockers)
    blockers.extend(required_file_blockers(relative_names))
    blockers.extend(reproducibility_bundle_blockers(relative_names, bundle_prefixes))
    blockers.extend(forbidden_path_blockers(relative_names, bundle_prefixes))
    blockers.extend(manifest_shape_blockers(manifest, relative_names, prefix))
    blockers.extend(manifest_file_record_blockers(archive, manifest, member_by_relative, prefix))
    return blockers


def required_file_blockers(relative_names: list[str]) -> list[str]:
    present = set(relative_names)
    return [f"missing required archive file: {path}" for path in REQUIRED_ARCHIVE_PATHS if path not in present]


def reproducibility_bundle_prefixes(
    archive: tarfile.TarFile,
    prefix: str,
) -> tuple[tuple[str, ...], list[str]]:
    member_name = f"{prefix}/{REPRODUCIBILITY_SUMMARY}"
    try:
        handle = archive.extractfile(member_name)
    except KeyError:
        return (), [f"missing required archive file: {REPRODUCIBILITY_SUMMARY}"]
    if handle is None:
        return (), [f"{REPRODUCIBILITY_SUMMARY} is not a regular file"]
    try:
        text = handle.read().decode("utf-8")
        rows = list(csv.DictReader(io.StringIO(text)))
    except (UnicodeDecodeError, csv.Error) as exc:
        return (), [f"{REPRODUCIBILITY_SUMMARY} is not readable CSV: {exc}"]
    analysis_ids = [
        str(row.get("analysis_id") or "").strip()
        for row in rows
        if str(row.get("analysis_id") or "").strip()
    ]
    if not analysis_ids:
        return (), [f"{REPRODUCIBILITY_SUMMARY} contains no analysis_id values"]
    if len(analysis_ids) != len(set(analysis_ids)):
        return (), [f"{REPRODUCIBILITY_SUMMARY} contains duplicate analysis_id values"]
    return tuple(f"artifacts/{analysis_id}/" for analysis_id in analysis_ids), []


def reproducibility_bundle_blockers(
    relative_names: list[str],
    bundle_prefixes: tuple[str, ...],
) -> list[str]:
    present = set(relative_names)
    blockers: list[str] = []
    for bundle_prefix in bundle_prefixes:
        for filename in REPRODUCIBILITY_BUNDLE_FILES:
            path = bundle_prefix + filename
            if path not in present:
                blockers.append(f"missing reconstruction-benchmark file: {path}")
    return blockers


def forbidden_path_blockers(
    relative_names: list[str],
    bundle_prefixes: tuple[str, ...],
) -> list[str]:
    blockers: list[str] = []
    for name in relative_names:
        normalized = "/" + name
        if any(fragment in normalized for fragment in FORBIDDEN_FRAGMENTS):
            blockers.append(f"forbidden runtime/cache path included: {name}")
        if any(name.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
            blockers.append(f"forbidden generated file included: {name}")
        if (
            name.startswith("artifacts/")
            and name not in ALLOWLISTED_RUNTIME_FILES
            and not any(name.startswith(bundle_prefix) for bundle_prefix in bundle_prefixes)
        ):
            blockers.append(f"unexpected non-benchmark artifact included: {name}")
        if name.startswith("clinical/") and name not in ALLOWLISTED_RUNTIME_FILES:
            blockers.append(f"unexpected clinical data included: {name}")
        if name.startswith("jcga/") and name not in ALLOWLISTED_RUNTIME_FILES:
            blockers.append(f"unexpected JCGA data included: {name}")
    return blockers


def manifest_shape_blockers(manifest: dict[str, Any], relative_names: list[str], prefix: str) -> list[str]:
    blockers: list[str] = []
    if manifest.get("schema_version") != "tcga-trace-review-archive-v1":
        blockers.append("manifest schema_version is not tcga-trace-review-archive-v1")
    if manifest.get("project_name") != "TCGA-TRACE":
        blockers.append("manifest project_name is not TCGA-TRACE")
    if manifest.get("archive_prefix") != prefix:
        blockers.append(f"manifest archive_prefix is not {prefix}")
    files = manifest.get("files")
    if not isinstance(files, list):
        blockers.append("manifest files field is missing or not a list")
        return blockers
    expected_file_count = len([name for name in relative_names if name != "submission_archive_manifest.json"])
    if manifest.get("file_count") != expected_file_count:
        blockers.append(
            f"manifest file_count {manifest.get('file_count')} does not match archive file count {expected_file_count}"
        )
    if manifest.get("submission_artifact_count") != manifest.get("submission_artifacts_available"):
        blockers.append("manifest reports missing submission artifacts")
    return blockers


def manifest_file_record_blockers(
    archive: tarfile.TarFile,
    manifest: dict[str, Any],
    member_by_relative: dict[str | None, tarfile.TarInfo],
    prefix: str,
) -> list[str]:
    blockers: list[str] = []
    records = manifest.get("files")
    if not isinstance(records, list):
        return blockers
    seen: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            blockers.append(f"manifest file record {index} is not an object")
            continue
        path = record.get("path")
        if not isinstance(path, str) or not path:
            blockers.append(f"manifest file record {index} has invalid path")
            continue
        seen.add(path)
        member = member_by_relative.get(path)
        if member is None:
            blockers.append(f"manifest records missing archive member: {path}")
            continue
        if member.size != record.get("bytes"):
            blockers.append(f"manifest byte count mismatch for {path}")
        actual_sha = archive_member_sha256(archive, f"{prefix}/{path}")
        if actual_sha != record.get("sha256"):
            blockers.append(f"manifest sha256 mismatch for {path}")
    archive_files = {
        path
        for path in member_by_relative
        if path is not None and path != "submission_archive_manifest.json"
    }
    missing_records = sorted(archive_files - seen)
    for path in missing_records:
        blockers.append(f"archive member missing from manifest files: {path}")
    return blockers


def archive_member_sha256(archive: tarfile.TarFile, name: str) -> str:
    handle = archive.extractfile(name)
    if handle is None:
        raise ArchiveError(f"{name} is not a regular file")
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def strip_prefix(name: str, prefix: str) -> str | None:
    exact_prefix = prefix + "/"
    if not name.startswith(exact_prefix):
        return None
    relative = name[len(exact_prefix) :]
    return relative or None


def report(check: ArchiveCheck) -> dict[str, Any]:
    return {
        "archive": str(check.path),
        "archive_prefix": check.prefix,
        "entry_count": len(check.names),
        "manifest_file_count": check.manifest.get("file_count"),
        "submission_artifact_count": check.manifest.get("submission_artifact_count"),
        "submission_artifacts_available": check.manifest.get("submission_artifacts_available"),
        "blockers": check.blockers,
    }


def print_human_summary(check: ArchiveCheck) -> None:
    if check.blockers:
        print("Submission archive blockers:")
        for blocker in check.blockers:
            print(f"- {blocker}")
        return
    print(
        "Submission archive OK: "
        f"{len(check.names)} entries, "
        f"{check.manifest.get('file_count')} manifest files, "
        f"{check.manifest.get('submission_artifacts_available')}/"
        f"{check.manifest.get('submission_artifact_count')} submission artifacts."
    )


class ArchiveError(Exception):
    pass


if __name__ == "__main__":
    sys.exit(main())
