#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Artifact:
    path: Path
    group: str
    purpose: str
    required: bool = True


ARTIFACTS = [
    Artifact(
        Path("manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-application-note.pdf"),
        "journal_upload",
        "Main manuscript PDF.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-supplement.pdf"),
        "journal_upload",
        "Supplementary PDF.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-oup-preview.pdf"),
        "editorial_qc",
        "OUP two-column preview used as a conservative estimate of the four-page Application Note limit.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/main.tex"),
        "source",
        "Main manuscript source.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/supplementary.tex"),
        "source",
        "Supplementary source.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/references.bib"),
        "source",
        "Bibliography.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/figures/graphical_abstract.tex"),
        "source",
        "Reproducible vector source for Figure 1.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/figures/figure_alt_text.md"),
        "source",
        "Accessibility text for Figure 1.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/figures/tcga_trace_ui_analysis.png"),
        "source",
        "Reviewer-facing screenshot of a completed TCGA-TRACE single-gene analysis.",
        required=False,
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/figures/tcga_trace_ui_multiverse.png"),
        "source",
        "Reviewer-facing screenshot of a completed TCGA-TRACE specification family.",
        required=False,
    ),
    Artifact(
        Path("REVIEWER_QUICKSTART.md"),
        "reviewer",
        "Root reviewer entry point.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/submission/artifact_manifest.md"),
        "reviewer",
        "Human-readable artifact map.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/submission/cover_letter_draft.md"),
        "journal_upload",
        "Mandatory Bioinformatics cover-letter draft with owner placeholders.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/submission/data_availability_statement.md"),
        "journal_upload",
        "Prepared data-availability wording for the manuscript and submission form.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/submission/release_and_license_checklist.md"),
        "owner_handoff",
        "Owner-controlled release, license and archive checklist.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/submission/browser_compatibility_record.md"),
        "owner_handoff",
        "Final cross-browser smoke-test record for the public web server.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/submission/reviewer_access_statement.md"),
        "reviewer",
        "Public HTTPS web-server and Docker fallback access statement.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/submission/anticipated_reviewer_response.md"),
        "reviewer",
        "Anticipated reviewer response map.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/submission/reviewer_reproduction_guide.md"),
        "reviewer",
        "Reviewer reproduction guide.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/submission/reviewer_walkthrough.md"),
        "reviewer",
        "Reviewer-facing interface walkthrough.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/submission/submission_readiness_checklist.md"),
        "reviewer",
        "Bioinformatics readiness checklist.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/submission/final_submission_decisions.md"),
        "owner_handoff",
        "Owner-controlled metadata decision tracker.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/submission/owner_metadata.template.json"),
        "owner_handoff",
        "Template for final owner metadata consumed by apply_submission_metadata.py.",
    ),
    Artifact(
        Path("docs/publication/benchmark/README.md"),
        "evidence",
        "Benchmark reproduction and interpretation guide.",
    ),
    Artifact(
        Path("docs/PROJECT_IDENTITY.md"),
        "source",
        "Canonical TCGA-TRACE identity and legacy compatibility contract.",
    ),
    Artifact(
        Path("docs/CLI.md"),
        "software",
        "English standalone public API CLI guide.",
    ),
    Artifact(
        Path("docs/CLI_ES.md"),
        "software",
        "Spanish standalone public API CLI guide.",
    ),
    Artifact(
        Path("docs/publication/benchmark/single_gene_benchmark_overview.md"),
        "evidence",
        "Aggregate single-gene cutpoint-sensitivity result.",
    ),
    Artifact(
        Path("docs/publication/benchmark/skcm_tmem176b_os_cutpoint_benchmark/summary.md"),
        "evidence",
        "TCGA-SKCM TMEM176B exploratory cutpoint benchmark summary.",
    ),
    Artifact(
        Path("docs/publication/benchmark/feature_benchmarks/feature_benchmark_summary.md"),
        "evidence",
        "Feature-level benchmark summary.",
    ),
    Artifact(
        Path("docs/publication/benchmark/feature_benchmarks/signature_definitions.md"),
        "evidence",
        "Feature benchmark signature gene membership and score construction.",
    ),
    Artifact(
        Path("docs/publication/benchmark/immune_pancancer_atlas_v2_1/atlas_summary.json"),
        "evidence",
        "Compact versioned ImmPort pan-cancer atlas result and audit record.",
    ),
    Artifact(
        Path("docs/publication/benchmark/immune_pancancer_atlas_v2_1/README.md"),
        "evidence",
        "ImmPort atlas contract, interpretation and reproducibility guide.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/tables/immune_pancancer_atlas_model_summary.tex"),
        "archived_evidence",
        "Archived ImmPort atlas model-family table; not included in the submitted supplement.",
        required=False,
    ),
    Artifact(
        Path("docs/publication/benchmark/data_snapshot_manifest.json"),
        "evidence",
        "TCGA/CDR/cache data snapshot manifest.",
    ),
    Artifact(
        Path("docs/publication/benchmark/reproducibility_benchmark/summary.md"),
        "evidence",
        "Three-class audit reconstruction and mutation-detection benchmark.",
    ),
    Artifact(
        Path("docs/publication/benchmark/server_attestation/audit_report.json"),
        "evidence",
        "Exact audit report bound by the frozen server receipt.",
    ),
    Artifact(
        Path("docs/publication/benchmark/server_attestation/attestation_receipt.json"),
        "evidence",
        "Detached Ed25519 receipt for the frozen audit report.",
    ),
    Artifact(
        Path("docs/publication/benchmark/server_attestation/public_key.json"),
        "evidence",
        "Archived public key used to verify the frozen receipt.",
    ),
    Artifact(
        Path("docs/publication/benchmark/server_attestation/verification_results.raw.json"),
        "evidence",
        "Positive and negative server-attestation verification controls.",
    ),
    Artifact(
        Path("docs/publication/benchmark/server_attestation/summary.md"),
        "evidence",
        "Human-readable server-attestation benchmark summary.",
    ),
    Artifact(
        Path("docs/publication/benchmark/clean_container_reproduction/benchmark_results.raw.json"),
        "evidence",
        "Pinned clean-container reproduction results across native arm64 and emulated amd64.",
    ),
    Artifact(
        Path("docs/publication/benchmark/clean_container_reproduction/summary.md"),
        "evidence",
        "Human-readable clean-container reproduction summary.",
    ),
    Artifact(
        Path("docs/publication/benchmark/clean_container_reproduction/manifest.json"),
        "evidence",
        "Checksummed clean-container evidence and frozen-capsule manifest.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/tables/reproducibility_benchmark.tex"),
        "source",
        "Generated executable audit reconstruction table.",
    ),
    Artifact(
        Path("docs/publication/benchmark/runtime_concurrency/benchmark_results.raw.json"),
        "evidence",
        "Raw public-API runtime, concurrency and Docker cgroup memory measurements.",
    ),
    Artifact(
        Path("docs/publication/benchmark/runtime_concurrency/summary.csv"),
        "evidence",
        "Machine-readable runtime and concurrency benchmark summary.",
    ),
    Artifact(
        Path("docs/publication/benchmark/runtime_concurrency/summary.md"),
        "evidence",
        "Human-readable runtime, queue-limit and measurement-scope summary.",
    ),
    Artifact(
        Path("docs/publication/benchmark/runtime_concurrency/manifest.json"),
        "evidence",
        "Checksummed runtime benchmark output manifest.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/tables/runtime_concurrency_benchmark.tex"),
        "source",
        "Generated public workflow runtime and memory table.",
    ),
    Artifact(
        Path("docs/publication/benchmark/browser_compatibility/benchmark_results.raw.json"),
        "evidence",
        "Machine-readable Chromium, Firefox/Gecko and WebKit compatibility results.",
    ),
    Artifact(
        Path("docs/publication/benchmark/browser_compatibility/summary.md"),
        "evidence",
        "Human-readable cross-browser compatibility summary.",
    ),
    Artifact(
        Path("docs/publication/benchmark/browser_compatibility/manifest.json"),
        "evidence",
        "Checksummed browser compatibility evidence manifest.",
    ),
    Artifact(
        Path("docs/publication/benchmark/statistical_calibration/calibration_design.json"),
        "evidence",
        "Prespecified permutation and known-truth simulation design.",
    ),
    Artifact(
        Path("docs/publication/benchmark/statistical_calibration/calibration_results.raw.json"),
        "evidence",
        "Statistical calibration results, source hashes and software versions.",
    ),
    Artifact(
        Path("docs/publication/benchmark/statistical_calibration/permutation_replicates.csv"),
        "evidence",
        "Replicate-level observed-cohort null permutation metrics.",
    ),
    Artifact(
        Path("docs/publication/benchmark/statistical_calibration/simulation_replicates.csv"),
        "evidence",
        "Replicate-level known-truth simulation metrics.",
    ),
    Artifact(
        Path("docs/publication/benchmark/statistical_calibration/summary.csv"),
        "evidence",
        "Machine-readable statistical calibration rejection proportions.",
    ),
    Artifact(
        Path("docs/publication/benchmark/statistical_calibration/summary.md"),
        "evidence",
        "Human-readable statistical calibration summary.",
    ),
    Artifact(
        Path("docs/publication/benchmark/statistical_calibration/manifest.json"),
        "evidence",
        "Checksummed statistical calibration output manifest.",
    ),
    Artifact(
        Path("manuscript/bioinformatics_app_note/tables/statistical_calibration.tex"),
        "source",
        "Generated permutation and simulation calibration table.",
    ),
    Artifact(
        Path("docs/publication/benchmark/skcm_sample_rule_sensitivity/README.md"),
        "evidence",
        "TCGA-SKCM PDCD1 sample-type sensitivity record.",
    ),
    Artifact(
        Path("docs/publication/benchmark/skcm_tmem176b_sample_rule_sensitivity/README.md"),
        "evidence",
        "TCGA-SKCM TMEM176B sample-type sensitivity record.",
    ),
    Artifact(
        Path("docs/publication/external_concordance_kmplotter_ca9_kirc.md"),
        "evidence",
        "External KM Plotter concordance record.",
    ),
    Artifact(
        Path("docs/publication/comparator_matrix.md"),
        "evidence",
        "Literature-backed comparator matrix.",
    ),
    Artifact(
        Path("docs/publication/validation_candidate_register.md"),
        "evidence",
        "Literature-prioritized validation and exploratory candidate register.",
    ),
    Artifact(
        Path("docs/BIOINFORMATICS_PUBLICATION_READINESS.md"),
        "evidence",
        "Publication readiness analysis.",
    ),
    Artifact(
        Path("docs/publication/bioinformatics_app_note_strategy.md"),
        "evidence",
        "Bioinformatics Application Note narrative and benchmark strategy.",
    ),
    Artifact(
        Path("docs/publication/application_note_writing_blueprint.md"),
        "editorial_qc",
        "Internal writing blueprint based on Bioinformatics, scientific-writing and REMARK guidance.",
    ),
    Artifact(
        Path("docker-compose.yml"),
        "software",
        "Local Docker orchestration.",
    ),
    Artifact(
        Path("backend/Dockerfile"),
        "software",
        "Backend Docker image definition.",
    ),
    Artifact(
        Path("backend/renv.lock"),
        "software",
        "Exact R dependency lockfile exported with each reproduction capsule.",
    ),
    Artifact(
        Path("backend/app/reproduction_capsule.py"),
        "software",
        "Standalone R reproduction-capsule generator.",
    ),
    Artifact(
        Path("backend/app/attestation.py"),
        "software",
        "Persistent Ed25519 key and detached receipt implementation.",
    ),
    Artifact(
        Path("backend/tests/test_attestation.py"),
        "software",
        "Server-key persistence, signature and mutation regression tests.",
    ),
    Artifact(
        Path("backend/app/session_history.py"),
        "software",
        "Server-resolved exploratory-session family and signed export implementation.",
    ),
    Artifact(
        Path("backend/tests/test_session_history.py"),
        "software",
        "Session deduplication, family separation, privacy and signed-bundle tests.",
    ),
    Artifact(
        Path("frontend/Dockerfile"),
        "software",
        "Frontend Docker image definition.",
    ),
    Artifact(
        Path("frontend/src/sessionHistory.js"),
        "software",
        "Opt-in browser-local run-event history and export payload contract.",
    ),
    Artifact(
        Path("frontend/src/sessionHistory.test.js"),
        "software",
        "Browser-history lifecycle, storage-bound and payload privacy tests.",
    ),
    Artifact(
        Path(".github/workflows/ci.yml"),
        "software",
        "CI workflow for reviewer-visible checks.",
    ),
    Artifact(
        Path(".gitleaks.toml"),
        "software",
        "Secret-scanning policy with narrowly scoped documented false-positive exclusions.",
    ),
    Artifact(
        Path(".github/workflows/release-readiness.yml"),
        "software",
        "Exact-tag release gate for deployed identity, tests, metadata and archive integrity.",
    ),
    Artifact(
        Path("scripts/publication/pre_submission_check.sh"),
        "software",
        "Full local pre-submission gate.",
    ),
    Artifact(
        Path("scripts/publication/apply_submission_metadata.py"),
        "software",
        "Applies final owner metadata to the manuscript, supplement, cover letter and decision tracker.",
    ),
    Artifact(
        Path("scripts/publication/build_submission_archive.py"),
        "software",
        "Compact reviewer/source archive builder.",
    ),
    Artifact(
        Path("scripts/publication/build_oup_preview.py"),
        "software",
        "Generates the synchronized OUP two-column preview source.",
    ),
    Artifact(
        Path("scripts/publication/capture_reviewer_screenshots.py"),
        "software",
        "Regenerates reviewer-facing web interface screenshots from a running app stack.",
    ),
    Artifact(
        Path("scripts/publication/check_submission_artifacts.py"),
        "software",
        "Submission artifact verifier.",
    ),
    Artifact(
        Path("scripts/publication/check_editorial_compliance.py"),
        "software",
        "Checks page, structure, float and alt-text requirements.",
    ),
    Artifact(
        Path("scripts/publication/check_project_identity.py"),
        "software",
        "Prevents legacy display and package names from replacing TCGA-TRACE.",
    ),
    Artifact(
        Path("scripts/publication/check_submission_metadata.py"),
        "software",
        "Owner metadata readiness checker.",
    ),
    Artifact(
        Path("scripts/publication/finalize_submission_package.py"),
        "software",
        "Final owner-metadata, strict-gate and archive handoff runner.",
    ),
    Artifact(
        Path("scripts/publication/export_immune_atlas_benchmark.py"),
        "software",
        "Validates and exports the compact ImmPort atlas publication record.",
    ),
    Artifact(
        Path("scripts/publication/verify_submission_archive.py"),
        "software",
        "Compact reviewer/source archive verifier.",
    ),
    Artifact(
        Path("scripts/publication/verify_reproducibility_bundle.py"),
        "software",
        "Run-bundle reproducibility verifier.",
    ),
    Artifact(
        Path("scripts/tcga_trace_cli.py"),
        "software",
        "Dependency-free public API submit, poll, download and verification CLI.",
    ),
    Artifact(
        Path("scripts/verify_server_attestation.py"),
        "software",
        "Standalone detached Ed25519 receipt verifier.",
    ),
    Artifact(
        Path("scripts/tests/test_verify_server_attestation.py"),
        "software",
        "Standalone verifier positive and negative regression test.",
    ),
    Artifact(
        Path("scripts/tests/test_tcga_trace_cli.py"),
        "software",
        "CLI contract, compute-family and integrity-control tests.",
    ),
    Artifact(
        Path("scripts/publication/run_reproducibility_benchmark.py"),
        "software",
        "Runs the three-class reconstruction and mutation-detection benchmark.",
    ),
    Artifact(
        Path("scripts/publication/run_server_attestation_benchmark.py"),
        "software",
        "Freezes and verifies the server-attestation acceptance controls.",
    ),
    Artifact(
        Path("scripts/publication/tests/test_run_server_attestation_benchmark.py"),
        "software",
        "Frozen server-attestation evidence regression tests.",
    ),
    Artifact(
        Path("scripts/publication/run_runtime_benchmark.py"),
        "software",
        "Measures and validates public workflow runtime, concurrency and memory.",
    ),
    Artifact(
        Path("scripts/publication/run_browser_compatibility.py"),
        "software",
        "Runs and verifies the Chromium, Firefox/Gecko and WebKit UI contract.",
    ),
    Artifact(
        Path("scripts/publication/run_clean_reproduction_benchmark.py"),
        "software",
        "Rebuilds the pinned R image and reruns frozen capsules in isolation.",
    ),
    Artifact(
        Path("scripts/publication/run_statistical_calibration.py"),
        "software",
        "Runs and verifies the permutation and known-truth simulation benchmark.",
    ),
    Artifact(
        Path("scripts/publication/statistical_calibration.R"),
        "software",
        "R statistical calibration engine.",
    ),
    Artifact(
        Path("scripts/publication/write_license_template.py"),
        "software",
        "Writes owner-selected common license text for the final LICENSE file.",
    ),
]


