from __future__ import annotations

from typing import Any, Mapping


CAPABILITY_EXPRESSION = "expression"
CAPABILITY_EXPRESSION_COMPARISON = "expression_comparison"
CAPABILITY_GSEA = "gsea"
CAPABILITY_SURVIVAL = "survival"
CAPABILITY_RANK_BASED_SIGNATURE_SCORING = "rank_based_signature_scoring"

CAPABILITY_NAMES = (
    CAPABILITY_EXPRESSION,
    CAPABILITY_EXPRESSION_COMPARISON,
    CAPABILITY_GSEA,
    CAPABILITY_SURVIVAL,
    CAPABILITY_RANK_BASED_SIGNATURE_SCORING,
)

# These are the stable workspace page identifiers used by TRACE Explorer.
MODULE_CAPABILITY_REQUIREMENTS = {
    "analysis": CAPABILITY_SURVIVAL,
    "compare": CAPABILITY_SURVIVAL,
    "expression": CAPABILITY_EXPRESSION_COMPARISON,
    "gsea": CAPABILITY_GSEA,
    "multiverse": CAPABILITY_SURVIVAL,
}
AVAILABLE_MODULE_ORDER = tuple(MODULE_CAPABILITY_REQUIREMENTS)

ANALYSIS_TYPE_ALIASES = {
    **MODULE_CAPABILITY_REQUIREMENTS,
    "survival": CAPABILITY_SURVIVAL,
    "robustness": CAPABILITY_SURVIVAL,
    "expression_comparison": CAPABILITY_EXPRESSION_COMPARISON,
    "expression-comparison": CAPABILITY_EXPRESSION_COMPARISON,
    CAPABILITY_RANK_BASED_SIGNATURE_SCORING: (
        CAPABILITY_RANK_BASED_SIGNATURE_SCORING
    ),
}

DEFAULT_MINIMUM_PATIENTS = 10
DEFAULT_MINIMUM_GENES = 10_000
RANK_SIGNATURE_MINIMUM_GENES = 1_000
RANK_SIGNATURE_MAXIMUM_MATRIX_ENTRIES = 75_000_000


def capability_for_analysis_type(analysis_type: str) -> str:
    normalized = str(analysis_type or "").strip().casefold()
    capability = ANALYSIS_TYPE_ALIASES.get(normalized)
    if capability is None:
        supported = ", ".join(sorted(ANALYSIS_TYPE_ALIASES))
        raise ValueError(
            f"Unknown repository analysis type {analysis_type!r}. "
            f"Supported values: {supported}."
        )
    return capability


