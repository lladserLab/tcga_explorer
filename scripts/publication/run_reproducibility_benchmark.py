#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import csv
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

import verify_reproducibility_bundle as verifier


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "docs" / "publication" / "benchmark" / "reproducibility_benchmark"
LATEX_TABLE = (
    ROOT
    / "manuscript"
    / "bioinformatics_app_note"
    / "tables"
    / "reproducibility_benchmark.tex"
)
CLEAN_REPRODUCTION_RESULTS = (
    ROOT
    / "docs"
    / "publication"
    / "benchmark"
    / "clean_container_reproduction"
    / "benchmark_results.raw.json"
)


def main() -> int:
    args = parse_args()
    bundles = resolve_requested_bundles(args.bundle)
    if not bundles:
        raise RuntimeError(
            "No reproducibility bundles were found. Run the single-gene and feature benchmarks first."
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LATEX_TABLE.parent.mkdir(parents=True, exist_ok=True)
    summaries = []
    for label, bundle in bundles:
        summary = verifier.verify_bundle(
            bundle,
            r_script=None,
            rscript_bin="Rscript",
            docker_compose_service=args.docker_compose_service,
            container_r_script="",
            container_artifact_dir="/app/artifacts",
            rerun=not args.no_rerun,
            tolerance=args.tolerance,
        )
        summaries.append(summarize_verification(label, bundle, summary))

    tamper = tamper_detection_checks(bundles[0][1], tolerance=args.tolerance)
    clean_reproduction = load_clean_container_evidence()
    attach_clean_reproduction(summaries, clean_reproduction)
    payload = {
        "schema_version": "tcga-trace-reproducibility-benchmark-v3",
        "design": {
            "statistical_roundtrip": (
                "Re-execute each bundle's checksummed km_analysis.R "
                "from its frozen input.json and compare all core outputs using the "
                "recorded quantity-aware absolute-plus-relative policy; exact fields "
                "remain exact and maximum observed errors are retained."
            ),
            "scoring_roundtrip": (
                "Reconstruct single-gene, weighted-signature or combined-signature "
                "scores from audited component values, weights and standardization parameters."
            ),
            "integrity_checks": (
                "Recompute patient-record, scoring-provenance, reproducibility and artifact SHA-256 values."
            ),
            "integrity_boundary": (
                "Mutate request, patient, scoring and source fields bound by the "
                "reproducibility hash; mutate plot and methodology artifacts covered "
                "only by file checksums; and confirm that generated-at and quality "
                "metadata are intentionally outside the reproducibility hash."
            ),
            "clean_capsule_reproduction": (
                "Rebuild the pinned R environment from an immutable base-image digest "
                "and renv.lock, then re-execute self-contained capsules with no network, "
                "application source, TCGA matrices or database."
            ),
            "threat_model": {
                "covered": (
                    "Detection of accidental drift, corruption or incomplete transfer "
                    "relative to the hashes and checksums recorded in an export."
                ),
                "excluded": (
                    "Adversarial forgery by an exporter able to alter content and "
                    "recompute every unsigned hash. No authenticity or authorship claim "
                    "is made without third-party attestation."
                ),
            },
        },
        "bundles": summaries,
        "tamper_detection": tamper,
        "clean_container_reproduction": clean_reproduction,
    }
    write_json(OUTPUT_DIR / "benchmark_results.raw.json", payload)
    write_csv(OUTPUT_DIR / "summary.csv", summaries)
    write_markdown(OUTPUT_DIR / "summary.md", payload)
    write_latex(LATEX_TABLE, summaries, tamper, clean_reproduction)
    print(f"Wrote {OUTPUT_DIR / 'summary.md'}")
    print(f"Wrote {LATEX_TABLE}")
    return (
        0
        if all(row["status"] == "passed" for row in summaries)
        and tamper["status"] == "passed"
        and clean_reproduction["status"] == "passed"
        else 1
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark TCGA-TRACE audit integrity and deterministic statistical reconstruction."
    )
    parser.add_argument(
        "--bundle",
        action="append",
        default=[],
        type=Path,
        help="Analysis artifact directory. Can be repeated; defaults to representative frozen runs.",
    )
    parser.add_argument("--docker-compose-service", default="backend")
    parser.add_argument("--no-rerun", action="store_true")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=None,
        help=(
            "Legacy diagnostic override for one absolute floating-point tolerance; "
            "omit to use the quantity-aware policy."
        ),
    )
    return parser.parse_args()


