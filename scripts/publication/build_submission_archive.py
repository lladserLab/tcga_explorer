#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path("manuscript/bioinformatics_app_note/build/tcga-trace-review-package-draft.tar.gz")
DEFAULT_PREFIX = "tcga-trace-review-package"
REPRODUCIBILITY_SUMMARY = Path(
    "docs/publication/benchmark/reproducibility_benchmark/summary.csv"
)

EXTRA_INCLUDE_PATHS = [
    Path(".gitleaks.toml"),
    Path(".github/workflows/ci.yml"),
    Path(".github/workflows/release-readiness.yml"),
    Path("REVIEWER_QUICKSTART.md"),
    Path("backend/app"),
    Path("backend/app/attestation.py"),
    Path("backend/app/reproduction_capsule.py"),
    Path("backend/renv.lock"),
    Path("backend/scripts"),
    Path("backend/tests"),
    Path("backend/tests/test_attestation.py"),
    Path("docs/publication/benchmark/clean_container_reproduction"),
    Path("docs/publication/benchmark/data_snapshot_manifest.json"),
    Path("docs/publication/benchmark/feature_benchmarks"),
    Path("docs/publication/benchmark/immune_pancancer_atlas_v2_1"),
    Path("docs/publication/benchmark/lgg_emp3_os_cutpoint_benchmark"),
    Path("docs/publication/benchmark/lihc_cdc20_os_cutpoint_benchmark"),
    Path("docs/publication/benchmark/luad_birc5_os_cutpoint_benchmark"),
    Path("docs/publication/benchmark/reproducibility_benchmark"),
    Path("docs/publication/benchmark/server_attestation"),
    Path("docs/publication/benchmark/browser_compatibility"),
    Path("docs/publication/benchmark/runtime_concurrency"),
    Path("docs/publication/benchmark/statistical_calibration"),
    Path("docs/publication/benchmark/skcm_sample_rule_sensitivity"),
    Path("docs/publication/benchmark/skcm_tmem176b_os_cutpoint_benchmark"),
    Path("docs/publication/benchmark/skcm_tmem176b_sample_rule_sensitivity"),
    Path("docs/publication/benchmark/uvm_bap1_dss_cutpoint_benchmark"),
    Path("docs/publication/benchmark_revision_log.md"),
    Path("docs/publication/application_note_writing_blueprint.md"),
    Path("docs/publication/concordance_validation_plan.md"),
    Path("docs/publication/external_concordance_kmplotter_ca9_kirc.md"),
    Path("docs/PROJECT_IDENTITY.md"),
    Path("docs/CLI.md"),
    Path("docs/CLI_ES.md"),
    Path("frontend/public"),
    Path("frontend/src"),
    Path("manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-application-note.pdf"),
    Path("manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-oup-preview.pdf"),
    Path("manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-supplement.pdf"),
    Path("manuscript/bioinformatics_app_note/figures/figure_alt_text.md"),
    Path("manuscript/bioinformatics_app_note/figures/graphical_abstract.tex"),
    Path("manuscript/bioinformatics_app_note/figures/tcga_trace_ui_analysis.png"),
    Path("manuscript/bioinformatics_app_note/figures/tcga_trace_ui_multiverse.png"),
    Path("manuscript/bioinformatics_app_note/submission/anticipated_reviewer_response.md"),
    Path("manuscript/bioinformatics_app_note/submission/browser_compatibility_record.md"),
    Path("manuscript/bioinformatics_app_note/submission/data_availability_statement.md"),
    Path("manuscript/bioinformatics_app_note/submission/owner_metadata.template.json"),
    Path("manuscript/bioinformatics_app_note/submission/release_and_license_checklist.md"),
    Path("manuscript/bioinformatics_app_note/submission/reviewer_access_statement.md"),
    Path("manuscript/bioinformatics_app_note/submission/reviewer_walkthrough.md"),
    Path("manuscript/bioinformatics_app_note/tables/feature_benchmark_diagnostic_summary.tex"),
    Path("manuscript/bioinformatics_app_note/tables/feature_benchmark_summary.tex"),
    Path("manuscript/bioinformatics_app_note/tables/feature_signature_definitions.tex"),
    Path("manuscript/bioinformatics_app_note/tables/immune_pancancer_atlas_model_summary.tex"),
    Path("manuscript/bioinformatics_app_note/tables/reproducibility_benchmark.tex"),
    Path("manuscript/bioinformatics_app_note/tables/runtime_concurrency_benchmark.tex"),
    Path("manuscript/bioinformatics_app_note/tables/statistical_calibration.tex"),
    Path("manuscript/bioinformatics_app_note/tables/lgg_emp3_os_cutpoint_benchmark.tex"),
    Path("manuscript/bioinformatics_app_note/tables/lihc_cdc20_os_cutpoint_benchmark.tex"),
    Path("manuscript/bioinformatics_app_note/tables/luad_birc5_os_cutpoint_benchmark.tex"),
    Path("manuscript/bioinformatics_app_note/tables/single_gene_benchmark_full_overview.tex"),
    Path("manuscript/bioinformatics_app_note/tables/skcm_sample_rule_sensitivity.tex"),
    Path("manuscript/bioinformatics_app_note/tables/skcm_tmem176b_os_cutpoint_benchmark.tex"),
    Path("manuscript/bioinformatics_app_note/tables/skcm_tmem176b_sample_rule_sensitivity.tex"),
    Path("manuscript/bioinformatics_app_note/tables/uvm_bap1_dss_cutpoint_benchmark.tex"),
    Path("scripts/publication/apply_submission_metadata.py"),
    Path("scripts/publication/build_oup_preview.py"),
    Path("scripts/publication/build_submission_archive.py"),
    Path("scripts/publication/capture_reviewer_screenshots.py"),
    Path("scripts/publication/check_editorial_compliance.py"),
    Path("scripts/publication/check_project_identity.py"),
    Path("scripts/publication/check_submission_artifacts.py"),
    Path("scripts/publication/check_submission_metadata.py"),
    Path("scripts/publication/export_data_snapshot_manifest.py"),
    Path("scripts/publication/export_immune_atlas_benchmark.py"),
    Path("scripts/publication/finalize_submission_package.py"),
    Path("scripts/publication/pre_submission_check.sh"),
    Path("scripts/publication/run_reproducibility_benchmark.py"),
    Path("scripts/publication/run_server_attestation_benchmark.py"),
    Path("scripts/publication/run_browser_compatibility.py"),
    Path("scripts/publication/run_runtime_benchmark.py"),
    Path("scripts/publication/run_clean_reproduction_benchmark.py"),
    Path("scripts/publication/run_statistical_calibration.py"),
    Path("scripts/publication/statistical_calibration.R"),
    Path("scripts/publication/run_skcm_sample_rule_sensitivity.py"),
    Path("scripts/publication/tests"),
    Path("scripts/publication/verify_submission_archive.py"),
    Path("scripts/publication/verify_reproducibility_bundle.py"),
    Path("scripts/publication/write_license_template.py"),
    Path("scripts/tcga_trace_cli.py"),
    Path("scripts/tests/test_tcga_trace_cli.py"),
    Path("scripts/tests/test_verify_server_attestation.py"),
    Path("scripts/verify_server_attestation.py"),
]