def derive_repository_capabilities(
    qc: Mapping[str, Any] | None,
    expression_layer_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Derive analysis availability from immutable release QC.

    Persisted capability blocks are deliberately not trusted as authority.
    Capabilities are always reconstructed from the immutable QC facts and the
    current prohibition policy, so a stale or tampered cache can neither
    bypass failed QC nor re-enable a prohibited analysis. Older v1 QC payloads
    are upgraded deterministically from their layer and endpoint summaries.
    """

    payload = dict(qc or {})
    thresholds = payload.get("thresholds") or {}
    minimum_patients = int(
        thresholds.get("minimum_patients") or DEFAULT_MINIMUM_PATIENTS
    )
    minimum_genes = int(
        thresholds.get("minimum_genes") or DEFAULT_MINIMUM_GENES
    )
    patients, samples, genes = _molecular_counts(
        payload,
        expression_layer_id=expression_layer_id,
    )
    qc_passed = str(payload.get("status") or "").casefold() == "passed"
    molecular_available = (
        qc_passed
        and patients >= minimum_patients
        and samples >= minimum_patients
        and genes >= minimum_genes
    )
    molecular_reason = None
    if not qc_passed:
        molecular_reason = "The release has not passed repository QC."
    elif patients < minimum_patients or samples < minimum_patients:
        molecular_reason = (
            f"At least {minimum_patients} expression-linked patients and "
            "samples are required."
        )
    elif genes < minimum_genes:
        molecular_reason = (
            f"At least {minimum_genes} mapped genes are required."
        )

    _, selected_layer = _selected_layer_qc(payload, expression_layer_id)
    endpoint_rows = (
        selected_layer["endpoints"]
        if expression_layer_id and selected_layer is not None
        and "endpoints" in selected_layer
        else payload.get("endpoints") or {}
    )
    available_endpoint_ids = sorted(
        str(endpoint_id)
        for endpoint_id, endpoint_qc in endpoint_rows.items()
        if isinstance(endpoint_qc, Mapping)
        and bool(endpoint_qc.get("available"))
    )
    survival_available = molecular_available and bool(available_endpoint_ids)
    survival_reason = None
    if not molecular_available:
        survival_reason = molecular_reason
    elif not available_endpoint_ids:
        survival_reason = (
            "No endpoint currently reaches the repository survival QC "
            "thresholds."
        )

    capabilities: dict[str, dict[str, Any]] = {
        CAPABILITY_EXPRESSION: {
            "available": molecular_available,
            "reason": molecular_reason,
            "patient_count": patients,
            "sample_count": samples,
            "gene_count": genes,
        },
        CAPABILITY_EXPRESSION_COMPARISON: {
            "available": molecular_available,
            "reason": molecular_reason,
            "patient_count": patients,
            "sample_count": samples,
            "gene_count": genes,
        },
        CAPABILITY_GSEA: {
            "available": molecular_available,
            "reason": molecular_reason,
            "patient_count": patients,
            "sample_count": samples,
            "gene_count": genes,
        },
        CAPABILITY_SURVIVAL: {
            "available": survival_available,
            "reason": survival_reason,
            "patient_count": max(
                (
                    int(row.get("patients") or 0)
                    for row in endpoint_rows.values()
                    if isinstance(row, Mapping)
                    and bool(row.get("available"))
                ),
                default=0,
            ),
            "endpoint_ids": available_endpoint_ids,
        },
    }
    _apply_capability_prohibitions(capabilities, payload)
    expression_capability = capabilities[CAPABILITY_EXPRESSION]
    capabilities[CAPABILITY_RANK_BASED_SIGNATURE_SCORING] = (
        rank_signature_capability_from_qc(
            payload,
            expression_layer_id=expression_layer_id,
            prerequisite_available=bool(expression_capability.get("available")),
            prerequisite_reason=expression_capability.get("reason"),
        )
    )
    # The rank-scoring capability is derived after the core molecular
    # capabilities, so apply any explicit rank-scoring prohibition now that
    # the key exists.
    _apply_capability_prohibitions(capabilities, payload)
    return capabilities


def available_repository_modules(
    capabilities: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    return [
        module
        for module in AVAILABLE_MODULE_ORDER
        if bool(
            capabilities.get(
                MODULE_CAPABILITY_REQUIREMENTS[module], {}
            ).get("available")
        )
    ]


def _selected_layer_qc(
    payload: Mapping[str, Any],
    expression_layer_id: str | None,
) -> tuple[str | None, Mapping[str, Any] | None]:
    layers = payload.get("layers") or {}
    if not isinstance(layers, Mapping):
        layers = {}
    if expression_layer_id:
        row = layers.get(expression_layer_id)
        return (
            expression_layer_id,
            row if isinstance(row, Mapping) else None,
        )

    default_layer_id = str(
        payload.get("default_expression_layer_id") or ""
    ).strip()
    if default_layer_id:
        row = layers.get(default_layer_id)
        return (
            default_layer_id,
            row if isinstance(row, Mapping) else None,
        )
    defaults = [
        (str(layer_id), row)
        for layer_id, row in layers.items()
        if isinstance(row, Mapping) and bool(row.get("is_default"))
    ]
    if len(defaults) == 1:
        return defaults[0]
    if len(layers) == 1:
        layer_id, row = next(iter(layers.items()))
        return (
            str(layer_id),
            row if isinstance(row, Mapping) else None,
        )
    return None, None


def rank_signature_capability(
    *,
    gene_count: int,
    sample_count: int | None,
    missing_value_count: int | None,
    expression_layer_id: str | None,
    prerequisite_available: bool = True,
    prerequisite_reason: Any = None,
) -> dict[str, Any]:
    """Describe rank-scoring availability without guessing matrix completeness."""

    genes = max(0, int(gene_count or 0))
    samples = (
        max(0, int(sample_count)) if sample_count is not None else None
    )
    matrix_entry_count = genes * samples if samples is not None else None
    missing = (
        max(0, int(missing_value_count))
        if missing_value_count is not None
        else None
    )
    complete_matrix_verified = missing is not None and missing == 0
    available = bool(
        prerequisite_available
        and genes >= RANK_SIGNATURE_MINIMUM_GENES
        and matrix_entry_count is not None
        and matrix_entry_count <= RANK_SIGNATURE_MAXIMUM_MATRIX_ENTRIES
        and complete_matrix_verified
    )
    reason = None
    if not prerequisite_available:
        reason = str(
            prerequisite_reason
            or "The selected expression layer is not available for analysis."
        )
    elif genes < RANK_SIGNATURE_MINIMUM_GENES:
        reason = (
            "Rank-based scoring needs a broad expression layer with at least "
            f"{RANK_SIGNATURE_MINIMUM_GENES:,} unique genes; the selected "
            f"layer contains {genes:,}. Use Mean, Z-score or Weighted, or "
            "choose a complete broad expression layer."
        )
    elif matrix_entry_count is None:
        reason = (
            "Rank-based scoring is unavailable because TRACE could not verify "
            "the dimensions of the selected expression layer. Use Mean, "
            "Z-score or Weighted, or choose a fully attested layer."
        )
    elif matrix_entry_count > RANK_SIGNATURE_MAXIMUM_MATRIX_ENTRIES:
        reason = (
            "Rank-based scoring is unavailable because the selected expression "
            f"layer contains {matrix_entry_count:,} matrix entries; the current "
            f"limit is {RANK_SIGNATURE_MAXIMUM_MATRIX_ENTRIES:,}. Use Mean, "
            "Z-score or Weighted, or choose a smaller expression layer."
        )
    elif missing is None:
        reason = (
            "Rank-based scoring is unavailable because TRACE could not verify "
            "that every value in the selected expression layer is finite. "
            "Use Mean, Z-score or Weighted, or choose a verified complete layer."
        )
    elif missing:
        noun = "value" if missing == 1 else "values"
        reason = (
            "Rank-based scoring is unavailable because the selected expression "
            f"layer contains {missing:,} missing or non-finite {noun}. Upload "
            "a complete matrix, choose another expression layer, or use Mean, "
            "Z-score or Weighted."
        )
    return {
        "available": available,
        "reason": reason,
        "expression_layer_id": expression_layer_id,
        "gene_count": genes,
        "sample_count": samples,
        "minimum_genes": RANK_SIGNATURE_MINIMUM_GENES,
        "matrix_entry_count": matrix_entry_count,
        "maximum_matrix_entries": RANK_SIGNATURE_MAXIMUM_MATRIX_ENTRIES,
        "missing_value_count": missing,
        "complete_matrix_verified": complete_matrix_verified,
        "methods": ["singscore", "ssgsea", "aucell"],
    }


def rank_signature_capability_from_qc(
    qc: Mapping[str, Any] | None,
    *,
    expression_layer_id: str | None = None,
    prerequisite_available: bool = True,
    prerequisite_reason: Any = None,
) -> dict[str, Any]:
    """Resolve rank capability for the exact layer used by the engine."""

    payload = dict(qc or {})
    selected_id, layer = _selected_layer_qc(payload, expression_layer_id)
    if layer is not None:
        gene_count = int(layer.get("genes") or layer.get("gene_count") or 0)
        raw_sample_count = (
            layer.get("samples")
            if "samples" in layer
            else layer.get("sample_count")
        )
        if "nonfinite_values" in layer:
            missing_value_count: int | None = int(
                layer.get("nonfinite_values") or 0
            )
        elif "missing_cells" in layer:
            missing_value_count = int(layer.get("missing_cells") or 0)
        else:
            missing_value_count = None
        return rank_signature_capability(
            gene_count=gene_count,
            sample_count=(
                int(raw_sample_count) if raw_sample_count is not None else None
            ),
            missing_value_count=missing_value_count,
            expression_layer_id=selected_id,
            prerequisite_available=prerequisite_available,
            prerequisite_reason=prerequisite_reason,
        )

    # Private upload QC predates the generic layers block. Its single canonical
    # matrix is still identifiable and records the number of unavailable cells.
    expression = payload.get("expression") or {}
    if isinstance(expression, Mapping) and (
        not expression_layer_id or expression_layer_id == "uploaded_expression"
    ):
        raw_sample_count = expression.get("samples")
        missing_value_count = (
            int(expression.get("missing_cells") or 0)
            if "missing_cells" in expression
            else None
        )
        return rank_signature_capability(
            gene_count=int(expression.get("genes") or 0),
            sample_count=(
                int(raw_sample_count) if raw_sample_count is not None else None
            ),
            missing_value_count=missing_value_count,
            expression_layer_id=(expression_layer_id or "uploaded_expression"),
            prerequisite_available=prerequisite_available,
            prerequisite_reason=prerequisite_reason,
        )

    return rank_signature_capability(
        gene_count=0,
        sample_count=None,
        missing_value_count=None,
        expression_layer_id=expression_layer_id,
        prerequisite_available=prerequisite_available,
        prerequisite_reason=prerequisite_reason,
    )


def _molecular_counts(
    payload: Mapping[str, Any],
    expression_layer_id: str | None = None,
) -> tuple[int, int, int]:
    molecular = payload.get("molecular_population") or {}
    layers = payload.get("layers") or {}
    expression = payload.get("expression") or {}
    _, selected_layer = _selected_layer_qc(payload, expression_layer_id)
    layer_samples = int((selected_layer or {}).get("samples") or 0)
    layer_genes = int((selected_layer or {}).get("genes") or 0)
    patients = int(
        molecular.get("patients")
        or payload.get("patients")
        or (payload.get("matching") or {}).get("matched_patients")
        or 0
    )
    if expression_layer_id and selected_layer is not None and "patients" in selected_layer:
        patients = int(selected_layer["patients"])
    samples = int(
        layer_samples
        if expression_layer_id
        else (
            molecular.get("samples")
            or layer_samples
            or expression.get("samples")
            or payload.get("samples")
            or 0
        )
    )
    genes = int(
        layer_genes
        if expression_layer_id
        else (
            molecular.get("genes")
            or layer_genes
            or expression.get("genes")
            or 0
        )
    )
    return patients, samples, genes


def _apply_capability_prohibitions(
    capabilities: dict[str, dict[str, Any]],
    payload: Mapping[str, Any],
) -> None:
    policy = payload.get("capability_policy") or {}
    prohibited = policy.get("prohibited") or {}
    if not isinstance(prohibited, Mapping):
        return
    for capability, raw_reason in prohibited.items():
        if capability not in capabilities:
            continue
        reason = str(raw_reason or "").strip()
        capabilities[capability]["available"] = False
        capabilities[capability]["reason"] = (
            reason or "This analysis is prohibited by the curated study policy."
        )
        if capability == CAPABILITY_EXPRESSION:
            for dependent in (
                CAPABILITY_EXPRESSION_COMPARISON,
                CAPABILITY_GSEA,
                CAPABILITY_SURVIVAL,
            ):
                capabilities[dependent]["available"] = False
                capabilities[dependent]["reason"] = capabilities[
                    capability
                ]["reason"]
        if capability == CAPABILITY_SURVIVAL:
            capabilities[capability]["endpoint_ids"] = []
        if capability == CAPABILITY_RANK_BASED_SIGNATURE_SCORING:
            capabilities[capability]["methods"] = []