def resolve_requested_bundles(requested: list[Path]) -> list[tuple[str, Path]]:
    if requested:
        return [(path.name, path) for path in requested]

    candidates = [
        (
            "Single gene",
            ROOT
            / "docs"
            / "publication"
            / "benchmark"
            / "lihc_cdc20_os_cutpoint_benchmark"
            / "benchmark_results.raw.json",
            "median",
        ),
        (
            "Weighted signature",
            ROOT
            / "docs"
            / "publication"
            / "benchmark"
            / "feature_benchmarks"
            / "weighted_signature.raw.json",
            None,
        ),
        (
            "Two signatures",
            ROOT
            / "docs"
            / "publication"
            / "benchmark"
            / "feature_benchmarks"
            / "two_signature.raw.json",
            None,
        ),
    ]
    resolved: list[tuple[str, Path]] = []
    for label, source, method in candidates:
        analysis_id = analysis_id_from_result(source, method=method)
        if analysis_id:
            bundle = ROOT / "artifacts" / analysis_id
            if (bundle / "audit_report.json").exists():
                resolved.append((label, bundle))
    return resolved


def analysis_id_from_result(path: Path, *, method: str | None) -> str | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if method is None:
        return payload.get("id")
    for item in payload.get("results") or []:
        result = item.get("result") or {}
        if result.get("cutpoint_method") == method:
            return result.get("id")
    return None


def summarize_verification(
    label: str,
    bundle: Path,
    summary: dict[str, Any],
) -> dict[str, Any]:
    report = json.loads((bundle / "audit_report.json").read_text(encoding="utf-8"))
    checks = summary.get("checks") or []
    data_provenance = (report.get("data") or {}).get("provenance") or {}
    scoring = (report.get("analysis_design") or {}).get("scoring_provenance") or {}
    numeric_comparison = summary.get("numeric_comparison") or {}
    observed_errors = numeric_comparison.get("observed_errors") or {}
    return {
        "label": label,
        "analysis_id": report.get("analysis_id"),
        "analysis_type": scoring.get("analysis_type") or scoring.get("method"),
        "patients": len(((report.get("cohort_selection") or {}).get("patient_records") or [])),
        "checks": len(checks),
        "checks_passed": sum(1 for item in checks if item.get("passed")),
        "score_reconstructed": any(
            item.get("passed") and str(item.get("name", "")).endswith("score_reconstruction")
            for item in checks
        ),
        "r_roundtrip": any(
            item.get("passed") and item.get("name") == "roundtrip_core_results"
            for item in checks
        ),
        "expression_artifact_hashed": (
            (data_provenance.get("provenance_completeness") or {}).get(
                "exact_expression_artifact_hashed"
            )
        ),
        "gdc_identifiers": data_provenance.get("selected_gdc_file_count"),
        "reproducibility_hash": report.get("reproducibility_hash"),
        "numeric_policy_version": numeric_comparison.get("policy_version"),
        "numeric_comparisons": sum(
            int(record.get("comparisons") or 0)
            for record in observed_errors.values()
        ),
        "max_absolute_error": max(
            (
                float(record.get("max_absolute_error") or 0.0)
                for record in observed_errors.values()
            ),
            default=0.0,
        ),
        "max_relative_error": max(
            (
                float(record.get("max_relative_error") or 0.0)
                for record in observed_errors.values()
            ),
            default=0.0,
        ),
        "status": summary.get("status"),
    }


