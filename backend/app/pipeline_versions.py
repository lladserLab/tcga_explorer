from __future__ import annotations

from typing import Any


ANALYSIS_PIPELINE_VERSION = "server-attested-competing-risk-contract-v6.13"
COMBINED_SIGNATURE_PIPELINE_VERSION = "server-attested-competing-risk-contract-v4.5"
MULTIVERSE_PIPELINE_VERSION = "server-attested-prespecified-multiverse-contract-v2.2"
PANCANCER_PIPELINE_VERSION = "server-attested-common-scale-reml-hksj-contract-v3.2"
SESSION_HISTORY_PIPELINE_VERSION = (
    "server-attested-exploratory-session-family-contract-v1.0"
)
IMMUNE_ATLAS_PIPELINE_VERSION = (
    "immune-pancancer-primary-plus-ordinal-sensitivity-cox-audit-v2.1"
)


COMPUTE_PIPELINE_VERSIONS = {
    "analysis": ANALYSIS_PIPELINE_VERSION,
    "combined": COMBINED_SIGNATURE_PIPELINE_VERSION,
    "batch": ANALYSIS_PIPELINE_VERSION,
    "multiverse": MULTIVERSE_PIPELINE_VERSION,
    "pancancer": PANCANCER_PIPELINE_VERSION,
    "session": SESSION_HISTORY_PIPELINE_VERSION,
}


def compute_cache_context(
    kind: str,
    *,
    data_version: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the scientific context that participates in public-job identity."""
    return {
        "pipeline_version": COMPUTE_PIPELINE_VERSIONS.get(kind, "unknown"),
        "data_version": data_version,
    }
