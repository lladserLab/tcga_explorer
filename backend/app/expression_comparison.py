from __future__ import annotations

from array import array
import csv
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Callable

from app.gene_aliases import GENE_ALIASES
from app.gsea import ExpressionMatrix
from app.r_runner import json_safe_value, stable_hash


EXPRESSION_COMPARISON_RESULT_SCHEMA = (
    "tcga-trace-expression-comparison-result-v1"
)
EXPRESSION_COMPARISON_AUDIT_SCHEMA = (
    "tcga-trace-expression-comparison-audit-v1"
)
EXPRESSION_COMPARISON_ENGINE_SCHEMA = (
    "tcga-trace-expression-comparison-engine-input-v1"
)
MIN_FINITE_SAMPLES_PER_GROUP = 5


def _file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fields: list[str],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def resolve_expression_genes(
    matrix: ExpressionMatrix,
    requested_genes: list[str],
    *,
    resolver: Callable[[str], str | None] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Resolve request-order symbols to unique rows in the selected matrix."""

    by_symbol: dict[str, Any] = {}
    duplicate_rows: set[str] = set()
    for gene in matrix.genes:
        symbol = gene.symbol.strip().upper()
        if not symbol:
            continue
        if symbol in by_symbol:
            duplicate_rows.add(symbol)
            continue
        by_symbol[symbol] = gene

    resolved: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    missing: list[str] = []
    for raw in requested_genes:
        query = raw.strip().upper()
        candidates: list[str] = []
        if resolver is not None:
            resolved_candidate = resolver(query)
            if resolved_candidate:
                candidates.append(str(resolved_candidate).strip().upper())
        candidates.extend([GENE_ALIASES.get(query, query), query])
        canonical = next(
            (candidate for candidate in candidates if candidate in by_symbol),
            None,
        )
        if canonical is None:
            missing.append(query)
            continue
        if canonical in seen:
            warnings.append(
                f"Gene {query} resolves to {canonical}, which was already "
                "requested; the duplicate was collapsed."
            )
            continue
        seen.add(canonical)
        gene = by_symbol[canonical]
        resolved.append(
            {
                "requested_symbol": query,
                "gene_symbol": canonical,
                "row_number": int(gene.row_number),
                "resolution": "exact" if query == canonical else "alias",
            }
        )
        if query != canonical:
            warnings.append(f"Gene alias {query} was resolved to {canonical}.")
        if canonical in duplicate_rows:
            warnings.append(
                f"The matrix contains duplicate rows for {canonical}; the "
                "first indexed row was used."
            )
    if missing:
        raise ValueError(
            "Requested genes were not found in the selected expression matrix: "
            + ", ".join(missing)
            + "."
        )
    if not resolved:
        raise ValueError("No unique requested genes remain after resolution.")
    return resolved, warnings


def extract_expression_value_rows(
    matrix: ExpressionMatrix,
    resolved_genes: list[dict[str, Any]],
    assignments: dict[str, str],
    samples: list[Any],
    *,
    group_a_label: str,
    group_b_label: str,
) -> list[dict[str, Any]]:
    """Read only requested float32 rows and export finite assigned values."""

    if matrix.dtype != "float32":
        raise ValueError(
            f"Unsupported expression matrix dtype: {matrix.dtype}."
        )
    sample_by_barcode = {
        sample.barcode: sample
        for sample in samples
        if sample.barcode in assignments
    }
    selected_indices = [
        index
        for index, barcode in enumerate(matrix.sample_ids)
        if barcode in sample_by_barcode
        and assignments.get(barcode) in {"a", "b"}
    ]
    if not selected_indices:
        raise ValueError("No assigned samples are present in the expression matrix.")

    item_size = array("f").itemsize
    sample_count = len(matrix.sample_ids)
    labels = {"a": group_a_label, "b": group_b_label}
    rows: list[dict[str, Any]] = []
    with matrix.path.open("rb") as handle:
        for gene in resolved_genes:
            values = array("f")
            handle.seek(int(gene["row_number"]) * sample_count * item_size)
            values.fromfile(handle, sample_count)
            if len(values) != sample_count:
                raise ValueError(
                    f"Expression matrix row for {gene['gene_symbol']} is truncated."
                )
            if matrix.byte_order == "little" and sys.byteorder != "little":
                values.byteswap()
            elif matrix.byte_order == "big" and sys.byteorder != "big":
                values.byteswap()
            for index in selected_indices:
                value = float(values[index])
                if not math.isfinite(value):
                    continue
                barcode = matrix.sample_ids[index]
                sample = sample_by_barcode[barcode]
                group_key = assignments[barcode]
                rows.append(
                    {
                        "patient_id": sample.patient_id,
                        "sample_barcode": barcode,
                        "gene_symbol": gene["gene_symbol"],
                        "group_key": group_key,
                        "group_label": labels[group_key],
                        "expression_value": value,
                    }
                )
    return rows


def _make_svg_accessible(
    path: Path,
    *,
    title: str,
    description: str,
) -> None:
    content = path.read_text(encoding="utf-8")
    marker = "<svg "
    if marker not in content:
        raise RuntimeError(f"R did not produce a valid SVG artifact: {path.name}.")
    title_id = f"{path.stem}-title"
    desc_id = f"{path.stem}-desc"
    content = content.replace(
        marker,
        (
            f'<svg role="img" aria-labelledby="{title_id} {desc_id}" '
        ),
        1,
    )
    opening_end = content.find(">", content.find("<svg"))
    content = (
        content[: opening_end + 1]
        + f'<title id="{title_id}">{escape(title)}</title>'
        + f'<desc id="{desc_id}">{escape(description)}</desc>'
        + content[opening_end + 1 :]
    )
    path.write_text(content, encoding="utf-8")


def expression_comparison_artifact_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "input": output_dir / "input.json",
        "engine_input": output_dir / "engine_input.json",
        "values": output_dir / "expression_values.csv",
        "groups": output_dir / "sample_groups.csv",
        "statistics": output_dir / "gene_statistics.csv",
        "summaries": output_dir / "group_summaries.csv",
        "engine_statistics": output_dir / "statistics.json",
        "violin_svg": output_dir / "violin_plot.svg",
        "boxplot_svg": output_dir / "boxplot.svg",
        "heatmap_svg": output_dir / "heatmap.svg",
        "methodology": output_dir / "methodology.txt",
        "result": output_dir / "result.json",
        "audit": output_dir / "audit_report.json",
    }


def run_expression_comparison_engine(
    output_dir: Path,
    *,
    request_payload: dict[str, Any],
    value_rows: list[dict[str, Any]],
    assignment_rows: list[dict[str, Any]],
    resolved_genes: list[dict[str, Any]],
    gene_policies: dict[str, dict[str, Any]],
    group_a_label: str,
    group_b_label: str,
    fdr_threshold: float,
    heatmap_max_samples: int,
    pipeline_version: str,
    script_path: Path | None = None,
) -> dict[str, Any]:
    """Run deterministic base-R statistics and plots into a new artifact dir."""

    output_dir.mkdir(parents=True, exist_ok=False)
    paths = expression_comparison_artifact_paths(output_dir)
    _write_csv(
        paths["values"],
        value_rows,
        [
            "patient_id",
            "sample_barcode",
            "gene_symbol",
            "group_key",
            "group_label",
            "expression_value",
        ],
    )
    _write_csv(
        paths["groups"],
        assignment_rows,
        [
            "patient_id",
            "sample_barcode",
            "analysis_included",
            "exclusion_reason",
            "group_key",
            "group_label",
            "clinical_variable_id",
            "clinical_variable_label",
            "clinical_source",
            "clinical_source_field",
            "clinical_value",
            "sample_type",
            "stage",
            "grade",
            "gender",
            "race",
            "age_at_index",
        ],
    )
    engine_genes = []
    for gene in resolved_genes:
        symbol = str(gene["gene_symbol"])
        policy = gene_policies.get(symbol) or {}
        engine_genes.append(
            {
                **gene,
                "inferential_status": str(
                    policy.get("inferential_status") or "inferential"
                ),
                "circularity_reason": policy.get("circularity_reason"),
                "included_in_multiplicity": bool(
                    policy.get("included_in_multiplicity", True)
                ),
            }
        )
    engine_input = {
        **request_payload,
        "schema_version": EXPRESSION_COMPARISON_ENGINE_SCHEMA,
        "pipeline_version": pipeline_version,
        "contrast": "group_b_minus_group_a",
        "group_a_label": group_a_label,
        "group_b_label": group_b_label,
        "fdr_threshold": fdr_threshold,
        "heatmap_max_samples": heatmap_max_samples,
        "minimum_finite_samples_per_group": MIN_FINITE_SAMPLES_PER_GROUP,
        "genes_resolved": engine_genes,
        "values_csv": str(paths["values"]),
        "groups_csv": str(paths["groups"]),
        "statistics_json": str(paths["engine_statistics"]),
        "statistics_csv": str(paths["statistics"]),
        "summaries_csv": str(paths["summaries"]),
        "violin_svg": str(paths["violin_svg"]),
        "boxplot_svg": str(paths["boxplot_svg"]),
        "heatmap_svg": str(paths["heatmap_svg"]),
    }
    paths["input"].write_text(
        json.dumps(
            request_payload,
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    paths["engine_input"].write_text(
        json.dumps(
            engine_input,
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    selected_script = script_path or (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "expression_comparison.R"
    )
    if not selected_script.is_file():
        raise RuntimeError(
            f"Expression-comparison R engine is unavailable: {selected_script}."
        )
    result = subprocess.run(
        ["Rscript", str(selected_script), str(paths["engine_input"])],
        check=False,
        capture_output=True,
        text=True,
        timeout=240,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Expression-comparison R engine failed: "
            + (result.stderr or result.stdout or "unknown error")
        )
    required = [
        "engine_statistics",
        "statistics",
        "summaries",
        "violin_svg",
        "boxplot_svg",
        "heatmap_svg",
    ]
    missing = [key for key in required if not paths[key].is_file()]
    if missing:
        raise RuntimeError(
            "Expression-comparison engine omitted required artifacts: "
            + ", ".join(missing)
            + "."
        )
    metrics = json_safe_value(
        json.loads(paths["engine_statistics"].read_text(encoding="utf-8"))
    )
    _make_svg_accessible(
        paths["violin_svg"],
        title="Expression distributions by group",
        description=(
            f"Violin distributions for group A ({group_a_label}) and group B "
            f"({group_b_label}) in request gene order."
        ),
    )
    _make_svg_accessible(
        paths["boxplot_svg"],
        title="Expression boxplots by group",
        description=(
            f"Boxplots compare group A ({group_a_label}) with group B "
            f"({group_b_label}) for every requested gene."
        ),
    )
    _make_svg_accessible(
        paths["heatmap_svg"],
        title="Gene expression heatmap",
        description=(
            "Within-gene z scores for a deterministic, group-stratified sample "
            "subset. Columns are ordered by group and sample barcode."
        ),
    )
    return metrics


def finalize_expression_comparison_artifacts(
    output_dir: Path,
    *,
    request_payload: dict[str, Any],
    result_payload: dict[str, Any],
    pipeline_version: str,
) -> dict[str, Any]:
    paths = expression_comparison_artifact_paths(output_dir)
    methods = [
        "TRACE Explorer grouped expression comparison",
        "",
        (
            "The exact binary grouping machinery used by GSEA was reused. "
            "The declared contrast is group B minus group A."
        ),
        (
            "For every gene, finite observations are summarized by n, mean, "
            "sample SD, median, quartiles, minimum and maximum. No values are "
            "imputed."
        ),
        (
            "Welch's unequal-variance two-sample t test and a two-sided "
            "Mann-Whitney-Wilcoxon rank-sum test are always declared. The mean "
            "difference and its 95% Welch confidence interval, Hedges g and "
            "rank-biserial correlation all use the B-minus-A direction."
        ),
        (
            "Benjamini-Hochberg adjustment is applied separately across the "
            "eligible Welch and Mann-Whitney gene families. Genes that define "
            "their own grouping are descriptive-only and excluded from both "
            "multiplicity families. When a clinical annotation is itself "
            "derived from transcriptomic expression, every target gene is "
            "descriptive-only and excluded from both families."
        ),
        (
            "The heatmap uses within-gene z scores and deterministic, "
            "group-stratified sample thinning when the declared sample cap is "
            "exceeded."
        ),
        (
            "Mann-Whitney evaluates distributional/location shift under its "
            "assumptions and is not, in general, a test of medians. Results are "
            "exploratory and are not intended for clinical decision-making."
        ),
        "",
        f"Pipeline version: {pipeline_version}",
        f"FDR threshold: {result_payload['summary']['fdr_threshold']}",
    ]
    paths["methodology"].write_text("\n".join(methods) + "\n", encoding="utf-8")

    artifact_keys = [
        "input",
        "values",
        "groups",
        "statistics",
        "violin_svg",
        "boxplot_svg",
        "heatmap_svg",
        "methodology",
    ]
    artifacts = {
        key: {
            "filename": paths[key].name,
            "file": paths[key].name,
            "sha256": _file_sha256(paths[key]),
            "bytes": paths[key].stat().st_size,
        }
        for key in artifact_keys
    }
    audit = {
        "report_type": "expression_comparison_audit",
        "schema_version": EXPRESSION_COMPARISON_AUDIT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": pipeline_version,
        "request_sha256": stable_hash(request_payload),
        "group_assignments_sha256": _file_sha256(paths["groups"]),
        "expression_values_sha256": _file_sha256(paths["values"]),
        "gene_statistics_sha256": _file_sha256(paths["statistics"]),
        "matrix_sha256": (
            result_payload.get("data_provenance") or {}
        ).get("matrix_sha256"),
        "data_version": (
            result_payload.get("data_provenance") or {}
        ).get("data_version") or {},
        "multiplicity_families": {
            "welch": "BH across eligible requested genes with evaluable Welch p-values",
            "mann_whitney": (
                "BH across eligible requested genes with evaluable two-sided "
                "Mann-Whitney p-values"
            ),
            "descriptive_only_genes_excluded": True,
        },
        "result_core_sha256": stable_hash(
            json_safe_value(
                {
                    "grouping": result_payload["grouping"],
                    "summary": result_payload["summary"],
                    "statistics": result_payload["statistics"],
                    "warnings": result_payload.get("warnings") or [],
                    "data_provenance": result_payload.get("data_provenance")
                    or {},
                }
            )
        ),
        "artifacts": artifacts,
        "limitations": [
            (
                "Expression-derived groups are exploratory; a target gene that "
                "participated in grouping is reported as descriptive-only. "
                "All targets are descriptive-only when the selected clinical "
                "annotation is itself expression-derived."
            ),
            (
                "Survival maxstat groups are outcome-informed and require "
                "independent validation."
            ),
            (
                "Separate Welch and Mann-Whitney BH families answer distinct "
                "prespecified questions and must not be selected post hoc."
            ),
            (
                "This exploratory analysis is not intended for clinical "
                "decision-making."
            ),
        ],
    }
    paths["audit"].write_text(
        json.dumps(audit, ensure_ascii=True, allow_nan=False, indent=2),
        encoding="utf-8",
    )
    paths["result"].write_text(
        json.dumps(
            {**result_payload, "audit": audit},
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return audit


def cleanup_expression_comparison_artifacts(output_dir: Path) -> None:
    shutil.rmtree(output_dir, ignore_errors=True)
