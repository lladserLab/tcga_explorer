from __future__ import annotations

from typing import Any, Mapping


STUDY_SPEC_SCHEMA_VERSION_V1 = "tcga-trace-study-spec-v1"
STUDY_SPEC_SCHEMA_VERSION_V2 = "tcga-trace-study-spec-v2"
SUPPORTED_STUDY_SPEC_SCHEMA_VERSIONS = frozenset(
    {STUDY_SPEC_SCHEMA_VERSION_V1, STUDY_SPEC_SCHEMA_VERSION_V2}
)

BUNDLE_SCHEMA_VERSION_V1 = "tcga-trace-external-rnaseq-bundle-v1"
BUNDLE_SCHEMA_VERSION_V2 = "tcga-trace-external-rnaseq-bundle-v2"
SUPPORTED_BUNDLE_SCHEMA_VERSIONS = frozenset(
    {BUNDLE_SCHEMA_VERSION_V1, BUNDLE_SCHEMA_VERSION_V2}
)


def require_supported_study_spec(
    spec: Mapping[str, Any],
) -> str:
    schema_version = str(spec.get("schema_version") or "")
    if schema_version not in SUPPORTED_STUDY_SPEC_SCHEMA_VERSIONS:
        raise ValueError("Unsupported repository study specification.")
    return schema_version


def bundle_schema_for_study_spec(spec_schema_version: str) -> str:
    if spec_schema_version == STUDY_SPEC_SCHEMA_VERSION_V1:
        return BUNDLE_SCHEMA_VERSION_V1
    if spec_schema_version == STUDY_SPEC_SCHEMA_VERSION_V2:
        return BUNDLE_SCHEMA_VERSION_V2
    raise ValueError("Unsupported repository study specification.")


def is_capability_first_schema(schema_version: str) -> bool:
    return schema_version in {
        STUDY_SPEC_SCHEMA_VERSION_V2,
        BUNDLE_SCHEMA_VERSION_V2,
    }
