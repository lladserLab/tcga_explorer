#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.reproduction_capsule import (  # noqa: E402
    BASE_IMAGE,
    CRAN_SNAPSHOT,
    REPRODUCTION_TOLERANCE_POLICY,
    REPRODUCTION_TOLERANCE_POLICY_VERSION,
    RENV_VERSION,
    write_reproduction_capsule,
)
import verify_reproducibility_bundle as verifier  # noqa: E402


OUTPUT_DIR = (
    ROOT
    / "docs"
    / "publication"
    / "benchmark"
    / "clean_container_reproduction"
)
CAPSULE_DIR = OUTPUT_DIR / "capsules"
RECONSTRUCTION_SUMMARY = (
    ROOT
    / "docs"
    / "publication"
    / "benchmark"
    / "reproducibility_benchmark"
    / "summary.csv"
)
FROZEN_CAPSULE_LABELS = {
    "single_gene": "Single gene",
    "weighted_signature": "Weighted signature",
    "two_signatures": "Two signatures",
}
CURRENT_CAPSULE_FILENAMES = (
    "input.json",
    "metrics.json",
    "audit_report.json",
    "rerun_analysis.R",
    "km_analysis.R",
    "clinical_covariates.R",
    "cox_diagnostics.R",
    "competing_risks.R",
    "renv.lock",
    "Dockerfile.reproduce",
    "REPRODUCE.md",
    "reproduction_manifest.json",
)
REQUIRED_MANIFEST_LABELS = {
    "input",
    "reproduction_dockerfile",
    "reproduction_km_analysis",
    "reproduction_r_runner",
    "reproduction_renv_lock",
}
REQUIRED_RUNTIME_PACKAGES = {
    "jsonlite",
    "survival",
    "survminer",
    "ggplot2",
    "svglite",
    "survRM2",
    "coxphf",
    "maxstat",
}


def main() -> int:
    args = parse_args()
    if args.check_only:
        verify_frozen_outputs()
        print("Clean-container reproduction outputs verified.")
        return 0

    capsules = prepare_capsules(refresh=args.refresh_capsules)
    requested_platforms = args.platform or ["native"]
    environments = []
    rows = []
    for requested_platform in requested_platforms:
        image = image_tag(args.image_prefix, requested_platform)
        if args.build:
            build_image(
                capsule=next(iter(capsules.values())),
                image=image,
                requested_platform=requested_platform,
            )
        image_metadata = inspect_image(image)
        case_results = []
        for label, capsule in capsules.items():
            result = run_capsule(
                label=label,
                capsule=capsule,
                image=image,
                requested_platform=requested_platform,
            )
            case_results.append(result)
            error_extrema = numeric_error_extrema(
                result.get("numeric_comparison") or {}
            )
            rows.append(
                {
                    "environment": requested_platform,
                    "architecture": image_metadata["architecture"],
                    "analysis": label,
                    "analysis_id": result["analysis_id"],
                    "status": result["status"],
                    "runtime_seconds": result["runtime_seconds"],
                    "difference_count": len(result["differences"]),
                    "numeric_comparisons": error_extrema["comparisons"],
                    "max_absolute_error": error_extrema[
                        "max_absolute_error"
                    ],
                    "max_relative_error": error_extrema[
                        "max_relative_error"
                    ],
                    "r_version": result["r_version"],
                    "image_id": image_metadata["image_id"],
                }
            )
        input_tamper = run_input_tamper(
            capsule=next(iter(capsules.values())),
            image=image,
            requested_platform=requested_platform,
        )
        environments.append(
            {
                "requested_platform": requested_platform,
                "image": image,
                "image_metadata": image_metadata,
                "cases": case_results,
                "input_tamper": input_tamper,
            }
        )

    snapshot_tamper = data_snapshot_tamper_detected(next(iter(capsules.values())))
    payload = {
        "schema_version": "tcga-trace-clean-reproduction-benchmark-v1",
        "generated_at": utc_now(),
        "design": {
            "runtime_isolation": [
                "No TCGA matrix, PostgreSQL database, FastAPI service or application source is mounted.",
                "The capsule is mounted read-only.",
                "The container root filesystem is read-only.",
                "Network access is disabled.",
                "Only /tmp and /output are writable.",
            ],
            "base_image": BASE_IMAGE,
            "cran_snapshot": CRAN_SNAPSHOT,
            "renv_version": RENV_VERSION,
            "numeric_comparison": {
                "policy_version": REPRODUCTION_TOLERANCE_POLICY_VERSION,
                "pass_rule": (
                    "absolute_error <= absolute + relative * "
                    "max(abs(expected), abs(observed))"
                ),
                "classes": REPRODUCTION_TOLERANCE_POLICY,
            },
            "host": {
                "system": platform.system(),
                "machine": platform.machine(),
                "python": platform.python_version(),
            },
        },
        "capsules": {
            label: capsule_metadata(path) for label, path in capsules.items()
        },
        "environments": environments,
        "negative_controls": {
            "data_snapshot_hash_change_detected": snapshot_tamper,
            "mutated_input_rejected_by_all_environments": all(
                environment["input_tamper"]["detected"]
                for environment in environments
            ),
        },
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json(OUTPUT_DIR / "benchmark_results.raw.json", payload)
    write_csv(OUTPUT_DIR / "summary.csv", rows)
    write_markdown(OUTPUT_DIR / "summary.md", payload, rows)
    write_manifest()
    verify_frozen_outputs()
    print(f"Wrote {OUTPUT_DIR / 'summary.md'}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Re-execute frozen TCGA-TRACE capsules in a pinned, network-disabled "
            "container that does not contain or mount the web application."
        )
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Build the pinned reproduction image before running capsules.",
    )
    parser.add_argument(
        "--platform",
        action="append",
        choices=("native", "linux/amd64", "linux/arm64"),
        help="Execution platform. Repeat to benchmark more than one architecture.",
    )
    parser.add_argument(
        "--image-prefix",
        default="tcga-trace-reproduction:2026-07-25",
    )
    parser.add_argument(
        "--refresh-capsules",
        action="store_true",
        help=(
            "Explicitly replace frozen capsules from matching local analysis "
            "artifacts and the current engine. Existing capsules are immutable "
            "by default."
        ),
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Verify frozen outputs and hashes without running Docker.",
    )
    return parser.parse_args()