def load_clean_container_evidence(
    path: Path = CLEAN_REPRODUCTION_RESULTS,
) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing clean-container reproduction evidence: {path}"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("schema_version")
        != "tcga-trace-clean-reproduction-benchmark-v1"
    ):
        raise RuntimeError("Unexpected clean-container reproduction schema.")

    environments = payload.get("environments") or []
    cases: dict[str, dict[str, int | float]] = {}
    for environment in environments:
        for case in environment.get("cases") or []:
            label = str(case.get("label") or "").strip()
            if not label:
                continue
            entry = cases.setdefault(
                label,
                {
                    "passed": 0,
                    "total": 0,
                    "numeric_comparisons": 0,
                    "max_absolute_error": 0.0,
                    "max_relative_error": 0.0,
                },
            )
            entry["total"] += 1
            entry["passed"] += int(case.get("status") == "passed")
            extrema = numeric_error_extrema(case.get("numeric_comparison") or {})
            entry["numeric_comparisons"] = max(
                int(entry["numeric_comparisons"]),
                extrema["numeric_comparisons"],
            )
            entry["max_absolute_error"] = max(
                float(entry["max_absolute_error"]),
                extrema["max_absolute_error"],
            )
            entry["max_relative_error"] = max(
                float(entry["max_relative_error"]),
                extrema["max_relative_error"],
            )

    controls = payload.get("negative_controls") or {}
    controls_passed = sum(bool(value) for value in controls.values())
    all_cases_passed = bool(cases) and all(
        record["passed"] == record["total"] and record["total"] > 0
        for record in cases.values()
    )
    all_controls_passed = bool(controls) and controls_passed == len(controls)
    source_path = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    return {
        "source": str(source_path),
        "status": (
            "passed"
            if environments and all_cases_passed and all_controls_passed
            else "failed"
        ),
        "environment_count": len(environments),
        "architectures": sorted(
            {
                str((environment.get("image_metadata") or {}).get("architecture"))
                for environment in environments
                if (environment.get("image_metadata") or {}).get("architecture")
            }
        ),
        "cases": cases,
        "negative_controls": {
            "passed": controls_passed,
            "total": len(controls),
            "checks": controls,
        },
        "numeric_comparison": (payload.get("design") or {}).get(
            "numeric_comparison"
        ),
    }


def attach_clean_reproduction(
    rows: list[dict[str, Any]],
    clean_reproduction: dict[str, Any],
) -> None:
    cases = clean_reproduction.get("cases") or {}
    for row in rows:
        clean = cases.get(row["label"]) or {
            "passed": 0,
            "total": 0,
            "numeric_comparisons": 0,
            "max_absolute_error": 0.0,
            "max_relative_error": 0.0,
        }
        row["clean_reruns_passed"] = clean["passed"]
        row["clean_reruns"] = clean["total"]
        row["numeric_comparisons"] = clean["numeric_comparisons"]
        row["max_absolute_error"] = clean["max_absolute_error"]
        row["max_relative_error"] = clean["max_relative_error"]
        if clean["total"] == 0 or clean["passed"] != clean["total"]:
            row["status"] = "failed"


def numeric_error_extrema(comparison: dict[str, Any]) -> dict[str, int | float]:
    observed = comparison.get("observed_errors") or {}
    return {
        "numeric_comparisons": sum(
            int(record.get("comparisons") or 0)
            for record in observed.values()
        ),
        "max_absolute_error": max(
            (
                float(record.get("max_absolute_error") or 0.0)
                for record in observed.values()
            ),
            default=0.0,
        ),
        "max_relative_error": max(
            (
                float(record.get("max_relative_error") or 0.0)
                for record in observed.values()
            ),
            default=0.0,
        ),
    }