def main() -> int:
    args = parse_args()
    manifest = build_manifest(ROOT)
    if args.json:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    else:
        print_human_summary(manifest)

    failed = bool(manifest["missing_required_artifacts"])
    if args.strict_owner_metadata and manifest["owner_metadata_blockers"]:
        failed = True
    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the submission/reviewer artifact set and report SHA-256 "
            "checksums for files that should be present before journal upload."
        )
    )
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable artifact manifest.")
    parser.add_argument(
        "--strict-owner-metadata",
        action="store_true",
        help="Exit non-zero if owner-controlled metadata blockers are still present.",
    )
    return parser.parse_args()


def build_manifest(root: Path, artifacts: list[Artifact] | None = None) -> dict[str, Any]:
    selected = artifacts or ARTIFACTS
    records = [artifact_record(root, artifact) for artifact in selected]
    missing = [record["path"] for record in records if record["required"] and record["status"] != "available"]
    owner_blockers = load_metadata_checker().collect_blockers(root)
    return {
        "schema_version": "tcga-trace-submission-artifacts-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifact_count": len(records),
        "available_artifact_count": sum(1 for record in records if record["status"] == "available"),
        "missing_required_artifacts": missing,
        "owner_metadata_blockers": owner_blockers,
        "artifacts": records,
    }


