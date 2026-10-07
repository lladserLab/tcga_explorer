"""Read-only registry for datasets that are not yet production releases.

Candidate records are intentionally separate from ``RepositoryDataset``.  A
candidate can document useful public evidence without acquiring a compute ID
or being mistaken for a cohort that passed TRACE repository QC.
"""

from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
from typing import Any


CANDIDATE_REGISTRY_SCHEMA = "tcga-trace-dataset-candidate-registry-v1"


class CandidateRegistryError(RuntimeError):
    """Raised when the curated registry itself is absent or invalid."""


def candidate_registry_path(module_path: Path | str) -> Path:
    resolved = Path(module_path).resolve()
    for parent in resolved.parents:
        candidate = (
            parent / "repository_registry" / "dataset_candidates_v1.json"
        )
        if candidate.is_file():
            return candidate
    return (
        resolved.parents[2]
        / "repository_registry"
        / "dataset_candidates_v1.json"
    )


DEFAULT_CANDIDATE_REGISTRY_PATH = candidate_registry_path(__file__)

CAPABILITY_ALIASES = {
    "analysis": "survival",
    "survival": "survival",
    "compare": "survival",
    "robustness": "survival",
    "multiverse": "survival",
    "expression": "expression_comparison",
    "expression_comparison": "expression_comparison",
    "gsea": "gsea",
    "hierarchical_pancancer": "hierarchical_pancancer",
    "pancancer_hierarchical": "hierarchical_pancancer",
}

_CAPABILITY_DECISIONS = {
    "enabled",
    "disabled",
    "pending",
    "not_applicable",
}
_CANDIDATE_STATUSES = {
    "promoted",
    "under_review",
    "access_required",
    "not_eligible",
}