def prepare_capsules(*, refresh: bool = False) -> dict[str, Path]:
    if not refresh:
        return frozen_capsules()

    rows = reconstruction_rows()
    capsules: dict[str, Path] = {}
    for row in rows:
        label = row["label"]
        analysis_id = row["analysis_id"]
        source = ROOT / "artifacts" / analysis_id
        destination = CAPSULE_DIR / slugify(label)
        if not (source / "input.json").is_file() or not (
            source / "metrics.json"
        ).is_file():
            raise FileNotFoundError(
                f"Cannot refresh {label}: source artifact {analysis_id} "
                "is incomplete or unavailable."
            )
        write_reproduction_capsule(
            source,
            r_script_path=ROOT / "backend" / "scripts" / "km_analysis.R",
            renv_lock_path=ROOT / "backend" / "renv.lock",
        )
        destination.mkdir(parents=True, exist_ok=True)
        for filename in CURRENT_CAPSULE_FILENAMES:
            source_path = source / filename
            if not source_path.is_file():
                raise FileNotFoundError(
                    f"Capsule {analysis_id} is missing {filename}."
                )
            shutil.copyfile(source_path, destination / filename)
        capsules[label] = destination
    return capsules


def reconstruction_rows() -> list[dict[str, str]]:
    if not RECONSTRUCTION_SUMMARY.is_file():
        raise FileNotFoundError(
            f"Missing reconstruction summary: {RECONSTRUCTION_SUMMARY}"
        )
    with RECONSTRUCTION_SUMMARY.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise RuntimeError("Reconstruction summary contains no representative analyses.")

    normalized = []
    for row in rows:
        label = str(row.get("label") or "").strip()
        analysis_id = str(row.get("analysis_id") or "").strip()
        if not label or not analysis_id:
            raise RuntimeError("Reconstruction summary has an incomplete row.")
        normalized.append({"label": label, "analysis_id": analysis_id})
    return normalized


def verify_frozen_capsules() -> None:
    frozen_capsules()


def frozen_capsules() -> dict[str, Path]:
    capsules: dict[str, Path] = {}
    for slug, label in FROZEN_CAPSULE_LABELS.items():
        path = CAPSULE_DIR / slug
        audit_path = path / "audit_report.json"
        if not audit_path.is_file():
            raise FileNotFoundError(
                f"Frozen capsule {path} is missing audit_report.json."
            )
        analysis_id = str(read_json(audit_path).get("analysis_id") or "")
        if not analysis_id:
            raise RuntimeError(
                f"Frozen capsule {path} has no recorded analysis identifier."
            )
        validate_frozen_capsule(path, analysis_id=analysis_id)
        capsules[label] = path
    return capsules


