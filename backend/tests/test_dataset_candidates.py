import json

import pytest

from app.repository.candidates import (
    CANDIDATE_REGISTRY_SCHEMA,
    CandidateRegistryError,
    candidate_registry_path,
    clear_dataset_candidate_registry_cache,
    list_dataset_candidates,
    load_dataset_candidate_registry,
)


def capability(decision, reason="Reviewed decision"):
    return {
        "available": decision == "enabled",
        "decision": decision,
        "reason": reason,
    }


def registry_payload():
    return {
        "schema_version": CANDIDATE_REGISTRY_SCHEMA,
        "source_cutoff": "2026-08-20",
        "updated_at": "2026-08-20",
        "candidates": [
            {
                "id": "target-aml",
                "label": "TARGET AML",
                "disease": {"id": "PAML", "label": "Pediatric AML"},
                "source": {"repository": "GDC", "accession": "TARGET-AML"},
                "tier": "S1",
                "status": "under_review",
                "access_class": "public",
                "capabilities": {
                    "catalog": capability("pending"),
                    "expression_comparison": capability("pending"),
                    "gsea": capability("pending"),
                    "survival": capability("pending"),
                    "hierarchical_pancancer": capability("pending"),
                },
                "decisions": {
                    "catalog_state": "under_review",
                    "promotion_state": "audit_required",
                    "hierarchical_state": "preflight_pending",
                },
                "blockers": [
                    {
                        "code": "release_audit_pending",
                        "detail": "Release audit is not complete.",
                    }
                ],
                "links": [
                    {
                        "rel": "source",
                        "url": "https://portal.gdc.cancer.gov/projects/TARGET-AML",
                    }
                ],
            },
            {
                "id": "controlled-fl",
                "label": "Controlled follicular lymphoma",
                "disease": {"id": "FL", "label": "Follicular lymphoma"},
                "source": {"repository": "dbGaP", "accession": "phs-test"},
                "tier": "C",
                "status": "access_required",
                "access_class": "controlled",
                "capabilities": {
                    "catalog": capability("pending"),
                    "expression_comparison": capability("disabled"),
                    "gsea": capability("disabled"),
                    "survival": capability("disabled"),
                    "hierarchical_pancancer": capability("disabled"),
                },
                "decisions": {
                    "catalog_state": "access_required",
                    "promotion_state": "blocked",
                    "hierarchical_state": "blocked",
                },
                "blockers": [
                    {
                        "code": "controlled_access",
                        "detail": "Controlled access is required.",
                    }
                ],
                "links": [],
            },
        ],
    }


@pytest.fixture
def registry_path(tmp_path):
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(registry_payload()), encoding="utf-8")
    clear_dataset_candidate_registry_cache()
    return path


def test_candidate_registry_is_validated_and_filterable(registry_path):
    loaded = load_dataset_candidate_registry(registry_path)
    assert loaded["source_cutoff"] == "2026-08-20"

    result = list_dataset_candidates(
        registry_path,
        disease_id="paml",
        status="under_review",
        analysis_type="survival",
        query="target",
    )

    assert result["count"] == 1
    assert result["candidates"][0]["id"] == "target-aml"
    assert result["filters"]["analysis_type"] == "survival"


def test_candidate_registry_rejects_implicit_capability_state(registry_path):
    payload = registry_payload()
    del payload["candidates"][0]["capabilities"]["gsea"]["decision"]
    registry_path.write_text(json.dumps(payload), encoding="utf-8")
    clear_dataset_candidate_registry_cache()

    with pytest.raises(CandidateRegistryError, match="invalid decision"):
        load_dataset_candidate_registry(registry_path)


def test_candidate_registry_rejects_unknown_filter(registry_path):
    with pytest.raises(ValueError, match="analysis_type must be"):
        list_dataset_candidates(registry_path, analysis_type="magic")


def test_candidate_registry_path_supports_container_layout(tmp_path):
    module = tmp_path / "app" / "repository" / "candidates.py"
    module.parent.mkdir(parents=True)
    module.touch()
    registry = tmp_path / "repository_registry" / "dataset_candidates_v1.json"
    registry.parent.mkdir()
    registry.write_text("{}", encoding="utf-8")

    assert candidate_registry_path(module) == registry


def test_candidate_registry_rejects_unpromoted_analysis_capability(
    registry_path,
):
    payload = registry_payload()
    payload["candidates"][0]["capabilities"]["gsea"] = capability("enabled")
    registry_path.write_text(json.dumps(payload), encoding="utf-8")
    clear_dataset_candidate_registry_cache()

    with pytest.raises(CandidateRegistryError, match="Unpromoted candidate"):
        load_dataset_candidate_registry(registry_path)


def test_candidate_registry_rejects_inconsistent_summary_counts(
    registry_path,
):
    payload = registry_payload()
    payload["counts"] = {
        "candidates": 99,
        "explicitly_dispositioned": 2,
        "analysis_ready": 0,
        "by_status": {
            "promoted": 0,
            "under_review": 1,
            "access_required": 1,
            "not_eligible": 0,
        },
        "by_tier": {"S1": 1, "C": 1},
    }
    registry_path.write_text(json.dumps(payload), encoding="utf-8")
    clear_dataset_candidate_registry_cache()

    with pytest.raises(CandidateRegistryError, match="count candidates"):
        load_dataset_candidate_registry(registry_path)