EXCLUDED_DIR_PREFIXES = [
    ".git",
    "frontend/node_modules",
    "frontend/dist",
    "postgres_data",
    "derived",
    "clinical",
    "jcga",
    "artifacts",
    "logs",
    "attestation_keys",
]

EXCLUDED_SUFFIXES = (
    ".pyc",
    ".log",
    ".tar.gz",
    ".zip",
)

EXCLUDED_FILE_NAMES = {
    "ed25519-private.pem",
}

ALLOWLISTED_RUNTIME_FILES = {
    Path("derived/.gitkeep"),
    Path("clinical/.gitkeep"),
    Path("jcga/.gitkeep"),
    Path("artifacts/.gitkeep"),
}


@dataclass(frozen=True)
class FileRecord:
    path: Path
    bytes: int
    sha256: str


def main() -> int:
    args = parse_args()
    output = Path(args.output)
    output = output if output.is_absolute() else ROOT / output

    artifact_manifest = load_artifact_checker().build_manifest(ROOT)
    if artifact_manifest["missing_required_artifacts"]:
        print("Missing required submission artifacts:", file=sys.stderr)
        for item in artifact_manifest["missing_required_artifacts"]:
            print(f"- {item}", file=sys.stderr)
        return 1
    if args.strict_owner_metadata and artifact_manifest["owner_metadata_blockers"]:
        print("Owner metadata blockers remain:", file=sys.stderr)
        for item in artifact_manifest["owner_metadata_blockers"]:
            print(f"- {item}", file=sys.stderr)
        return 1

    records = collect_file_records(ROOT, output)
    manifest = build_archive_manifest(records, artifact_manifest, args.prefix, output)
    if args.json or args.dry_run:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    if args.dry_run:
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    write_archive(ROOT, output, args.prefix, records, manifest)
    display_output = output.relative_to(ROOT) if is_relative_to(output, ROOT) else output
    print(
        f"Wrote {display_output} "
        f"({output.stat().st_size} bytes, sha256={file_sha256(output)})"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a compact TCGA-TRACE reviewer/submission source archive. "
            "The archive includes source, manuscript PDFs, compact benchmark "
            "evidence, three reconstruction bundles and frozen standalone R capsules, while excluding full TCGA "
            "matrices, derived caches and large local analysis output."
        )
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output .tar.gz path.")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="Top-level directory name inside the archive.")
    parser.add_argument("--dry-run", action="store_true", help="Report the archive manifest without writing an archive.")
    parser.add_argument("--json", action="store_true", help="Emit the manifest JSON.")
    parser.add_argument(
        "--strict-owner-metadata",
        action="store_true",
        help="Fail if author/license/repository/DOI placeholders remain.",
    )
    return parser.parse_args()