def validate_frozen_capsule(path: Path, *, analysis_id: str) -> None:
    envelope_files = (
        "input.json",
        "metrics.json",
        "audit_report.json",
        "reproduction_manifest.json",
    )
    missing = [
        filename for filename in envelope_files if not (path / filename).is_file()
    ]
    if missing:
        raise FileNotFoundError(
            f"Neither local artifacts nor a complete frozen capsule are available "
            f"for {analysis_id}; missing: {', '.join(missing)}."
        )
    metrics = read_json(path / "metrics.json")
    audit = read_json(path / "audit_report.json")
    audit_id = str(audit.get("analysis_id") or "")
    metrics_id = str(metrics.get("analysis_id") or "")
    if audit_id != analysis_id or (
        metrics_id and metrics_id != analysis_id
    ):
        raise RuntimeError(
            f"Frozen capsule {path} does not match analysis {analysis_id}."
        )

    manifest = read_json(path / "reproduction_manifest.json")
    if manifest.get("schema_version") != "tcga-trace-reproduction-capsule-v1":
        raise RuntimeError(f"Frozen capsule {path} has an unexpected schema.")
    manifest_files = manifest.get("files") or {}
    missing_labels = sorted(REQUIRED_MANIFEST_LABELS - set(manifest_files))
    if missing_labels:
        raise RuntimeError(
            f"Frozen capsule {path} manifest is missing required records: "
            f"{', '.join(missing_labels)}."
        )
    for record in manifest_files.values():
        filename = str(record.get("filename") or "")
        if not filename or Path(filename).name != filename:
            raise RuntimeError(
                f"Frozen capsule {path} contains an unsafe manifest filename."
            )
        frozen_file = path / filename
        if (
            not frozen_file.is_file()
            or frozen_file.stat().st_size != record.get("bytes")
            or file_sha256(frozen_file) != record.get("sha256")
        ):
            raise RuntimeError(
                f"Frozen capsule integrity check failed for {path / filename}."
            )


def image_tag(prefix: str, requested_platform: str) -> str:
    suffix = {
        "native": "native",
        "linux/amd64": "amd64",
        "linux/arm64": "arm64",
    }[requested_platform]
    return f"{prefix}-{suffix}"


def build_image(*, capsule: Path, image: str, requested_platform: str) -> None:
    if requested_platform == "native":
        command = [
            "docker",
            "build",
            "-f",
            str(capsule / "Dockerfile.reproduce"),
            "-t",
            image,
            str(capsule),
        ]
    else:
        command = [
            "docker",
            "buildx",
            "build",
            "--platform",
            requested_platform,
            "--load",
            "-f",
            str(capsule / "Dockerfile.reproduce"),
            "-t",
            image,
            str(capsule),
        ]
    subprocess.run(command, cwd=ROOT, check=True)