def artifact_record(root: Path, artifact: Artifact) -> dict[str, Any]:
    path = root / artifact.path
    record: dict[str, Any] = {
        "path": str(artifact.path),
        "group": artifact.group,
        "purpose": artifact.purpose,
        "required": artifact.required,
    }
    if not path.exists():
        record.update({"status": "missing", "bytes": None, "sha256": None})
        return record
    record.update(
        {
            "status": "available",
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
    )
    return record


def print_human_summary(manifest: dict[str, Any]) -> None:
    print("Submission artifact check:")
    for record in manifest["artifacts"]:
        if record["status"] == "available":
            print(
                f"- OK {record['path']} "
                f"({record['bytes']} bytes, sha256={record['sha256'][:12]}...)"
            )
        else:
            print(f"- MISSING {record['path']}")
    if manifest["missing_required_artifacts"]:
        print("Missing required artifacts:")
        for path in manifest["missing_required_artifacts"]:
            print(f"- {path}")
    else:
        print(f"Submission artifacts OK: {manifest['available_artifact_count']}/{manifest['artifact_count']} available.")

    blockers = manifest["owner_metadata_blockers"]
    if blockers:
        print(f"Owner metadata blockers still present: {len(blockers)}")
        print("Use scripts/publication/check_submission_metadata.py --strict for the detailed blocker list.")
    else:
        print("Owner metadata OK.")


def load_metadata_checker() -> Any:
    path = Path(__file__).with_name("check_submission_metadata.py")
    spec = importlib.util.spec_from_file_location("check_submission_metadata", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    sys.exit(main())