def collect_file_records(root: Path, output: Path) -> list[FileRecord]:
    paths = set(tracked_files(root))
    for extra in EXTRA_INCLUDE_PATHS:
        paths.update(existing_files(root, extra))
    reproducibility_bundles = reproducibility_bundle_paths(root)
    for bundle in reproducibility_bundles:
        paths.update(existing_files(root, bundle))
    output_relative = relative_to_root(root, output)
    filtered = [
        path
        for path in paths
        if should_include(
            path,
            output_relative,
            allowed_artifact_bundles=reproducibility_bundles,
        )
    ]
    return [file_record(root, path) for path in sorted(filtered)]


def tracked_files(root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]


def existing_files(root: Path, relative_path: Path) -> list[Path]:
    path = root / relative_path
    if not path.exists():
        return []
    if path.is_file():
        return [relative_path]
    return [
        item.relative_to(root)
        for item in path.rglob("*")
        if item.is_file()
    ]


def should_include(
    path: Path,
    output_relative: Path | None = None,
    *,
    allowed_artifact_bundles: tuple[Path, ...] | None = None,
) -> bool:
    if output_relative and path == output_relative:
        return False
    if path.name == ".DS_Store":
        return False
    if path.name in EXCLUDED_FILE_NAMES:
        return False
    if any(str(path).endswith(suffix) for suffix in EXCLUDED_SUFFIXES):
        return False
    if path in ALLOWLISTED_RUNTIME_FILES:
        return True
    bundles = (
        reproducibility_bundle_paths(ROOT)
        if allowed_artifact_bundles is None
        else allowed_artifact_bundles
    )
    if any(is_relative_to(path, bundle) for bundle in bundles):
        return True
    if is_allowed_build_pdf(path):
        return True
    parts = path.parts
    for prefix in EXCLUDED_DIR_PREFIXES:
        prefix_parts = Path(prefix).parts
        if parts[: len(prefix_parts)] == prefix_parts:
            return False
    return True


def reproducibility_bundle_paths(root: Path) -> tuple[Path, ...]:
    summary_path = root / REPRODUCIBILITY_SUMMARY
    if not summary_path.is_file():
        return ()
    import csv

    with summary_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return tuple(
        Path("artifacts") / analysis_id
        for analysis_id in (str(row.get("analysis_id") or "").strip() for row in rows)
        if analysis_id
    )


def is_allowed_build_pdf(path: Path) -> bool:
    return path in {
        Path("manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-application-note.pdf"),
        Path("manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-supplement.pdf"),
    }


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def relative_to_root(root: Path, path: Path) -> Path | None:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return None


def file_record(root: Path, path: Path) -> FileRecord:
    absolute = root / path
    return FileRecord(path=path, bytes=absolute.stat().st_size, sha256=file_sha256(absolute))


def build_archive_manifest(
    records: list[FileRecord],
    artifact_manifest: dict[str, Any],
    prefix: str,
    output: Path,
) -> dict[str, Any]:
    return {
        "schema_version": "tcga-trace-review-archive-v1",
        "project_name": "TCGA-TRACE",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "archive_prefix": prefix,
        "output": str(output.relative_to(ROOT)) if is_relative_to(output, ROOT) else str(output),
        "file_count": len(records),
        "total_uncompressed_bytes": sum(record.bytes for record in records),
        "owner_metadata_blockers": artifact_manifest["owner_metadata_blockers"],
        "submission_artifact_count": artifact_manifest["artifact_count"],
        "submission_artifacts_available": artifact_manifest["available_artifact_count"],
        "excluded_runtime_data": [
            "full TCGA RNA-seq matrices mounted from ../TCGA",
            "derived/rna_bulk expression matrix caches",
            "full local artifacts except the three reconstruction-benchmark bundles",
            "clinical and JCGA local data except placeholder .gitkeep files",
            "frontend/node_modules and frontend/dist",
            "server attestation private keys and key-volume contents",
        ],
        "files": [
            {"path": str(record.path), "bytes": record.bytes, "sha256": record.sha256}
            for record in records
        ],
    }


def write_archive(
    root: Path,
    output: Path,
    prefix: str,
    records: list[FileRecord],
    manifest: dict[str, Any],
) -> None:
    with tarfile.open(output, mode="w:gz", format=tarfile.PAX_FORMAT) as archive:
        for record in records:
            archive.add(root / record.path, arcname=str(Path(prefix) / record.path), recursive=False)
        manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
        info = tarfile.TarInfo(str(Path(prefix) / "submission_archive_manifest.json"))
        info.size = len(manifest_bytes)
        info.mtime = int(datetime.now(timezone.utc).timestamp())
        archive.addfile(info, fileobj=io.BytesIO(manifest_bytes))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_artifact_checker() -> Any:
    path = Path(__file__).with_name("check_submission_artifacts.py")
    spec = importlib.util.spec_from_file_location("check_submission_artifacts", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    sys.exit(main())