def inspect_image(image: str) -> dict[str, Any]:
    result = subprocess.run(
        ["docker", "image", "inspect", image],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    record = json.loads(result.stdout)[0]
    return {
        "image_id": record.get("Id"),
        "repo_digests": record.get("RepoDigests") or [],
        "architecture": record.get("Architecture"),
        "os": record.get("Os"),
        "created": record.get("Created"),
    }


def run_capsule(
    *,
    label: str,
    capsule: Path,
    image: str,
    requested_platform: str,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix="clean-reproduction-output-",
        dir=ROOT / "artifacts",
    ) as output:
        started = time.perf_counter()
        result = subprocess.run(
            docker_run_command(
                capsule=capsule,
                output=Path(output),
                image=image,
                requested_platform=requested_platform,
            ),
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        runtime = time.perf_counter() - started
        result_path = Path(output) / "reproduction_result.json"
        reproduction = (
            read_json(result_path)
            if result_path.is_file()
            else {
                "status": "failed",
                "differences": [
                    (result.stderr or result.stdout or "No reproduction result.").strip()
                ],
            }
        )
    metrics = read_json(capsule / "metrics.json")
    package_versions = reproduction.get("package_versions") or {}
    numeric_comparison = reproduction.get("numeric_comparison") or {}
    package_match = package_versions_match_lock(
        capsule=capsule,
        observed=package_versions,
    )
    status = (
        "passed"
        if result.returncode == 0
        and reproduction.get("status") == "passed"
        and package_match
        and numeric_comparison.get("policy_version")
        == REPRODUCTION_TOLERANCE_POLICY_VERSION
        else "failed"
    )
    return {
        "label": label,
        "analysis_id": metrics.get("analysis_id"),
        "status": status,
        "returncode": result.returncode,
        "runtime_seconds": round(runtime, 3),
        "differences": reproduction.get("differences") or [],
        "r_version": reproduction.get("r_version"),
        "package_versions": package_versions,
        "package_versions_match_lock": package_match,
        "numeric_comparison": numeric_comparison,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def run_input_tamper(
    *,
    capsule: Path,
    image: str,
    requested_platform: str,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix="clean-reproduction-tamper-",
        dir=ROOT / "artifacts",
    ) as temporary:
        temporary_path = Path(temporary)
        mutated_capsule = temporary_path / "capsule"
        output = temporary_path / "output"
        mutated_capsule.mkdir()
        output.mkdir()
        for filename in capsule_inventory(capsule):
            shutil.copyfile(capsule / filename, mutated_capsule / filename)
        payload = read_json(mutated_capsule / "input.json")
        records = payload.get("records") or []
        if not records:
            raise RuntimeError("Cannot run negative control without patient records.")
        records[0]["event"] = 1 - int(records[0]["event"])
        write_json(mutated_capsule / "input.json", payload)
        result = subprocess.run(
            docker_run_command(
                capsule=mutated_capsule,
                output=output,
                image=image,
                requested_platform=requested_platform,
            ),
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        result_path = output / "reproduction_result.json"
        reproduction = read_json(result_path) if result_path.is_file() else {}
    return {
        "detected": (
            result.returncode != 0
            and reproduction.get("status") == "failed"
            and bool(reproduction.get("differences"))
        ),
        "returncode": result.returncode,
        "difference_count": len(reproduction.get("differences") or []),
        "first_difference": (reproduction.get("differences") or [None])[0],
    }


def docker_run_command(
    *,
    capsule: Path,
    output: Path,
    image: str,
    requested_platform: str,
) -> list[str]:
    command = ["docker", "run", "--rm"]
    if requested_platform != "native":
        command.extend(["--platform", requested_platform])
    command.extend(
        [
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=512m",
            "--mount",
            f"type=bind,src={capsule.resolve()},dst=/analysis,readonly",
            "--mount",
            f"type=bind,src={output.resolve()},dst=/output",
            image,
        ]
    )
    return command


def data_snapshot_tamper_detected(capsule: Path) -> bool:
    report = read_json(capsule / "audit_report.json")
    expected = report.get("reproducibility_hash")
    mutated = copy.deepcopy(report)
    expression_files = (
        ((mutated.get("data") or {}).get("provenance") or {}).get(
            "expression_files"
        )
        or []
    )
    if not expression_files:
        raise RuntimeError("Audit report has no expression snapshot hashes.")
    expression_files[0]["sha256"] = "0" * 64
    patient_digest = (
        (mutated.get("cohort_selection") or {}).get("patient_records_sha256")
    )
    payload = verifier.reproducibility_payload_from_report(
        mutated,
        request_payload=mutated["request"],
        patient_digest=patient_digest,
    )
    return verifier.stable_hash(payload) != expected


def capsule_inventory(capsule: Path) -> list[str]:
    manifest = read_json(capsule / "reproduction_manifest.json")
    filenames = {
        "audit_report.json",
        "metrics.json",
        "reproduction_manifest.json",
    }
    for record in (manifest.get("files") or {}).values():
        filename = str(record.get("filename") or "")
        if not filename or Path(filename).name != filename:
            raise RuntimeError(
                f"Frozen capsule {capsule} contains an unsafe manifest filename."
            )
        filenames.add(filename)
    return sorted(filenames)


def package_versions_match_lock(
    *,
    capsule: Path,
    observed: dict[str, Any],
) -> bool:
    if not REQUIRED_RUNTIME_PACKAGES.issubset(observed):
        return False
    lock = read_json(capsule / "renv.lock")
    packages = lock.get("Packages") or {}
    for package, observed_version in observed.items():
        expected = (packages.get(package) or {}).get("Version")
        if not expected or normalize_r_package_version(
            observed_version
        ) != normalize_r_package_version(expected):
            return False
    return True


def normalize_r_package_version(value: Any) -> str:
    return str(value or "").strip().replace("-", ".")


def capsule_metadata(path: Path) -> dict[str, Any]:
    manifest = read_json(path / "reproduction_manifest.json")
    audit = read_json(path / "audit_report.json")
    return {
        "path": str(path.relative_to(ROOT)),
        "analysis_id": audit.get("analysis_id"),
        "reproducibility_hash": audit.get("reproducibility_hash"),
        "capsule_manifest_sha256": file_sha256(
            path / "reproduction_manifest.json"
        ),
        "base_image": manifest.get("base_image"),
        "cran_snapshot": manifest.get("cran_snapshot"),
    }


def numeric_error_extrema(comparison: dict[str, Any]) -> dict[str, float | int]:
    observed = comparison.get("observed_errors") or {}
    return {
        "comparisons": sum(
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


def write_markdown(
    path: Path,
    payload: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    lines = [
        "# Clean-Container Reproduction Benchmark",
        "",
        "Frozen patient-level inputs were re-executed without the TCGA-TRACE application, TCGA matrices, a database or network access.",
        "",
        f"- Base image: `{payload['design']['base_image']}`",
        f"- CRAN snapshot: `{payload['design']['cran_snapshot']}`",
        "- Runtime: read-only container and capsule; only `/tmp` and `/output` writable.",
        (
            "- Numerical comparison: exact counts and categorical fields; "
            "quantity-aware absolute-plus-relative tolerances for probabilities, "
            "effects, times and other floating outputs."
        ),
        "",
        "| Environment | Architecture | Analysis | Runtime (s) | Numeric values | Max abs. error | Max rel. error | Differences | Status |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['environment']} | {row['architecture']} | {row['analysis']} | "
            f"{row['runtime_seconds']:.3f} | {row['numeric_comparisons']} | "
            f"{row['max_absolute_error']:.3g} | {row['max_relative_error']:.3g} | "
            f"{row['difference_count']} | {row['status']} |"
        )
    lines.extend(
        [
            "",
            "## Negative Controls",
            "",
            f"- Altered expression-snapshot SHA-256 detected: {yes_no(payload['negative_controls']['data_snapshot_hash_change_detected'])}.",
            f"- Mutated patient input rejected in every environment: {yes_no(payload['negative_controls']['mutated_input_rejected_by_all_environments'])}.",
            "",
            "The local cross-architecture run uses Docker emulation and is not described as a second physical machine. The CI workflow repeats the same contract on an independent Linux/amd64 runner.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_manifest() -> None:
    paths = [
        path
        for path in OUTPUT_DIR.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    ]
    payload = {
        "schema_version": "tcga-trace-clean-reproduction-manifest-v1",
        "files": {
            str(path.relative_to(OUTPUT_DIR)): {
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
            for path in sorted(paths)
        },
    }
    write_json(OUTPUT_DIR / "manifest.json", payload)


def verify_frozen_outputs() -> None:
    verify_frozen_capsules()
    manifest_path = OUTPUT_DIR / "manifest.json"
    results_path = OUTPUT_DIR / "benchmark_results.raw.json"
    if not manifest_path.is_file() or not results_path.is_file():
        raise FileNotFoundError("Clean-container benchmark outputs are incomplete.")
    manifest = read_json(manifest_path)
    for relative, expected in (manifest.get("files") or {}).items():
        path = OUTPUT_DIR / relative
        if not path.is_file():
            raise RuntimeError(f"Missing frozen clean-reproduction file: {relative}")
        if path.stat().st_size != expected.get("bytes"):
            raise RuntimeError(f"Size mismatch for {relative}")
        if file_sha256(path) != expected.get("sha256"):
            raise RuntimeError(f"SHA-256 mismatch for {relative}")

    payload = read_json(results_path)
    if payload.get("schema_version") != "tcga-trace-clean-reproduction-benchmark-v1":
        raise RuntimeError("Unexpected clean-reproduction result schema.")
    environments = payload.get("environments") or []
    if not environments:
        raise RuntimeError("No clean-reproduction environments were recorded.")
    for environment in environments:
        if not environment.get("cases") or any(
            case.get("status") != "passed" for case in environment["cases"]
        ):
            raise RuntimeError("A frozen clean-reproduction case did not pass.")
        if any(
            (case.get("numeric_comparison") or {}).get("policy_version")
            != REPRODUCTION_TOLERANCE_POLICY_VERSION
            for case in environment["cases"]
        ):
            raise RuntimeError(
                "A frozen clean-reproduction case used an unexpected numeric policy."
            )
        if not (environment.get("input_tamper") or {}).get("detected"):
            raise RuntimeError("A frozen input-tamper control did not pass.")
    if not all((payload.get("negative_controls") or {}).values()):
        raise RuntimeError("Frozen clean-reproduction negative controls failed.")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slugify(value: str) -> str:
    return "_".join(
        part for part in "".join(
            character.lower() if character.isalnum() else " "
            for character in value
        ).split()
        if part
    )


def yes_no(value: Any) -> str:
    return "yes" if value else "no"


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    sys.exit(main())
