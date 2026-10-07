from __future__ import annotations

from typing import Any

from app.clinical_grouping import CLINICAL_GROUPING_CATALOG_VERSION
from app.sample_population import SAMPLE_POPULATION_CONTRACT_VERSION
from app.signature_scoring import SIGNATURE_SCORING_CONTRACT_VERSION


ANALYSIS_PIPELINE_VERSION = (
    "server-attested-competing-risk-split-cox-contract-v6.25"
)
COMBINED_SIGNATURE_PIPELINE_VERSION = (
    "server-attested-competing-risk-split-cox-contract-v4.16"
)
SIGNATURE_PANEL_PIPELINE_VERSION = (
    "signature-panel-main-effects-cox-audit-v1.7"
)
MULTIVERSE_PIPELINE_VERSION = "server-attested-prespecified-multiverse-contract-v2.9"
PANCANCER_PIPELINE_VERSION = "server-attested-common-scale-reml-hksj-contract-v3.5"
HIERARCHICAL_PANCANCER_PIPELINE_VERSION = (
    "hierarchical-study-cancer-iqr-reml-mhksj-contract-v1.3"
)
SESSION_HISTORY_PIPELINE_VERSION = (
    "server-attested-exploratory-session-family-contract-v1.0"
)
GSEA_PIPELINE_VERSION = (
    "camera-estimated-correlation-bh-preranked-effect-contract-v2.3"
)
EXPRESSION_COMPARISON_PIPELINE_VERSION = (
    "grouped-expression-comparison-welch-wilcoxon-bh-contract-v1.5"
)
IMMUNE_ATLAS_PIPELINE_VERSION = (
    "immune-pancancer-declared-primary-disease-ordinal-sensitivity-cox-audit-v2.2"
)


COMPUTE_PIPELINE_VERSIONS = {
    "analysis": ANALYSIS_PIPELINE_VERSION,
    "combined": COMBINED_SIGNATURE_PIPELINE_VERSION,
    "signature_panel": SIGNATURE_PANEL_PIPELINE_VERSION,
    "batch": ANALYSIS_PIPELINE_VERSION,
    "multiverse": MULTIVERSE_PIPELINE_VERSION,
    "pancancer": PANCANCER_PIPELINE_VERSION,
    "pancancer_hierarchical": HIERARCHICAL_PANCANCER_PIPELINE_VERSION,
    "session": SESSION_HISTORY_PIPELINE_VERSION,
    "gsea": GSEA_PIPELINE_VERSION,
    "expression_comparison": EXPRESSION_COMPARISON_PIPELINE_VERSION,
}

CLINICAL_CATALOG_COMPUTE_KINDS = {
    "analysis",
    "combined",
    "signature_panel",
    "batch",
    "multiverse",
    "gsea",
    "expression_comparison",
}

SIGNATURE_SCORING_COMPUTE_KINDS = {
    "analysis",
    "combined",
    "signature_panel",
    "batch",
    "multiverse",
    "pancancer",
    "gsea",
    "expression_comparison",
}


def compute_cache_context(
    kind: str,
    *,
    data_version: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the scientific context that participates in public-job identity."""
    context = {
        "pipeline_version": COMPUTE_PIPELINE_VERSIONS.get(kind, "unknown"),
        "sample_population_contract": SAMPLE_POPULATION_CONTRACT_VERSION,
        "data_version": data_version,
    }
    if kind in CLINICAL_CATALOG_COMPUTE_KINDS:
        context["clinical_grouping_catalog"] = CLINICAL_GROUPING_CATALOG_VERSION
    if kind in SIGNATURE_SCORING_COMPUTE_KINDS:
        context["signature_scoring_contract"] = (
            SIGNATURE_SCORING_CONTRACT_VERSION
        )
    if kind == "batch":
        context["grouped_family_contract"] = "compare-grouped-family-v1"
    return context
