#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.reproduction_capsule import (  # noqa: E402
    REPRODUCTION_TOLERANCE_POLICY,
    REPRODUCTION_TOLERANCE_POLICY_VERSION,
)

FROZEN_R_SCRIPT_RELATIVE = Path("km_analysis.R")
DEFAULT_CONTAINER_ARTIFACT_DIR = "/app/artifacts"
ROUNDTRIP_CORE_KEYS = [
    "n_patients",
    "n_events",
    "group_counts",
    "event_counts",
    "median_survival_days",
    "median_survival_status",
    "rmst",
    "logrank_p_value",
    "hazard_ratio",
    "hr_conf_low",
    "hr_conf_high",
    "hr_p_value",
    "cox_models",
    "signature_interaction_cox_models",
]


def main() -> int:
    args = parse_args()
    summaries = [
        verify_bundle(
            path,
            r_script=args.r_script,
            rscript_bin=args.rscript_bin,
            docker_compose_service=args.docker_compose_service,
            container_r_script=args.container_r_script,
            container_artifact_dir=args.container_artifact_dir,
            rerun=args.rerun,
            tolerance=args.tolerance,
        )
        for path in args.bundle
    ]
    if args.json:
        print(json.dumps(summaries, indent=2, sort_keys=True))
    else:
        for summary in summaries:
            print_summary(summary)
    return 0 if all(item["status"] == "passed" for item in summaries) else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a TCGA-TRACE local analysis bundle. By default this checks "
            "patient-record hashes, reproducibility hash definition and artifact "
            "checksums. With --rerun it re-executes the bundle's checksummed "
            "km_analysis.R from input.json and compares core "
            "statistical outputs."
        )
    )
    parser.add_argument("bundle", nargs="+", type=Path, help="Analysis artifact directory or audit_report.json path.")
    parser.add_argument("--rerun", action="store_true", help="Re-run km_analysis.R from input.json and compare results.")
    parser.add_argument(
        "--r-script",
        type=Path,
        default=None,
        help=(
            "Explicit local R-engine override. By default --rerun uses the "
            "checksummed km_analysis.R stored in each bundle."
        ),
    )
    parser.add_argument("--rscript-bin", default="Rscript")
    parser.add_argument(
        "--docker-compose-service",
        default="",
        help="Run the R round-trip inside this docker compose service instead of local Rscript.",
    )
    parser.add_argument(
        "--container-r-script",
        default="",
        help=(
            "Explicit R-engine path inside the compose service. When omitted, "
            "the verifier derives the frozen bundle path under /app/artifacts."
        ),
    )
    parser.add_argument("--container-artifact-dir", default=DEFAULT_CONTAINER_ARTIFACT_DIR)
    parser.add_argument(
        "--tolerance",
        type=float,
        default=None,
        help=(
            "Legacy diagnostic override: use one absolute tolerance for every "
            "non-exact numeric class. The default is the recorded quantity-aware "
            "absolute-plus-relative policy."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Write machine-readable JSON summary.")
    return parser.parse_args()


def verify_bundle(
    path: Path,
    *,
    r_script: Path | None,
    rscript_bin: str,
    docker_compose_service: str,
    container_r_script: str,
    container_artifact_dir: str,
    rerun: bool,
    tolerance: float | None,
) -> dict[str, Any]:
    bundle_dir, audit_path = resolve_bundle(path)
    checks: list[dict[str, Any]] = []
    report = read_json(audit_path)

    patient_records = ((report.get("cohort_selection") or {}).get("patient_records") or [])
    patient_digest = stable_hash({"records": patient_records})
    expected_patient_digest = (report.get("cohort_selection") or {}).get("patient_records_sha256")
    checks.append(check_equal("patient_records_sha256", patient_digest, expected_patient_digest))

    request_payload = report.get("request")
    if request_payload is None:
        checks.append(fail("request_payload_present", "audit_report.json does not include the full request payload. Re-run the analysis with the current code."))
    else:
        reproducibility_payload = reproducibility_payload_from_report(
            report,
            request_payload=request_payload,
            patient_digest=patient_digest,
        )
        recomputed = stable_hash(reproducibility_payload)
        checks.append(check_equal("reproducibility_hash", recomputed, report.get("reproducibility_hash")))

    checks.extend(verify_scoring_provenance(report, tolerance=tolerance))
    checks.extend(verify_artifacts(bundle_dir, report.get("artifacts") or {}))

    if rerun:
        checks.extend(
            rerun_and_compare(
                bundle_dir,
                report,
                r_script=r_script,
                rscript_bin=rscript_bin,
                docker_compose_service=docker_compose_service,
                container_r_script=container_r_script,
                container_artifact_dir=container_artifact_dir,
                tolerance=tolerance,
            )
        )

    status = "passed" if all(item["passed"] for item in checks) else "failed"
    return {
        "bundle": str(bundle_dir),
        "audit_report": str(audit_path),
        "analysis_id": report.get("analysis_id"),
        "status": status,
        "checks": checks,
        "numeric_comparison": aggregate_check_comparisons(checks),
    }


def reproducibility_payload_from_report(
    report: dict[str, Any],
    *,
    request_payload: dict[str, Any],
    patient_digest: str,
) -> dict[str, Any]:
    data = report.get("data") or {}
    analysis_design = report.get("analysis_design") or {}
    if report.get("schema_version") in {
        "tcga-trace-analysis-audit-v4",
        "tcga-trace-analysis-audit-v3",
    }:
        continuous_records = (
            (report.get("cohort_selection") or {}).get("continuous_patient_records")
            or []
        )
        continuous_record_digest = (
            stable_hash({"records": continuous_records})
            if continuous_records
            else None
        )
        scoring_provenance = analysis_design.get("scoring_provenance") or {}
        return {
            "request": request_payload,
            "data_dates": data.get("data_dates") or {},
            "data_provenance": data.get("provenance") or {},
            "scoring_provenance_sha256": stable_hash(scoring_provenance),
            "record_digest": patient_digest,
            "continuous_record_digest": continuous_record_digest,
            "core_results": report.get("results") or {},
        }
    if report.get("schema_version") == "tcga-trace-analysis-audit-v2":
        scoring_provenance = analysis_design.get("scoring_provenance") or {}
        return {
            "request": request_payload,
            "data_dates": data.get("data_dates") or {},
            "data_provenance": data.get("provenance") or {},
            "scoring_provenance_sha256": stable_hash(scoring_provenance),
            "record_digest": patient_digest,
            "core_results": report.get("results") or {},
        }
    return {
        "request": request_payload,
        "data_dates": data.get("data_dates") or {},
        "record_digest": patient_digest,
        "core_results": report.get("results") or {},
    }


def verify_scoring_provenance(
    report: dict[str, Any],
    *,
    tolerance: float | None,
) -> list[dict[str, Any]]:
    analysis_design = report.get("analysis_design") or {}
    provenance = analysis_design.get("scoring_provenance")
    expected_digest = analysis_design.get("scoring_provenance_sha256")
    if not provenance:
        if report.get("schema_version") == "tcga-trace-analysis-audit-v2":
            return [fail("scoring_provenance_present", "Audit v2 does not include scoring provenance.")]
        return [pass_check("scoring_provenance_legacy", "Legacy audit predates scoring provenance.")]

    checks = [
        check_equal(
            "scoring_provenance_sha256",
            stable_hash(provenance),
            expected_digest,
        )
    ]
    records = ((report.get("cohort_selection") or {}).get("patient_records") or [])
    if provenance.get("analysis_type") == "combined_signatures":
        checks.extend(
            verify_one_score(
                provenance.get("signature_a") or {},
                records,
                record_field="expression_value_a",
                check_prefix="signature_a",
                tolerance=tolerance,
            )
        )
        checks.extend(
            verify_one_score(
                provenance.get("signature_b") or {},
                records,
                record_field="expression_value_b",
                check_prefix="signature_b",
                tolerance=tolerance,
            )
        )
    else:
        checks.extend(
            verify_one_score(
                provenance,
                records,
                record_field="expression_value",
                check_prefix="signature",
                tolerance=tolerance,
            )
        )
    return checks


def verify_one_score(
    provenance: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    record_field: str,
    check_prefix: str,
    tolerance: float | None,
) -> list[dict[str, Any]]:
    components = provenance.get("components") or []
    score_values = provenance.get("score_values") or []
    checks: list[dict[str, Any]] = []
    if not components or not score_values:
        return [fail(f"{check_prefix}_components_present", "Scoring components or score values are missing.")]

    for component in components:
        selected_values = component.get("selected_values") or []
        checks.append(
            check_equal(
                f"{check_prefix}_{component.get('resolved_symbol')}_component_hash",
                stable_hash({"values": selected_values}),
                component.get("selected_values_sha256"),
            )
        )
    checks.append(
        check_equal(
            f"{check_prefix}_score_values_hash",
            stable_hash({"values": score_values}),
            provenance.get("score_values_sha256"),
        )
    )

    recomputed = recompute_scores(provenance)
    declared = {
        str(item.get("sample_barcode")): item.get("score")
        for item in score_values
    }
    score_comparison = compare_values_detailed(
        declared,
        recomputed,
        tolerance=tolerance,
    )
    if score_comparison["differences"]:
        checks.append(
            fail(
                f"{check_prefix}_score_reconstruction",
                {
                    "message": "; ".join(score_comparison["differences"][:10]),
                    "comparison": score_comparison,
                },
            )
        )
    else:
        checks.append(
            pass_check(
                f"{check_prefix}_score_reconstruction",
                {
                    "message": "Scores reconstruct from audited component values.",
                    "comparison": score_comparison,
                },
            )
        )

    record_scores = {
        str(record.get("sample_barcode")): record.get(record_field)
        for record in records
    }
    expected_record_scores = {
        barcode: declared.get(barcode)
        for barcode in record_scores
    }
    record_comparison = compare_values_detailed(
        record_scores,
        expected_record_scores,
        tolerance=tolerance,
    )
    if record_comparison["differences"]:
        checks.append(
            fail(
                f"{check_prefix}_record_scores",
                {
                    "message": "; ".join(record_comparison["differences"][:10]),
                    "comparison": record_comparison,
                },
            )
        )
    else:
        checks.append(
            pass_check(
                f"{check_prefix}_record_scores",
                {
                    "message": "Patient records match reconstructed audited scores.",
                    "comparison": record_comparison,
                },
            )
        )
    return checks


def recompute_scores(provenance: dict[str, Any]) -> dict[str, float]:
    components = provenance.get("components") or []
    method = provenance.get("method")
    values_by_gene = {
        str(component.get("resolved_symbol")): {
            str(item.get("sample_barcode")): float(item.get("expression_value"))
            for item in component.get("selected_values") or []
        }
        for component in components
    }
    barcodes = sorted(set.intersection(*(set(values) for values in values_by_gene.values())))
    denominator = float(provenance.get("weight_denominator") or 1.0)
    scores: dict[str, float] = {}
    for barcode in barcodes:
        if method == "single":
            scores[barcode] = next(iter(values_by_gene.values()))[barcode]
        elif method == "mean":
            scores[barcode] = sum(values[barcode] for values in values_by_gene.values()) / len(values_by_gene)
        elif method == "weighted":
            scores[barcode] = sum(
                float(component.get("weight") or 0.0)
                * values_by_gene[str(component.get("resolved_symbol"))][barcode]
                for component in components
            ) / denominator
        elif method == "zscore":
            scores[barcode] = sum(
                float(component.get("weight") or 0.0)
                * (
                    values_by_gene[str(component.get("resolved_symbol"))][barcode]
                    - float((component.get("standardization") or {}).get("center"))
                )
                / float((component.get("standardization") or {}).get("sample_standard_deviation"))
                for component in components
            ) / denominator
        else:
            raise ValueError(f"Unsupported audited scoring method: {method}")
    return scores


def resolve_bundle(path: Path) -> tuple[Path, Path]:
    if path.is_dir():
        return path, path / "audit_report.json"
    return path.parent, path


def verify_artifacts(bundle_dir: Path, artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for label, metadata in sorted(artifacts.items()):
        filename = metadata.get("filename")
        if not filename:
            checks.append(fail(f"artifact_{label}_filename", "Artifact entry has no filename."))
            continue
        artifact_path = bundle_dir / filename
        if not artifact_path.exists():
            checks.append(fail(f"artifact_{label}_exists", f"{artifact_path} does not exist."))
            continue
        checks.append(check_equal(f"artifact_{label}_bytes", artifact_path.stat().st_size, metadata.get("bytes")))
        checks.append(check_equal(f"artifact_{label}_sha256", file_sha256(artifact_path), metadata.get("sha256")))
    return checks


def rerun_and_compare(
    bundle_dir: Path,
    report: dict[str, Any],
    *,
    r_script: Path | None,
    rscript_bin: str,
    docker_compose_service: str,
    container_r_script: str,
    container_artifact_dir: str,
    tolerance: float | None,
) -> list[dict[str, Any]]:
    input_path = bundle_dir / "input.json"
    if not input_path.exists():
        return [fail("roundtrip_input_json", f"{input_path} does not exist.")]
    use_container = bool(docker_compose_service)
    selected_r_script = select_roundtrip_r_script(bundle_dir, r_script)
    if not selected_r_script.exists():
        return [
            fail(
                "roundtrip_r_script",
                f"{selected_r_script} does not exist; the frozen bundle engine is required.",
            )
        ]

    payload = read_json(input_path)
    temp_kwargs: dict[str, Any] = {"prefix": "tcga-trace-rerun-"}
    if use_container:
        try:
            bundle_rel = bundle_dir.resolve().relative_to((ROOT / "artifacts").resolve())
        except ValueError:
            return [fail("roundtrip_container_bundle_path", f"{bundle_dir} is not under {ROOT / 'artifacts'}.")]
        selected_container_r_script = select_container_roundtrip_r_script(
            bundle_rel,
            container_artifact_dir=container_artifact_dir,
            override=container_r_script,
        )
        temp_kwargs["dir"] = bundle_dir
    else:
        bundle_rel = None
        selected_container_r_script = ""

    with tempfile.TemporaryDirectory(**temp_kwargs) as tmp:
        tmp_dir = Path(tmp)
        host_output_path = tmp_dir / "metrics.json"
        if use_container:
            container_tmp_dir = PurePosixPath(container_artifact_dir) / PurePosixPath(bundle_rel.as_posix()) / tmp_dir.name
            container_output_path = container_tmp_dir / "metrics.json"
            payload["output_path"] = str(container_output_path)
            payload["png_path"] = str(container_tmp_dir / "plot.png")
            payload["svg_path"] = str(container_tmp_dir / "plot.svg")
            payload["cox_forest_png_path"] = str(container_tmp_dir / "cox_forest.png")
            payload["cox_forest_svg_path"] = str(container_tmp_dir / "cox_forest.svg")
        else:
            payload["output_path"] = str(host_output_path)
            payload["png_path"] = str(tmp_dir / "plot.png")
            payload["svg_path"] = str(tmp_dir / "plot.svg")
            payload["cox_forest_png_path"] = str(tmp_dir / "cox_forest.png")
            payload["cox_forest_svg_path"] = str(tmp_dir / "cox_forest.svg")
        payload["render_png"] = False
        payload["render_svg"] = False
        rerun_input = tmp_dir / "input.json"
        rerun_input.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        if use_container:
            container_input_path = PurePosixPath(payload["output_path"]).with_name("input.json")
            command = [
                "docker",
                "compose",
                "run",
                "--rm",
                "--no-deps",
                docker_compose_service,
                "Rscript",
                selected_container_r_script,
                str(container_input_path),
            ]
        else:
            command = [rscript_bin, str(selected_r_script), str(rerun_input)]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=240,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            runner = docker_compose_service if use_container else rscript_bin
            return [fail("roundtrip_rscript", detail[:1000] or f"{runner} exited with {result.returncode}.")]
        metrics = read_json(host_output_path)

    rerun_core = core_results_from_metrics(metrics)
    expected_core = roundtrip_core_results(report.get("results") or {})
    comparison = compare_values_detailed(
        expected_core,
        rerun_core,
        tolerance=tolerance,
    )
    if comparison["differences"]:
        return [
            fail(
                "roundtrip_core_results",
                {
                    "message": "; ".join(comparison["differences"][:10]),
                    "comparison": comparison,
                },
            )
        ]
    return [
        pass_check(
            "roundtrip_core_results",
            {
                "message": "Rerun core statistical outputs match audit_report.json.",
                "comparison": comparison,
            },
        )
    ]


def select_roundtrip_r_script(bundle_dir: Path, override: Path | None) -> Path:
    return override or (bundle_dir / FROZEN_R_SCRIPT_RELATIVE)


def select_container_roundtrip_r_script(
    bundle_relative: Path,
    *,
    container_artifact_dir: str,
    override: str,
) -> str:
    if override:
        return override
    return str(
        PurePosixPath(container_artifact_dir)
        / PurePosixPath(bundle_relative.as_posix())
        / PurePosixPath(FROZEN_R_SCRIPT_RELATIVE.as_posix())
    )


def core_results_from_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    median_status = median_survival_status(metrics)
    return roundtrip_core_results({
        "n_patients": metrics.get("n_patients"),
        "n_events": metrics.get("n_events"),
        "group_counts": metrics.get("group_counts") or {},
        "event_counts": metrics.get("event_counts") or {},
        "median_survival_days": metrics.get("median_survival_days") or {},
        "median_survival_status": median_status,
        "rmst": metrics.get("rmst"),
        "logrank_p_value": metrics.get("logrank_p_value"),
        "hazard_ratio": metrics.get("hazard_ratio"),
        "hr_conf_low": metrics.get("hr_conf_low"),
        "hr_conf_high": metrics.get("hr_conf_high"),
        "hr_p_value": metrics.get("hr_p_value"),
        "cox_models": metrics.get("cox_models") or [],
        "signature_interaction_cox_models": metrics.get("signature_interaction_cox_models") or [],
    })


def roundtrip_core_results(results: dict[str, Any]) -> dict[str, Any]:
    return {key: results.get(key) for key in ROUNDTRIP_CORE_KEYS}


def median_survival_status(metrics: dict[str, Any]) -> dict[str, Any]:
    medians = metrics.get("median_survival_days") or {}
    status = {}
    for group, value in medians.items():
        if value is None:
            status[group] = {
                "status": "not_reached",
                "explanation": "The Kaplan-Meier curve did not fall to or below 50% survival in this group, so median survival was not reached.",
            }
        else:
            status[group] = {
                "status": "estimated",
                "explanation": "Median survival was reached and estimated from the Kaplan-Meier curve.",
            }
    return status


def compare_values(
    left: Any,
    right: Any,
    *,
    tolerance: float | None = None,
    path: str = "$",
) -> list[str]:
    return compare_values_detailed(
        left,
        right,
        tolerance=tolerance,
        path=path,
    )["differences"]


def compare_values_detailed(
    left: Any,
    right: Any,
    *,
    tolerance: float | None = None,
    path: str = "$",
) -> dict[str, Any]:
    observed_errors = {
        class_name: {
            "comparisons": 0,
            "max_absolute_error": 0.0,
            "max_relative_error": 0.0,
            "max_absolute_path": None,
            "max_relative_path": None,
        }
        for class_name in REPRODUCTION_TOLERANCE_POLICY
    }
    differences: list[str] = []

    def visit(expected: Any, observed: Any, current_path: str) -> None:
        if isinstance(expected, dict) and isinstance(observed, dict):
            for key in sorted(set(expected) | set(observed)):
                visit(
                    expected.get(key),
                    observed.get(key),
                    f"{current_path}.{key}",
                )
            return
        if isinstance(expected, list) and isinstance(observed, list):
            if len(expected) != len(observed):
                differences.append(
                    f"{current_path}: length {len(expected)} != {len(observed)}"
                )
                return
            for index, (expected_item, observed_item) in enumerate(
                zip(expected, observed)
            ):
                visit(
                    expected_item,
                    observed_item,
                    f"{current_path}[{index}]",
                )
            return
        if is_numeric_scalar(expected) or is_numeric_scalar(observed):
            if not (
                is_numeric_scalar(expected) and is_numeric_scalar(observed)
            ):
                differences.append(
                    f"{current_path}: {expected!r} != {observed!r}"
                )
                return
            class_name = metric_class_for_path(current_path)
            policy = tolerance_for_class(class_name, tolerance=tolerance)
            expected_number = float(expected)
            observed_number = float(observed)
            absolute_error = abs(expected_number - observed_number)
            scale = max(abs(expected_number), abs(observed_number))
            relative_error = absolute_error / scale if scale else 0.0
            limit = policy["absolute"] + policy["relative"] * scale
            class_errors = observed_errors[class_name]
            class_errors["comparisons"] += 1
            if absolute_error >= class_errors["max_absolute_error"]:
                class_errors["max_absolute_error"] = absolute_error
                class_errors["max_absolute_path"] = current_path
            if relative_error >= class_errors["max_relative_error"]:
                class_errors["max_relative_error"] = relative_error
                class_errors["max_relative_path"] = current_path
            if absolute_error > limit:
                differences.append(
                    f"{current_path} [{class_name}]: {expected!r} != "
                    f"{observed!r} (abs {absolute_error:.6g} > {limit:.6g})"
                )
            return
        if expected != observed:
            differences.append(
                f"{current_path}: {expected!r} != {observed!r}"
            )

    visit(left, right, path)
    return {
        "policy_version": REPRODUCTION_TOLERANCE_POLICY_VERSION,
        "pass_rule": (
            "absolute_error <= absolute + relative * "
            "max(abs(expected), abs(observed))"
        ),
        "classes": {
            class_name: tolerance_for_class(
                class_name,
                tolerance=tolerance,
            )
            for class_name in REPRODUCTION_TOLERANCE_POLICY
        },
        "legacy_absolute_override": tolerance,
        "observed_errors": observed_errors,
        "differences": differences,
    }


def metric_class_for_path(path: str) -> str:
    lower = path.lower()
    exact_fragments = (
        ".group_counts.",
        ".event_counts.",
    )
    exact_suffixes = (
        ".n_patients",
        ".n_events",
        ".parameter_count",
        ".degrees_of_freedom",
    )
    if any(fragment in lower for fragment in exact_fragments) or lower.endswith(
        exact_suffixes
    ):
        return "exact"
    if any(
        fragment in lower
        for fragment in ("p_value", "q_value", "fdr", "probability", "alpha")
    ):
        return "probability"
    if any(
        fragment in lower
        for fragment in ("time", "days", "tau", "rmst", "median_survival")
    ):
        return "time"
    if any(
        fragment in lower
        for fragment in (
            "hazard_ratio",
            "hr_conf",
            "log_hr",
            "standard_error",
            "coefficient",
            "estimate",
            "expression",
            "score",
            "center",
            "deviation",
            "threshold",
        )
    ):
        return "effect"
    return "generic"


def tolerance_for_class(
    class_name: str,
    *,
    tolerance: float | None,
) -> dict[str, float]:
    policy = dict(REPRODUCTION_TOLERANCE_POLICY[class_name])
    if tolerance is not None and class_name != "exact":
        return {"absolute": float(tolerance), "relative": 0.0}
    return policy


def is_numeric_scalar(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def aggregate_check_comparisons(
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    aggregate = {
        class_name: {
            "comparisons": 0,
            "max_absolute_error": 0.0,
            "max_relative_error": 0.0,
            "max_absolute_path": None,
            "max_relative_path": None,
        }
        for class_name in REPRODUCTION_TOLERANCE_POLICY
    }
    comparison_count = 0
    for check in checks:
        detail = check.get("detail")
        if not isinstance(detail, dict):
            continue
        comparison = detail.get("comparison")
        if not isinstance(comparison, dict):
            continue
        comparison_count += 1
        for class_name, observed in (
            comparison.get("observed_errors") or {}
        ).items():
            target = aggregate.get(class_name)
            if target is None:
                continue
            target["comparisons"] += int(observed.get("comparisons") or 0)
            if float(observed.get("max_absolute_error") or 0.0) >= float(
                target["max_absolute_error"]
            ):
                target["max_absolute_error"] = float(
                    observed.get("max_absolute_error") or 0.0
                )
                target["max_absolute_path"] = observed.get("max_absolute_path")
            if float(observed.get("max_relative_error") or 0.0) >= float(
                target["max_relative_error"]
            ):
                target["max_relative_error"] = float(
                    observed.get("max_relative_error") or 0.0
                )
                target["max_relative_path"] = observed.get("max_relative_path")
    return {
        "policy_version": REPRODUCTION_TOLERANCE_POLICY_VERSION,
        "classes": REPRODUCTION_TOLERANCE_POLICY,
        "comparison_sets": comparison_count,
        "observed_errors": aggregate,
    }


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def stable_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_equal(name: str, observed: Any, expected: Any) -> dict[str, Any]:
    if observed == expected:
        return pass_check(name, observed)
    return fail(name, f"observed {observed!r}, expected {expected!r}")


def pass_check(name: str, detail: Any) -> dict[str, Any]:
    return {"name": name, "passed": True, "detail": detail}


def fail(name: str, detail: Any) -> dict[str, Any]:
    return {"name": name, "passed": False, "detail": detail}


def print_summary(summary: dict[str, Any]) -> None:
    print(f"{summary['status'].upper()} {summary['bundle']}")
    for check in summary["checks"]:
        marker = "ok" if check["passed"] else "FAIL"
        detail = check["detail"]
        if isinstance(detail, dict):
            detail = detail.get("message") or json.dumps(
                detail,
                sort_keys=True,
            )
        print(f"  {marker} {check['name']}: {detail}")


if __name__ == "__main__":
    sys.exit(main())