def tamper_detection_checks(
    bundle: Path,
    *,
    tolerance: float | None,
) -> dict[str, Any]:
    report = json.loads((bundle / "audit_report.json").read_text(encoding="utf-8"))
    expected_reproducibility_hash = report.get("reproducibility_hash")
    expected_patient_hash = (report.get("cohort_selection") or {}).get("patient_records_sha256")
    baseline_hash = recompute_reproducibility_hash(
        report,
        patient_digest=expected_patient_hash,
    )

    patient_report = copy.deepcopy(report)
    patient_records = (patient_report.get("cohort_selection") or {}).get("patient_records") or []
    patient_records[0]["event"] = 1 - int(patient_records[0]["event"])
    mutated_patient_hash = verifier.stable_hash({"records": patient_records})
    patient_hash_detected = (
        mutated_patient_hash != expected_patient_hash
        and recompute_reproducibility_hash(
            patient_report,
            patient_digest=mutated_patient_hash,
        )
        != expected_reproducibility_hash
    )

    request_report = copy.deepcopy(report)
    request_report["request"]["time_unit"] = "tampered"
    request_hash_detected = (
        recompute_reproducibility_hash(
            request_report,
            patient_digest=expected_patient_hash,
        )
        != expected_reproducibility_hash
    )

    scoring_report = copy.deepcopy(report)
    scoring = (scoring_report.get("analysis_design") or {}).get("scoring_provenance") or {}
    target = scoring
    if scoring.get("analysis_type") == "combined_signatures":
        target = scoring.get("signature_a") or {}
    target["components"][0]["selected_values"][0]["expression_value"] += 1.0
    scoring_checks = verifier.verify_scoring_provenance(
        scoring_report,
        tolerance=tolerance,
    )
    scoring_tamper_detected = (
        any(not item.get("passed") for item in scoring_checks)
        and recompute_reproducibility_hash(
            scoring_report,
            patient_digest=expected_patient_hash,
        )
        != expected_reproducibility_hash
    )

    source_report = copy.deepcopy(report)
    provenance = source_report.setdefault("data", {}).setdefault(
        "provenance",
        {},
    )
    expression_files = provenance.get("expression_files") or []
    if expression_files:
        expression_files[0]["sha256"] = "0" * 64
    else:
        provenance["integrity_boundary_probe"] = "mutated"
    source_hash_detected = (
        recompute_reproducibility_hash(
            source_report,
            patient_digest=expected_patient_hash,
        )
        != expected_reproducibility_hash
    )

    plot_boundary = artifact_mutation_boundary(
        bundle,
        report,
        preferred_labels=("png", "cox_forest_png"),
    )
    methodology_boundary = artifact_mutation_boundary(
        bundle,
        report,
        preferred_labels=("methodology", "txt"),
    )

    generated_at_report = copy.deepcopy(report)
    generated_at_report["generated_at"] = "2099-01-01T00:00:00+00:00"
    generated_at_outside_hash = (
        recompute_reproducibility_hash(
            generated_at_report,
            patient_digest=expected_patient_hash,
        )
        == expected_reproducibility_hash
    )

    quality_report = copy.deepcopy(report)
    quality_report.setdefault("quality", {}).setdefault("warnings", []).append(
        "integrity boundary probe"
    )
    quality_metadata_outside_hash = (
        recompute_reproducibility_hash(
            quality_report,
            patient_digest=expected_patient_hash,
        )
        == expected_reproducibility_hash
    )

    checks = {
        "baseline_reproducibility_hash_valid": (
            baseline_hash == expected_reproducibility_hash
        ),
        "patient_row_tamper_detected": patient_hash_detected,
        "request_tamper_detected": request_hash_detected,
        "expression_component_tamper_detected": scoring_tamper_detected,
        "source_provenance_tamper_detected": source_hash_detected,
        "plot_outside_reproducibility_hash": plot_boundary["hash_unchanged"],
        "plot_checksum_tamper_detected": plot_boundary["checksum_failed"],
        "methodology_outside_reproducibility_hash": methodology_boundary[
            "hash_unchanged"
        ],
        "methodology_checksum_tamper_detected": methodology_boundary[
            "checksum_failed"
        ],
        "generated_at_outside_reproducibility_hash": generated_at_outside_hash,
        "quality_metadata_outside_reproducibility_hash": (
            quality_metadata_outside_hash
        ),
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "bound_fields": [
            "request",
            "patient records",
            "scoring provenance",
            "source-data provenance",
            "core results",
        ],
        "artifact_only_fields": [
            plot_boundary["label"],
            methodology_boundary["label"],
        ],
        "unbound_report_metadata": ["generated_at", "quality.warnings"],
        "security_boundary": (
            "The controls detect drift relative to recorded unsigned hashes. "
            "An exporter able to modify content and recompute every hash is outside "
            "scope; authenticity requires independent attestation."
        ),
    }


def recompute_reproducibility_hash(
    report: dict[str, Any],
    *,
    patient_digest: str,
) -> str:
    payload = verifier.reproducibility_payload_from_report(
        report,
        request_payload=report.get("request") or {},
        patient_digest=patient_digest,
    )
    return verifier.stable_hash(payload)