def normalize_candidate_analysis_type(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    normalized = str(value).strip().lower()
    try:
        return CAPABILITY_ALIASES[normalized]
    except KeyError as exc:
        raise ValueError(
            "analysis_type must be survival, compare, robustness, "
            "expression_comparison, gsea or hierarchical_pancancer."
        ) from exc


def load_dataset_candidate_registry(
    path: Path | str = DEFAULT_CANDIDATE_REGISTRY_PATH,
) -> dict[str, Any]:
    registry_path = Path(path)
    if not registry_path.is_file():
        raise FileNotFoundError(
            f"Dataset candidate registry not found: {registry_path}"
        )
    stat = registry_path.stat()
    return _load_registry_cached(
        str(registry_path.resolve()),
        stat.st_mtime_ns,
        stat.st_size,
    )


@lru_cache(maxsize=8)
def _load_registry_cached(
    path: str,
    _mtime_ns: int,
    _size: int,
) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        _validate_registry(payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise CandidateRegistryError(
            f"Dataset candidate registry could not be validated: {exc}"
        ) from exc
    return payload


def clear_dataset_candidate_registry_cache() -> None:
    _load_registry_cached.cache_clear()


def list_dataset_candidates(
    path: Path | str = DEFAULT_CANDIDATE_REGISTRY_PATH,
    *,
    disease_id: str | None = None,
    status: str | None = None,
    analysis_type: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    registry = load_dataset_candidate_registry(path)
    capability = normalize_candidate_analysis_type(analysis_type)
    normalized_disease = str(disease_id or "").strip().upper()
    normalized_status = str(status or "").strip().lower()
    if normalized_status and normalized_status not in _CANDIDATE_STATUSES:
        raise ValueError(
            "status must be promoted, under_review, access_required or "
            "not_eligible."
        )
    needle = str(query or "").strip().casefold()

    rows: list[dict[str, Any]] = []
    for candidate in registry["candidates"]:
        disease = candidate["disease"]
        if normalized_disease and str(disease["id"]).upper() != normalized_disease:
            continue
        if normalized_status and candidate["status"] != normalized_status:
            continue
        if capability:
            decision = candidate["capabilities"][capability]["decision"]
            if decision not in {"enabled", "pending"}:
                continue
        if needle and needle not in _candidate_search_text(candidate):
            continue
        rows.append(candidate)

    return {
        "schema_version": registry["schema_version"],
        "source_cutoff": registry["source_cutoff"],
        "updated_at": registry["updated_at"],
        "filters": {
            "disease_id": normalized_disease or None,
            "status": normalized_status or None,
            "analysis_type": capability,
            "query": str(query or "").strip() or None,
        },
        "count": len(rows),
        "candidates": rows,
    }


def _candidate_search_text(candidate: dict[str, Any]) -> str:
    source = candidate["source"]
    disease = candidate["disease"]
    blocker_values = [
        value
        for blocker in candidate.get("blockers") or []
        for value in (
            (
                blocker.get("code"),
                blocker.get("detail"),
            )
            if isinstance(blocker, dict)
            else (blocker,)
        )
    ]
    values = [
        candidate["id"],
        candidate["label"],
        disease["id"],
        disease["label"],
        source["repository"],
        source["accession"],
        candidate["tier"],
        candidate["status"],
        candidate["access_class"],
        *blocker_values,
    ]
    return " ".join(str(value or "") for value in values).casefold()


def _validate_registry(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Dataset candidate registry must be a JSON object.")
    if payload.get("schema_version") != CANDIDATE_REGISTRY_SCHEMA:
        raise ValueError("Unsupported dataset candidate registry schema.")
    for key in ("source_cutoff", "updated_at"):
        if not str(payload.get(key) or "").strip():
            raise ValueError(f"Candidate registry requires {key}.")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("Candidate registry requires a candidates array.")

    seen: set[str] = set()
    required_capabilities = {
        "catalog",
        "expression_comparison",
        "gsea",
        "survival",
        "hierarchical_pancancer",
    }
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(f"Candidate {index} must be an object.")
        candidate_id = str(candidate.get("id") or "").strip()
        if not candidate_id:
            raise ValueError(f"Candidate {index} requires id.")
        if candidate_id in seen:
            raise ValueError(f"Duplicate candidate id {candidate_id!r}.")
        seen.add(candidate_id)
        for key in ("label", "tier", "status", "access_class"):
            if not str(candidate.get(key) or "").strip():
                raise ValueError(f"Candidate {candidate_id} requires {key}.")
        if candidate["status"] not in _CANDIDATE_STATUSES:
            raise ValueError(
                f"Candidate {candidate_id} has unsupported status "
                f"{candidate['status']!r}."
            )
        _required_text_object(candidate, candidate_id, "disease", ("id", "label"))
        _required_text_object(
            candidate,
            candidate_id,
            "source",
            ("repository", "accession"),
        )
        capabilities = candidate.get("capabilities")
        if not isinstance(capabilities, dict):
            raise ValueError(f"Candidate {candidate_id} requires capabilities.")
        missing = sorted(required_capabilities - set(capabilities))
        extra = sorted(set(capabilities) - required_capabilities)
        if missing or extra:
            raise ValueError(
                f"Candidate {candidate_id} capability keys do not match the "
                f"contract (missing={missing}, extra={extra})."
            )
        for name in sorted(required_capabilities):
            row = capabilities[name]
            if not isinstance(row, dict):
                raise ValueError(
                    f"Candidate {candidate_id} capability {name} must be an object."
                )
            if not isinstance(row.get("available"), bool):
                raise ValueError(
                    f"Candidate {candidate_id} capability {name} requires available."
                )
            decision = str(row.get("decision") or "")
            if decision not in _CAPABILITY_DECISIONS:
                raise ValueError(
                    f"Candidate {candidate_id} capability {name} has invalid decision."
                )
            if not str(row.get("reason") or "").strip():
                raise ValueError(
                    f"Candidate {candidate_id} capability {name} requires reason."
                )
            if row["available"] != (decision == "enabled"):
                raise ValueError(
                    f"Candidate {candidate_id} capability {name} availability "
                    "must agree with its decision."
                )
        decisions = candidate.get("decisions")
        if not isinstance(decisions, dict):
            raise ValueError(f"Candidate {candidate_id} requires decisions.")
        for field in (
            "catalog_state",
            "promotion_state",
            "hierarchical_state",
        ):
            if not str(decisions.get(field) or "").strip():
                raise ValueError(
                    f"Candidate {candidate_id} decisions requires {field}."
                )
        blockers = candidate.get("blockers")
        if not isinstance(blockers, list):
            raise ValueError(f"Candidate {candidate_id} requires blockers array.")
        for blocker in blockers:
            if not isinstance(blocker, dict) or not str(
                blocker.get("code") or ""
            ).strip() or not str(blocker.get("detail") or "").strip():
                raise ValueError(
                    f"Candidate {candidate_id} blockers require code and detail."
                )
        links = candidate.get("links")
        if not isinstance(links, list):
            raise ValueError(f"Candidate {candidate_id} requires links array.")
        for link in links:
            if (
                not isinstance(link, dict)
                or not str(link.get("rel") or "").strip()
                or not str(link.get("url") or "").strip()
            ):
                raise ValueError(
                    f"Candidate {candidate_id} links require rel and url."
                )

        promoted = candidate["status"] == "promoted"
        promotion_state = str(decisions.get("promotion_state") or "")
        if promoted:
            if promotion_state != "promoted":
                raise ValueError(
                    f"Promoted candidate {candidate_id} must declare "
                    "promotion_state=promoted."
                )
            if not capabilities["catalog"]["available"] or not any(
                capabilities[name]["available"]
                for name in ("expression_comparison", "gsea", "survival")
            ):
                raise ValueError(
                    f"Promoted candidate {candidate_id} is not analysis-ready."
                )
        else:
            if promotion_state == "promoted":
                raise ValueError(
                    f"Candidate {candidate_id} cannot declare promoted before "
                    "its status is promoted."
                )
            unexpectedly_available = [
                name
                for name in (
                    "expression_comparison",
                    "gsea",
                    "survival",
                    "hierarchical_pancancer",
                )
                if capabilities[name]["available"]
            ]
            if unexpectedly_available:
                raise ValueError(
                    f"Unpromoted candidate {candidate_id} exposes analysis "
                    f"capabilities: {', '.join(unexpectedly_available)}."
                )

    _validate_registry_summary(payload, candidates, seen)


def _validate_registry_summary(
    payload: dict[str, Any],
    candidates: list[dict[str, Any]],
    candidate_ids: set[str],
) -> None:
    counts = payload.get("counts")
    if counts is not None:
        if not isinstance(counts, dict):
            raise ValueError("Candidate registry counts must be an object.")
        expected_status = {
            status: sum(row["status"] == status for row in candidates)
            for status in sorted(_CANDIDATE_STATUSES)
        }
        expected_tier = {
            tier: sum(row["tier"] == tier for row in candidates)
            for tier in sorted({row["tier"] for row in candidates})
        }
        expected_scalars = {
            "candidates": len(candidates),
            "explicitly_dispositioned": len(candidates),
            "analysis_ready": expected_status["promoted"],
        }
        for field, expected in expected_scalars.items():
            if counts.get(field) != expected:
                raise ValueError(
                    f"Candidate registry count {field} must equal {expected}."
                )
        if counts.get("by_status") != expected_status:
            raise ValueError("Candidate registry by_status counts are inconsistent.")
        if counts.get("by_tier") != expected_tier:
            raise ValueError("Candidate registry by_tier counts are inconsistent.")

    coverage = payload.get("inventory_coverage")
    if coverage is not None:
        if not isinstance(coverage, dict) or coverage.get("complete") is not True:
            raise ValueError(
                "Candidate registry inventory coverage must be complete."
            )
        expected_digest = hashlib.sha256(
            "\n".join(sorted(candidate_ids)).encode("utf-8")
        ).hexdigest()
        if coverage.get("candidate_id_set_sha256") != expected_digest:
            raise ValueError(
                "Candidate registry candidate id digest is inconsistent."
            )


def _required_text_object(
    candidate: dict[str, Any],
    candidate_id: str,
    key: str,
    fields: tuple[str, ...],
) -> None:
    value = candidate.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Candidate {candidate_id} requires {key}.")
    for field in fields:
        if not str(value.get(field) or "").strip():
            raise ValueError(
                f"Candidate {candidate_id} {key} requires {field}."
            )