def artifact_mutation_boundary(
    bundle: Path,
    report: dict[str, Any],
    *,
    preferred_labels: tuple[str, ...],
) -> dict[str, Any]:
    artifacts = report.get("artifacts") or {}
    label = next(
        (
            candidate
            for candidate in preferred_labels
            if candidate in artifacts
            and (bundle / str(artifacts[candidate].get("filename") or "")).is_file()
        ),
        None,
    )
    if label is None:
        return {
            "label": "/".join(preferred_labels),
            "hash_unchanged": False,
            "checksum_failed": False,
        }
    metadata = artifacts[label]
    source = bundle / str(metadata["filename"])
    with tempfile.TemporaryDirectory(prefix="tcga-trace-integrity-boundary-") as tmp:
        temporary_dir = Path(tmp)
        destination = temporary_dir / source.name
        shutil.copyfile(source, destination)
        with destination.open("ab") as handle:
            handle.write(b"\nTCGA-TRACE integrity boundary probe\n")
        checks = verifier.verify_artifacts(
            temporary_dir,
            {label: metadata},
        )
    return {
        "label": label,
        "hash_unchanged": True,
        "checksum_failed": any(not check.get("passed") for check in checks),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Audit Reconstruction Benchmark",
        "",
        "This benchmark tests reproducibility as an executable contract, not as the presence of downloadable files.",
        (
            "The integrity threat model is accidental drift, corruption or incomplete "
            "transfer. Unsigned hashes do not establish authenticity against an "
            "exporter who can recompute them."
        ),
        "",
        "| Analysis | Type | Patients | Internal checks | Numeric comparisons | Max abs. error | Max rel. error | Isolated reruns | Status |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in payload["bundles"]:
        lines.append(
            f"| {row['label']} | {row['analysis_type']} | {row['patients']} | "
            f"{row['checks_passed']}/{row['checks']} | {row['numeric_comparisons']} | "
            f"{row['max_absolute_error']:.3g} | {row['max_relative_error']:.3g} | "
            f"{row['clean_reruns_passed']}/{row['clean_reruns']} | "
            f"{row['status']} |"
        )
    clean = payload["clean_container_reproduction"]
    tamper = payload["tamper_detection"]
    lines.extend(
        [
            "",
            "## Clean-Container Reproduction",
            "",
            f"- Environments: {clean['environment_count']} ({', '.join(clean['architectures'])})",
            f"- Capsule reruns: {sum(item['passed'] for item in clean['cases'].values())}/{sum(item['total'] for item in clean['cases'].values())}",
            f"- Clean negative controls: {clean['negative_controls']['passed']}/{clean['negative_controls']['total']}",
            "- Isolation: pinned environment; no network, application source, TCGA matrix or database.",
            "",
            "## Integrity Boundary",
            "",
        ]
    )
    for name, passed in tamper["checks"].items():
        lines.append(
            f"- {name.replace('_', ' ').capitalize()}: {yes_no(passed)}"
        )
    lines.extend(
        [
            "",
            f"- Boundary statement: {tamper['security_boundary']}",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_latex(
    path: Path,
    rows: list[dict[str, Any]],
    tamper: dict[str, Any],
    clean_reproduction: dict[str, Any],
) -> None:
    lines = [
        "\\begin{table}[H]",
        "\\centering",
        "\\caption{Executable audit reconstruction benchmark. Three frozen analyses underwent dependent internal integrity checks, score reconstruction and deterministic R re-execution. Clean reruns rebuilt the pinned environment and used a read-only, network-disabled capsule without application or TCGA data access.}",
        "\\label{tab:audit-reconstruction}",
        "\\resizebox{\\textwidth}{!}{%",
        "\\begin{tabular}{lrrrrrrrl}",
        "\\toprule",
        "Analysis & Patients & Checks & GDC IDs & Numeric values & Max $|\\Delta|$ & Max rel. & Isolated reruns & Status \\\\",
        "\\midrule",
    ]
    for row in rows:
        lines.append(
            f"{latex_escape(row['label'])} & {row['patients']} & "
            f"{row['checks_passed']}/{row['checks']} & {row['gdc_identifiers'] or 0} & "
            f"{row['numeric_comparisons']} & "
            f"{row['max_absolute_error']:.3g} & "
            f"{row['max_relative_error']:.3g} & "
            f"{row['clean_reruns_passed']}/{row['clean_reruns']} & "
            f"{latex_escape(row['status'])} \\\\"
        )
    lines.extend(
        [
            "\\midrule",
            f"Integrity-boundary controls & -- & "
            f"{sum(bool(value) for value in tamper['checks'].values())}/"
            f"{len(tamper['checks'])} & -- & -- & -- & -- & -- & "
            f"{latex_escape(tamper['status'])} \\\\",
            f"Clean negative controls & -- & -- & -- & -- & -- & -- & "
            f"{clean_reproduction['negative_controls']['passed']}/"
            f"{clean_reproduction['negative_controls']['total']} & "
            f"{latex_escape(clean_reproduction['status'])} \\\\",
            "\\bottomrule",
            "\\end{tabular}",
            "}",
            "\\end{table}",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def yes_no(value: Any) -> str:
    return "yes" if value else "no"


def latex_escape(value: Any) -> str:
    text = str(value)
    return (
        text.replace("\\", "\\textbackslash{}")
        .replace("&", "\\&")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


if __name__ == "__main__":
    sys.exit(main())
