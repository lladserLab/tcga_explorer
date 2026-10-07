"""Application service for the isolated hierarchical pan-cancer workflow.

This module intentionally does not extend the historical TCGA pan-cancer
implementation.  It resolves auditable study universes, prepares one patient
record per study participant, fits release-specific effects and only then
combines compatible evidence.
"""

from __future__ import annotations

from collections import defaultdict
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import html
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.attestation import write_attestation_receipt
from app.config import Settings
from app.expression import (
    GeneNotFoundError,
    gdc_expression_gene_provenance,
    get_expression_for_gene,
)
from app.hierarchical_pancancer import (
    HIERARCHICAL_EFFECT_SCALE,
    HIERARCHICAL_EFFECT_SCALE_LABEL,
    hierarchical_meta_analysis,
    run_hierarchical_release_cox,
)
from app.models import (
    ClinicalEndpoint,
    Cohort,
    RepositoryDataset,
    RepositoryEndpointDefinition,
    RepositoryRelease,
    Sample,
)
from app.pancancer_study_universes import (
    ClinicalContext,
    DEFAULT_STUDY_UNIVERSE_REGISTRY_FILENAME,
    EvidenceTier,
    PreflightPolicy,
    PreflightThresholds,
    SourceKind,
    StudyUniverseDefinition,
    StudyUniverseObservation,
    SynthesisTarget,
    TimeOriginClass,
    load_study_universe_registry,
    preflight_study_universes,
)
from app.pipeline_versions import HIERARCHICAL_PANCANCER_PIPELINE_VERSION
from app.r_runner import stable_hash
from app.repository.service import (
    require_repository_capability,
    repository_endpoint_outcomes,
    repository_gene_expression,
    repository_samples,
    resolve_repository_context,
)
from app.schemas import AnalysisFilters, HierarchicalPanCancerRequest
from app.survival import (
    ClinicalOutcome,
    filter_sample_candidates,
    sample_os_outcome,
    select_expression_complete_samples,
)


PREFLIGHT_SCHEMA = "tcga-trace-hierarchical-pancancer-preflight-v1"
RESULT_SCHEMA = "tcga-trace-hierarchical-pancancer-result-v1"
AUDIT_SCHEMA = "tcga-trace-hierarchical-pancancer-audit-v1"


@dataclass
class HierarchicalPreflightBundle:
    payload: dict[str, Any]
    prepared: dict[str, dict[str, Any]]
    registry_version: str
    data_version: dict[str, Any]


def hierarchical_scan_identity(
    request: HierarchicalPanCancerRequest,
    *,
    tcga_data_version: Mapping[str, Any],
    repository_version: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind a computed artifact to both its estimand and literal gene query.

    Alias and canonical requests use the same resolved symbol and therefore
    select the same scientific universe, but they remain separate artifacts so
    requested-symbol provenance never depends on which query populated a cache
    first.
    """

    return {
        "kind": "pancancer_hierarchical",
        "pipeline_version": HIERARCHICAL_PANCANCER_PIPELINE_VERSION,
        "request": request.model_dump(mode="json"),
        "gene_resolution": request.gene_resolution,
        "tcga_data_version": dict(tcga_data_version),
        "hierarchical_repository_version": dict(repository_version),
    }


def hierarchical_repository_version(
    db: Session,
    settings: Settings,
) -> dict[str, Any]:
    """Return every scientific input that determines the study universe.

    The aggregate digest deliberately covers inactive study manifests as well
    as active releases.  A manifest can change cancer grouping, time origin or
    clinical context before it becomes the preferred release, so omitting it
    would allow a stale completed-job cache to survive a registry revision.
    """

    rows = db.execute(
        select(
            RepositoryDataset.id,
            RepositoryDataset.active_release_id,
            RepositoryRelease.manifest_hash,
        )
        .join(
            RepositoryRelease,
            RepositoryRelease.id == RepositoryDataset.active_release_id,
        )
        .where(
            RepositoryDataset.status == "available",
            RepositoryDataset.visibility == "public",
            RepositoryRelease.status == "published",
            RepositoryRelease.qc_status == "passed",
        )
        .order_by(RepositoryDataset.id)
    ).all()
    active_releases = {
        str(dataset_id): {
            "release_id": str(release_id),
            "manifest_hash": str(manifest_hash),
        }
        for dataset_id, release_id, manifest_hash in rows
        if release_id
    }
    registry = _load_registry(settings, active_releases)
    registry_bundle = _registry_bundle_identity(
        settings,
        registry=registry,
        active_releases=active_releases,
    )
    return {
        "study_universe_registry": {
            "version": registry.registry_version,
            "schema_version": registry.schema_version,
            "sha256": _sha256_file(Path(registry.source_path)),
        },
        "registry_bundle_sha256": registry_bundle["sha256"],
        "registry_bundle": registry_bundle,
        "external_releases": active_releases,
    }


def _registry_bundle_identity(
    settings: Settings,
    *,
    registry: Any,
    active_releases: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a canonical, auditable digest of the complete registry bundle."""

    registry_root = Path(settings.cancer_repository_registry_dir)
    registry_path = Path(registry.source_path)
    cancer_types_path = registry_root / "cancer_types.json"
    manifests_root = registry_root / "studies"
    manifest_hashes = {
        path.relative_to(registry_root).as_posix(): _sha256_file(path)
        for path in sorted(manifests_root.glob("*.json"))
        if path.is_file()
    }
    release_identity = {
        str(dataset_id): {
            "release_id": str(metadata.get("release_id") or ""),
            "manifest_hash": str(metadata.get("manifest_hash") or ""),
        }
        for dataset_id, metadata in sorted(active_releases.items())
    }
    digest_payload = {
        "schema_version": str(registry.schema_version),
        "registry_version": str(registry.registry_version),
        "registry_files": {
            registry_path.relative_to(registry_root).as_posix(): _sha256_file(
                registry_path
            ),
            cancer_types_path.relative_to(registry_root).as_posix(): (
                _sha256_file(cancer_types_path)
            ),
            **manifest_hashes,
        },
        "external_releases": release_identity,
    }
    canonical = json.dumps(
        digest_payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    study_manifest_payload = json.dumps(
        manifest_hashes,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "sha256": hashlib.sha256(canonical).hexdigest(),
        "file_count": len(digest_payload["registry_files"]),
        "cancer_types_sha256": _sha256_file(cancer_types_path),
        "study_manifests": {
            "count": len(manifest_hashes),
            "sha256": hashlib.sha256(study_manifest_payload).hexdigest(),
        },
    }


def build_hierarchical_preflight(
    request: HierarchicalPanCancerRequest,
    db: Session,
    settings: Settings,
) -> HierarchicalPreflightBundle:
    gene_resolution = request.gene_resolution
    data_version = hierarchical_repository_version(db, settings)
    registry = _load_registry(settings, data_version["external_releases"])
    definitions = _selected_definitions(registry.definitions, request)
    target = _synthesis_target(request)
    policy = PreflightPolicy(
        primary=PreflightThresholds(
            request.min_patients,
            request.min_events,
            request.min_censored,
        ),
        exploratory=registry.preflight_policy.exploratory,
        endpoint_class="OS",
    )

    prepared: dict[str, dict[str, Any]] = {}
    observations: list[StudyUniverseObservation] = []
    preparation_errors: dict[str, dict[str, str]] = {}
    for definition in definitions:
        if _definition_matches_target(definition, target):
            try:
                release = _prepare_universe(
                    definition,
                    request.resolved_gene_symbol,
                    db,
                    settings,
                )
                prepared[definition.universe_id] = release
                observations.append(
                    StudyUniverseObservation(
                        universe_id=definition.universe_id,
                        n_patients=len(release["records"]),
                        n_events=sum(
                            int(record["event"])
                            for record in release["records"]
                        ),
                        n_censored=sum(
                            1 - int(record["event"])
                            for record in release["records"]
                        ),
                        release_id=release["release_id"],
                        expression_available=True,
                    )
                )
            except GeneNotFoundError as exc:
                nominal = _nominal_observation(definition, db)
                observations.append(
                    StudyUniverseObservation(
                        universe_id=definition.universe_id,
                        n_patients=nominal["n_patients"],
                        n_events=nominal["n_events"],
                        n_censored=nominal["n_censored"],
                        release_id=nominal.get("release_id"),
                        expression_available=False,
                    )
                )
                preparation_errors[definition.universe_id] = {
                    "code": "GENE_NOT_AVAILABLE",
                    "message": str(exc),
                }
            except (ValueError, OSError) as exc:
                preparation_errors[definition.universe_id] = {
                    "code": _preparation_error_code(exc),
                    "message": str(exc),
                }
        else:
            nominal = _nominal_observation(definition, db)
            if nominal["observed"]:
                observations.append(
                    StudyUniverseObservation(
                        universe_id=definition.universe_id,
                        n_patients=nominal["n_patients"],
                        n_events=nominal["n_events"],
                        n_censored=nominal["n_censored"],
                        release_id=nominal.get("release_id"),
                        expression_available=True,
                    )
                )

    report = preflight_study_universes(
        definitions,
        observations,
        target=target,
        policy=policy,
    )
    definition_by_id = {row.universe_id: row for row in definitions}
    universes: list[dict[str, Any]] = []
    for decision in report.decisions:
        definition = definition_by_id[decision.universe_id]
        definition_payload = definition.as_dict()
        if definition.manifest_path:
            definition_payload["manifest_path"] = (
                "repository_registry/studies/"
                + Path(definition.manifest_path).name
            )
        row = {
            **definition_payload,
            **decision.as_dict(),
            "name": definition.name,
            "dataset_id": definition.universe_id,
            "preferred_dataset_id": definition.preferred_dataset_id,
            "status": decision.evidence_tier.value,
            "included": decision.evidence_tier is EvidenceTier.PRIMARY,
            "analysis_eligible": (
                decision.evidence_tier is EvidenceTier.PRIMARY
                or (
                    request.include_exploratory
                    and decision.evidence_tier is EvidenceTier.EXPLORATORY
                )
            ),
            "patients": decision.n_patients,
            "events": decision.n_events,
            "censored": decision.n_censored,
            "reasons": [
                _reason_payload(reason) for reason in decision.reasons
            ],
            "preparation_error": preparation_errors.get(decision.universe_id),
            "expression_scale": (
                prepared.get(decision.universe_id, {}).get("expression_scale")
            ),
            "gene_mapping": (
                prepared.get(decision.universe_id, {}).get("gene_mapping")
            ),
        }
        if row["preparation_error"]:
            row["reasons"].append(
                {
                    "code": row["preparation_error"]["code"],
                    "label": row["preparation_error"]["message"],
                }
            )
        universes.append(row)

    primary = [row for row in universes if row["status"] == "primary"]
    exploratory = [
        row for row in universes if row["status"] == "exploratory"
    ]
    accepted = primary + (exploratory if request.include_exploratory else [])
    primary_clusters_by_cancer: dict[str, set[str]] = {}
    for row in primary:
        primary_clusters_by_cancer.setdefault(row["cancer_code"], set()).add(
            row["study_cluster_id"]
        )
    replicated_cancer_codes = {
        cancer_code
        for cancer_code, cluster_ids in primary_clusters_by_cancer.items()
        if len(cluster_ids) >= 2
    }
    replicated_primary = [
        row
        for row in primary
        if row["cancer_code"] in replicated_cancer_codes
    ]
    replicated_events = sum(
        int(row["n_events"] or 0) for row in replicated_primary
    )
    replicated_patients = sum(
        int(row["n_patients"] or 0) for row in replicated_primary
    )
    cancer_groups = _cancer_groups(universes)
    summary = {
        "catalog_universes": len(registry.definitions),
        "hierarchical_active_universes": sum(
            row["registry_category"] == "hierarchical_active"
            for row in universes
        ),
        "catalog_only_universes": sum(
            row["registry_category"] == "catalog_only"
            for row in universes
        ),
        "selected_universes": len(universes),
        "total_studies": len(universes),
        "primary_studies": len(primary),
        "exploratory_studies": len(exploratory),
        "included_studies": len(accepted),
        "excluded_studies": len(universes) - len(accepted),
        "cancers": len({row["cancer_code"] for row in accepted}),
        "primary_cancers": len(primary_clusters_by_cancer),
        "replicated_cancers": len(replicated_cancer_codes),
        "replicated_cancer_codes": sorted(replicated_cancer_codes),
        "replicated_patients": replicated_patients,
        "replicated_events": replicated_events,
        "preliminary_global_ready": len(replicated_cancer_codes) >= 2,
        "formal_global_ready": (
            len(replicated_cancer_codes) >= 5
            and replicated_events >= 100
        ),
        "independent_clusters": len(
            {row["study_cluster_id"] for row in accepted}
        ),
        "patients": sum(int(row["n_patients"] or 0) for row in accepted),
        "events": sum(int(row["n_events"] or 0) for row in accepted),
        "censored": sum(int(row["n_censored"] or 0) for row in accepted),
        "endpoint": "OS",
        "clinical_context": request.clinical_context,
        "time_origin_class": target.time_origin_class.value,
        "effect_unit": HIERARCHICAL_EFFECT_SCALE_LABEL,
        "can_run": len(primary) >= 1,
        "sources": {
            "tcga": sum(row["source_kind"] == "tcga" for row in accepted),
            "external": sum(
                row["source_kind"] == "external" for row in accepted
            ),
        },
    }
    warnings = _preflight_warnings(summary, request)
    if gene_resolution["resolution"] == "alias":
        warnings.insert(
            0,
            "Gene alias "
            f"{gene_resolution['requested_gene_symbol']} was resolved to "
            f"{gene_resolution['resolved_gene_symbol']} before selecting "
            "TCGA and external study universes.",
        )
    payload = {
        "schema_version": PREFLIGHT_SCHEMA,
        "pipeline_version": HIERARCHICAL_PANCANCER_PIPELINE_VERSION,
        "registry_version": registry.registry_version,
        **gene_resolution,
        "request": {
            **request.model_dump(mode="json"),
            **gene_resolution,
        },
        "summary": summary,
        "universes": universes,
        "cancer_groups": cancer_groups,
        "warnings": warnings,
    }
    return HierarchicalPreflightBundle(
        payload=payload,
        prepared=prepared,
        registry_version=registry.registry_version,
        data_version=data_version,
    )


def run_hierarchical_pancancer_analysis(
    request: HierarchicalPanCancerRequest,
    db: Session,
    settings: Settings,
    *,
    scan_id: str,
    tcga_data_version: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    bundle = build_hierarchical_preflight(request, db, settings)
    primary_ids = {
        row["universe_id"]
        for row in bundle.payload["universes"]
        if row["status"] == "primary"
        and row["universe_id"] in bundle.prepared
    }
    if not primary_ids:
        raise ValueError(
            "No primary study universe passed the requested "
            f"{request.min_patients}/{request.min_events}/{request.min_censored} "
            "patient/event/censored preflight. Exploratory studies are "
            "sensitivity evidence and cannot replace the primary set."
        )
    accepted_ids = {
        row["universe_id"]
        for row in bundle.payload["universes"]
        if row["status"] == "primary"
        or (
            request.include_exploratory
            and row["status"] == "exploratory"
        )
    }
    releases = [
        bundle.prepared[universe_id]
        for universe_id in sorted(accepted_ids)
        if universe_id in bundle.prepared
    ]
    if not releases:
        raise ValueError(
            "No study universe passed the requested endpoint, context, gene and "
            "minimum-information contract. Review the preflight ledger."
        )

    result_dir = hierarchical_result_path(settings, scan_id).parent
    r_payload = run_hierarchical_release_cox(
        scan_id=scan_id,
        releases=releases,
        input_path=result_dir / "hierarchical_cox_input.json",
        output_path=result_dir / "hierarchical_cox_results.json",
        min_patients=(
            min(request.min_patients, 10)
            if request.include_exploratory
            else request.min_patients
        ),
        min_events=(
            min(request.min_events, 5)
            if request.include_exploratory
            else request.min_events
        ),
        min_censored=(
            min(request.min_censored, 5)
            if request.include_exploratory
            else request.min_censored
        ),
    )
    universe_by_id = {
        row["universe_id"]: row for row in bundle.payload["universes"]
    }
    effect_rows: list[dict[str, Any]] = []
    for row in r_payload.get("results") or []:
        universe = universe_by_id.get(str(row.get("study_id") or ""), {})
        tier = str(universe.get("status") or "excluded")
        effect_rows.append(
            {
                **row,
                "universe_id": row.get("study_id"),
                "name": universe.get("name") or row.get("study_id"),
                "source_kind": universe.get("source_kind"),
                "evidence_tier": tier,
                "pooling_eligible": (
                    row.get("status") == "completed" and tier == "primary"
                ),
                "expression_scale": universe.get("expression_scale"),
                "gene_mapping": universe.get("gene_mapping"),
            }
        )

    primary_rows = [
        row for row in effect_rows if row.get("evidence_tier") == "primary"
    ]
    primary_meta = hierarchical_meta_analysis(primary_rows)
    cancer_results = _annotate_cancer_results(
        primary_meta.get("cancer_effects") or [],
        request.fdr_threshold,
    )
    global_result = {
        **(primary_meta.get("global_effect") or {}),
        "available": primary_meta.get("available", False),
        "model": primary_meta.get("model"),
        "classification": primary_meta.get("classification"),
        "formal_pan_cancer_support": primary_meta.get(
            "formal_pan_cancer_support"
        ),
        "within_cancer_replication": primary_meta.get(
            "within_cancer_replication"
        ),
        "comparability": primary_meta.get("comparability"),
        "reason": primary_meta.get("reason"),
    }

    sensitivities: dict[str, Any] = {}
    if request.include_exploratory:
        expanded_rows = [
            {
                **row,
                "pooling_eligible": row.get("status") == "completed",
            }
            for row in effect_rows
            if row.get("evidence_tier") in {"primary", "exploratory"}
        ]
        expanded = hierarchical_meta_analysis(expanded_rows)
        sensitivities["primary_plus_exploratory"] = {
            **expanded,
            "description": (
                "Sensitivity only: adds studies meeting 10 patients, 5 events "
                "and 5 censored observations; it does not replace the primary "
                "20/10/5 synthesis."
            ),
        }

    data_version = {
        "tcga": dict(tcga_data_version or {}),
        **bundle.data_version,
    }
    summary = {
        **(primary_meta.get("summary") or {}),
        "requested_universes": bundle.payload["summary"]["selected_universes"],
        "primary_eligible_studies": bundle.payload["summary"]["primary_studies"],
        "completed_primary_studies": sum(
            row.get("status") == "completed" for row in primary_rows
        ),
        "completed_cancers": len(cancer_results),
        "replicated_cancers": (
            (primary_meta.get("within_cancer_replication") or {}).get(
                "replicated_cancer_count",
                0,
            )
        ),
        "classification": primary_meta.get("classification"),
    }
    warnings = list(
        dict.fromkeys(
            bundle.payload["warnings"]
            + _analysis_warnings(primary_meta, effect_rows)
        )
    )
    result: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA,
        "scan_id": scan_id,
        "status": "completed",
        "cached": False,
        "pipeline_version": HIERARCHICAL_PANCANCER_PIPELINE_VERSION,
        "registry_version": bundle.registry_version,
        "analysis_mode": "hierarchical",
        "gene_symbol": request.resolved_gene_symbol,
        "requested_gene_symbol": request.requested_gene_symbol,
        "resolved_gene_symbol": request.resolved_gene_symbol,
        "endpoint": "OS",
        "effect_scale": {
            "id": HIERARCHICAL_EFFECT_SCALE,
            "label": HIERARCHICAL_EFFECT_SCALE_LABEL,
            "normalization_scope": "independently within each release",
        },
        "request_snapshot": {
            **request.model_dump(mode="json"),
            **request.gene_resolution,
        },
        "data_version": data_version,
        "software_versions": r_payload.get("software_versions") or {},
        "preflight": bundle.payload,
        "summary": summary,
        "study_results": effect_rows,
        "cancer_results": cancer_results,
        "global_result": global_result,
        "leave_one_out": {
            "studies": primary_meta.get("leave_one_study_out") or [],
            "cancers": primary_meta.get("leave_one_cancer_out") or [],
        },
        "sensitivities": sensitivities,
        "warnings": warnings,
        "downloads": hierarchical_downloads(scan_id),
        "audit": {},
    }
    result["audit"] = write_hierarchical_artifacts(
        settings=settings,
        scan_id=scan_id,
        result=result,
        releases=releases,
    )
    hierarchical_result_path(settings, scan_id).write_text(
        json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2),
        encoding="utf-8",
    )
    return result


def write_hierarchical_artifacts(
    *,
    settings: Settings,
    scan_id: str,
    result: dict[str, Any],
    releases: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    result_dir = hierarchical_result_path(settings, scan_id).parent
    result_dir.mkdir(parents=True, exist_ok=True)
    study_path = result_dir / "study_results.csv"
    cancer_path = result_dir / "cancer_results.csv"
    ledger_path = result_dir / "inclusion_ledger.csv"
    methodology_path = result_dir / "methodology.txt"
    request_path = result_dir / "request.json"
    preflight_path = result_dir / "preflight.json"
    audit_json_path = result_dir / "audit_report.json"
    audit_html_path = result_dir / "audit_report.html"

    _write_csv(study_path, result.get("study_results") or [])
    _write_csv(cancer_path, result.get("cancer_results") or [])
    _write_csv(
        ledger_path,
        (result.get("preflight") or {}).get("universes") or [],
    )
    request_path.write_text(
        json.dumps(
            result.get("request_snapshot") or {},
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    preflight_path.write_text(
        json.dumps(
            result.get("preflight") or {},
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    methodology_path.write_text(
        _hierarchical_methodology(result), encoding="utf-8"
    )

    patient_digest = stable_hash(
        {
            "releases": [
                {
                    "release_id": row["release_id"],
                    "records": row.get("records") or [],
                }
                for row in releases
            ]
        }
    )
    reproducibility_payload = {
        "pipeline_version": result.get("pipeline_version"),
        "registry_version": result.get("registry_version"),
        "request": result.get("request_snapshot"),
        "data_version": result.get("data_version"),
        "patient_records_sha256": patient_digest,
        "study_results": result.get("study_results"),
        "cancer_results": result.get("cancer_results"),
        "global_result": result.get("global_result"),
        "leave_one_out": result.get("leave_one_out"),
    }
    report: dict[str, Any] = {
        "schema_version": AUDIT_SCHEMA,
        "report_type": "hierarchical_pancancer_survival_audit",
        "scan_id": scan_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reproducibility_hash": stable_hash(reproducibility_payload),
        "request": result.get("request_snapshot"),
        "pipeline": {
            "version": result.get("pipeline_version"),
            "registry_version": result.get("registry_version"),
            "software_versions": result.get("software_versions"),
        },
        "data_version": result.get("data_version"),
        "analysis_design": {
            "unit_of_analysis": (
                "One release-specific Cox effect; patient-level expression "
                "matrices are never concatenated across studies."
            ),
            "estimand": HIERARCHICAL_EFFECT_SCALE_LABEL,
            "hierarchy": [
                "release-specific univariable Cox model",
                "study effects synthesized within cancer",
                "cancer effects synthesized across cancers",
            ],
            "meta_analysis": (
                "REML random effects with modified "
                "Hartung-Knapp-Sidik-Jonkman inference and 95% prediction "
                "intervals when estimable. The HKSJ scale is floored at "
                "one so inferential uncertainty cannot be smaller than the "
                "conventional random-effects uncertainty."
            ),
            "dependency_policy": (
                "At most one release per registered study cluster enters a "
                "synthesis; overlap and partition relations remain in the ledger."
            ),
            "comparability_guards": [
                "same overall-survival endpoint class",
                "same normalized time origin",
                "same clinical context",
                "same Cox model family",
                "same within-study IQR effect scale",
            ],
            "multiple_testing": (
                "Study p-values are descriptive. Benjamini-Hochberg is applied "
                "only across cancer-level effects supported by at least two "
                "independent study clusters; the global synthesis is one "
                "prespecified hypothesis."
            ),
        },
        "preflight": result.get("preflight"),
        "results": {
            "summary": result.get("summary"),
            "study_results": result.get("study_results"),
            "cancer_results": result.get("cancer_results"),
            "global_result": result.get("global_result"),
            "leave_one_out": result.get("leave_one_out"),
            "sensitivities": result.get("sensitivities"),
        },
        "quality": {
            "warnings": result.get("warnings") or [],
            "limitations": [
                "This is an observational association analysis and does not establish causality.",
                "The primary model is univariable and does not harmonize study-specific clinical covariates.",
                "A within-study IQR creates a comparable rank-spread estimand but does not harmonize assay biology.",
                "No global Kaplan-Meier curve is produced because raw study populations are not pooled.",
            ],
        },
        "patient_records": {
            "rows": sum(len(row.get("records") or []) for row in releases),
            "sha256": patient_digest,
            "public_exported": False,
            "reason": (
                "Patient-level cross-study records are retained only as a "
                "server-side compute input because source redistribution terms vary."
            ),
        },
    }
    artifact_paths = {
        "study_results": study_path,
        "cancer_results": cancer_path,
        "inclusion_ledger": ledger_path,
        "request": request_path,
        "preflight": preflight_path,
        "methodology": methodology_path,
        "raw_r_results": result_dir / "hierarchical_cox_results.json",
    }
    report["artifacts"] = {
        key: {
            "filename": path.name,
            "bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        for key, path in artifact_paths.items()
        if path.is_file()
    }
    audit_json_path.write_text(
        json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2),
        encoding="utf-8",
    )
    audit_html_path.write_text(
        _render_audit_html(report), encoding="utf-8"
    )
    receipt = write_attestation_receipt(
        settings,
        subject_type="pancancer_hierarchical_survival",
        subject_id=scan_id,
        audit_path=audit_json_path,
        reproducibility_hash=report["reproducibility_hash"],
        report_schema_version=AUDIT_SCHEMA,
    )
    return {
        "schema_version": AUDIT_SCHEMA,
        "generated_at": report["generated_at"],
        "reproducibility_hash": report["reproducibility_hash"],
        "patient_records_sha256": patient_digest,
        "server_attestation": receipt,
        "artifacts": report["artifacts"],
    }


def hierarchical_result_path(settings: Settings, scan_id: str) -> Path:
    if re.fullmatch(r"pch_[0-9a-f]{24}", scan_id) is None:
        raise ValueError("Invalid hierarchical pan-cancer scan id.")
    root = (settings.artifact_dir / "pancancer_hierarchical").resolve()
    path = (root / scan_id / "result.json").resolve()
    path.relative_to(root)
    return path


def hierarchical_downloads(scan_id: str) -> dict[str, str]:
    base = f"/api/pancancer/hierarchical-survival/{scan_id}/download"
    return {
        "studies": f"{base}/studies",
        "cancers": f"{base}/cancers",
        "ledger": f"{base}/ledger",
        "methodology": f"{base}/methodology",
        "audit_json": f"{base}/audit_json",
        "audit_html": f"{base}/audit_html",
        "attestation": f"{base}/attestation",
        "result_json": f"{base}/result_json",
        "zip": f"{base}/zip",
    }


def hierarchical_download_files() -> dict[str, tuple[str, str]]:
    return {
        "studies": ("study_results.csv", "text/csv"),
        "cancers": ("cancer_results.csv", "text/csv"),
        "ledger": ("inclusion_ledger.csv", "text/csv"),
        "methodology": ("methodology.txt", "text/plain"),
        "audit_json": ("audit_report.json", "application/json"),
        "audit_html": ("audit_report.html", "text/html"),
        "attestation": ("attestation_receipt.json", "application/json"),
        "result_json": ("result.json", "application/json"),
    }


def _load_registry(settings: Settings, active_releases: Mapping[str, Any]):
    release_ids = {
        dataset_id: str(
            metadata.get("release_id")
            if isinstance(metadata, Mapping)
            else metadata
        )
        for dataset_id, metadata in active_releases.items()
    }
    registry_root = settings.cancer_repository_registry_dir
    return load_study_universe_registry(
        registry_root / DEFAULT_STUDY_UNIVERSE_REGISTRY_FILENAME,
        manifest_dir=registry_root / "studies",
        cancer_types_path=registry_root / "cancer_types.json",
        active_release_ids=release_ids,
    )


def _selected_definitions(
    definitions: Sequence[StudyUniverseDefinition],
    request: HierarchicalPanCancerRequest,
) -> list[StudyUniverseDefinition]:
    cancer_ids = {
        str(value).strip().upper().removeprefix("TCGA-")
        for value in request.cancers
    }
    study_ids = {str(value).strip() for value in request.study_ids}
    selected = []
    for definition in definitions:
        if request.scope == "tcga_only" and definition.source_kind is not SourceKind.TCGA:
            continue
        if request.scope == "external_only" and definition.source_kind is not SourceKind.EXTERNAL:
            continue
        if cancer_ids and definition.cancer_code not in cancer_ids:
            continue
        if study_ids and definition.universe_id not in study_ids:
            continue
        selected.append(definition)
    return selected


def _synthesis_target(request: HierarchicalPanCancerRequest) -> SynthesisTarget:
    if request.clinical_context == "primary_baseline":
        return SynthesisTarget(
            endpoint_class="OS",
            clinical_context=ClinicalContext.PRIMARY_LOCAL,
            time_origin_class=TimeOriginClass.DIAGNOSIS,
        )
    if request.clinical_context == "advanced_treatment":
        return SynthesisTarget(
            endpoint_class="OS",
            clinical_context=ClinicalContext.METASTATIC,
            time_origin_class=TimeOriginClass.TREATMENT_START,
        )
    if request.clinical_context == "advanced_diagnostic":
        return SynthesisTarget(
            endpoint_class="OS",
            clinical_context=ClinicalContext.METASTATIC,
            time_origin_class=TimeOriginClass.DIAGNOSIS,
        )
    if request.clinical_context == "hematologic_treatment":
        return SynthesisTarget(
            endpoint_class="OS",
            clinical_context=ClinicalContext.HEMATOLOGIC,
            time_origin_class=TimeOriginClass.TREATMENT_START,
        )
    return SynthesisTarget(
        endpoint_class="OS",
        clinical_context=ClinicalContext.HEMATOLOGIC,
        time_origin_class=TimeOriginClass.DIAGNOSIS,
    )


def _definition_matches_target(
    definition: StudyUniverseDefinition,
    target: SynthesisTarget,
) -> bool:
    return bool(
        definition.capabilities.hierarchical_pancancer.available
        and definition.endpoint_class == target.endpoint_class
        and definition.clinical_context is target.clinical_context
        and definition.time_origin_class is target.time_origin_class
    )


def _prepare_universe(
    definition: StudyUniverseDefinition,
    gene_symbol: str,
    db: Session,
    settings: Settings,
) -> dict[str, Any]:
    if definition.source_kind is SourceKind.TCGA:
        return _prepare_tcga_universe(definition, gene_symbol, db, settings)
    return _prepare_external_universe(definition, gene_symbol, db)


def _prepare_tcga_universe(
    definition: StudyUniverseDefinition,
    gene_symbol: str,
    db: Session,
    settings: Settings,
) -> dict[str, Any]:
    cohort_id = definition.preferred_dataset_id
    if db.get(Cohort, cohort_id) is None:
        raise ValueError(f"TCGA cohort {cohort_id} is not available.")
    samples = list(
        db.scalars(select(Sample).where(Sample.cohort == cohort_id)).all()
    )
    endpoint_by_patient = _tcga_os_outcomes(db, cohort_id)
    candidates, warnings, selection = filter_sample_candidates(
        samples,
        AnalysisFilters(sample_population="primary_disease"),
        endpoint_by_patient=endpoint_by_patient or None,
        endpoint="OS",
        endpoint_label="Overall survival",
        endpoint_source=("tcga_cdr" if endpoint_by_patient else None),
    )
    expression = get_expression_for_gene(
        db,
        settings.tcga_data_dir,
        settings.derived_expression_dir,
        cohort_id,
        gene_symbol,
        "log2_tpm",
    )
    gene_mapping = gdc_expression_gene_provenance(
        settings.tcga_data_dir,
        settings.derived_expression_dir,
        cohort_id,
        gene_symbol,
    )
    retained, warnings, selection = select_expression_complete_samples(
        candidates,
        set(expression),
        warnings=warnings,
        summary=selection,
    )
    records = []
    for sample in retained:
        outcome = (
            endpoint_by_patient.get(sample.patient_id)
            if endpoint_by_patient
            else sample_os_outcome(sample)
        )
        if outcome is None or sample.barcode not in expression:
            continue
        if outcome.time_days <= 0 or outcome.event not in {0, 1}:
            continue
        records.append(
            {
                "patient_id": sample.patient_id,
                "sample_id": sample.barcode,
                "expression_value": float(expression[sample.barcode]),
                "time_days": float(outcome.time_days),
                "event": int(outcome.event),
            }
        )
    return _prepared_release(
        definition,
        release_id=definition.release_id or f"{cohort_id}:current",
        records=records,
        expression_scale={
            "source_unit": "GDC STAR-count TPM",
            "analysis_unit": "log2(TPM + 1)",
            "transform": "log2p",
        },
        gene_mapping=gene_mapping,
        sample_selection=selection,
        warnings=warnings,
        redistribution_allowed=True,
    )


def _prepare_external_universe(
    definition: StudyUniverseDefinition,
    gene_symbol: str,
    db: Session,
) -> dict[str, Any]:
    context = resolve_repository_context(
        db,
        definition.universe_id,
        definition.release_id,
    )
    require_repository_capability(context, "survival")
    endpoint_id = str(definition.endpoint_id or "").strip()
    if not endpoint_id:
        raise ValueError(
            f"Study universe {definition.universe_id!r} has no declared "
            "overall-survival endpoint identifier."
        )
    samples = repository_samples(db, context)
    outcomes, endpoint = repository_endpoint_outcomes(
        db,
        context,
        endpoint_id,
    )
    candidates, warnings, selection = filter_sample_candidates(
        samples,
        AnalysisFilters(),
        endpoint_by_patient=outcomes,
        endpoint="OS",
        endpoint_label=str(endpoint.get("label") or "Overall survival"),
        selection_rule="external",
        endpoint_source=str(endpoint.get("source") or "external"),
    )
    expression, layer, gene = repository_gene_expression(
        db, context, gene_symbol
    )
    retained, warnings, selection = select_expression_complete_samples(
        candidates,
        set(expression),
        warnings=warnings,
        summary=selection,
    )
    records = []
    for sample in retained:
        outcome = outcomes.get(sample.patient_id)
        if outcome is None or sample.barcode not in expression:
            continue
        if outcome.time_days <= 0 or outcome.event not in {0, 1}:
            continue
        records.append(
            {
                "patient_id": sample.patient_id,
                "sample_id": sample.barcode,
                "expression_value": float(expression[sample.barcode]),
                "time_days": float(outcome.time_days),
                "event": int(outcome.event),
            }
        )
    return _prepared_release(
        definition,
        release_id=context.release.id,
        records=records,
        expression_scale={
            "layer_id": layer.layer_id,
            "source_unit": layer.source_unit,
            "analysis_unit": layer.analysis_unit,
            "transform": layer.transform,
        },
        gene_mapping={
            "resolved_symbol": str(gene.gene_symbol),
            "source_gene_id": str(gene.original_gene_id),
            "source_identifier_type": "release_manifest_feature_id",
            "mapping_source": str(gene.mapping_source),
            "mapping_status": "verified",
            "row_number": int(gene.row_number),
        },
        sample_selection=selection,
        warnings=warnings,
        redistribution_allowed=bool(context.dataset.redistribution_allowed),
    )


def _prepared_release(
    definition: StudyUniverseDefinition,
    *,
    release_id: str,
    records: list[dict[str, Any]],
    expression_scale: dict[str, Any],
    gene_mapping: dict[str, Any],
    sample_selection: dict[str, Any],
    warnings: list[str],
    redistribution_allowed: bool,
) -> dict[str, Any]:
    return {
        "release_id": release_id,
        "study_id": definition.universe_id,
        "study_cluster_id": definition.study_cluster_id,
        "cancer_id": definition.cancer_code,
        "endpoint": "os",
        "time_origin": definition.time_origin_class.value,
        "clinical_context": definition.clinical_context.value,
        "model_family": "univariable_cox",
        "effect_scale": HIERARCHICAL_EFFECT_SCALE,
        "records": records,
        "expression_scale": expression_scale,
        "gene_mapping": gene_mapping,
        "sample_selection": sample_selection,
        "warnings": warnings,
        "redistribution_allowed": redistribution_allowed,
    }


def _tcga_os_outcomes(
    db: Session,
    cohort_id: str,
) -> dict[str, ClinicalOutcome]:
    rows = list(
        db.scalars(
            select(ClinicalEndpoint)
            .where(
                ClinicalEndpoint.cohort == cohort_id,
                ClinicalEndpoint.endpoint == "OS",
                ClinicalEndpoint.source_id == "tcga_cdr",
            )
            .order_by(ClinicalEndpoint.patient_id)
        ).all()
    )
    return {
        row.patient_id: ClinicalOutcome(
            endpoint="OS",
            time_days=float(row.time_days),
            event=int(row.event),
            source=row.source_id,
        )
        for row in rows
        if row.time_days is not None
        and float(row.time_days) > 0
        and row.event in {0, 1}
    }


def _nominal_observation(
    definition: StudyUniverseDefinition,
    db: Session,
) -> dict[str, Any]:
    if definition.source_kind is SourceKind.TCGA:
        samples = list(
            db.scalars(
                select(Sample).where(
                    Sample.cohort == definition.preferred_dataset_id
                )
            ).all()
        )
        if not samples:
            return _empty_nominal(definition)
        cdr = _tcga_os_outcomes(db, definition.preferred_dataset_id)
        if cdr:
            events = sum(row.event for row in cdr.values())
            return {
                "observed": True,
                "n_patients": len(cdr),
                "n_events": events,
                "n_censored": len(cdr) - events,
                "release_id": definition.release_id
                or f"{definition.preferred_dataset_id}:current",
            }
        by_patient: dict[str, Sample] = {}
        for sample in samples:
            if sample_os_outcome(sample) is not None:
                by_patient.setdefault(sample.patient_id, sample)
        events = sum(int(sample.os_event or 0) for sample in by_patient.values())
        return {
            "observed": bool(by_patient),
            "n_patients": len(by_patient),
            "n_events": events,
            "n_censored": len(by_patient) - events,
            "release_id": definition.release_id
            or f"{definition.preferred_dataset_id}:current",
        }

    try:
        context = resolve_repository_context(
            db,
            definition.universe_id,
            definition.release_id,
        )
        require_repository_capability(context, "survival")
    except ValueError:
        return _empty_nominal(definition)
    endpoint_id = str(definition.endpoint_id or "").strip()
    if not endpoint_id:
        return _empty_nominal(definition)
    endpoint = db.scalar(
        select(RepositoryEndpointDefinition).where(
            RepositoryEndpointDefinition.release_id == context.release.id,
            RepositoryEndpointDefinition.endpoint_id == endpoint_id,
            RepositoryEndpointDefinition.available.is_(True),
        )
    )
    if endpoint is None:
        return _empty_nominal(definition)
    patients = int(endpoint.patient_count or 0)
    events = int(endpoint.event_count or 0)
    return {
        "observed": True,
        "n_patients": patients,
        "n_events": events,
        "n_censored": max(0, patients - events),
        "release_id": context.release.id,
    }


def _empty_nominal(definition: StudyUniverseDefinition) -> dict[str, Any]:
    return {
        "observed": False,
        "n_patients": 0,
        "n_events": 0,
        "n_censored": 0,
        "release_id": definition.release_id,
    }


def _cancer_groups(universes: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in universes:
        grouped[str(row["cancer_code"])].append(row)
    return [
        {
            "cancer": cancer,
            "cancer_code": cancer,
            "label": cancer,
            "studies": sorted(
                rows,
                key=lambda row: (
                    not bool(row.get("analysis_eligible")),
                    str(row.get("source_kind") or ""),
                    str(row.get("name") or ""),
                ),
            ),
        }
        for cancer, rows in sorted(grouped.items())
    ]


def _annotate_cancer_results(
    rows: Sequence[dict[str, Any]],
    fdr_threshold: float,
) -> list[dict[str, Any]]:
    output = [dict(row) for row in rows]
    for row in output:
        row["inference_eligible"] = int(row.get("n_studies") or 0) >= 2
        if row.get("p_value") is None:
            random_effect = (row.get("meta_analysis") or {}).get(
                "random_effect"
            ) or {}
            row["p_value"] = random_effect.get("p_value")
        if row.get("p_value") is None:
            log_hr = _finite(row.get("log_hr"))
            standard_error = _finite(row.get("standard_error"))
            if log_hr is not None and standard_error and standard_error > 0:
                z_value = abs(log_hr / standard_error)
                row["p_value"] = math.erfc(z_value / math.sqrt(2.0))
    valid = [
        (index, float(row["p_value"]))
        for index, row in enumerate(output)
        if row["inference_eligible"]
        and _finite(row.get("p_value")) is not None
    ]
    adjusted = _benjamini_hochberg([value for _, value in valid])
    for (index, _value), fdr in zip(valid, adjusted, strict=True):
        output[index]["fdr"] = fdr
        output[index]["significant"] = fdr <= fdr_threshold
    for row in output:
        row.setdefault("fdr", None)
        row.setdefault("significant", False)
        if not row["inference_eligible"]:
            row["fdr"] = None
            row["significant"] = False
        row["level"] = "cancer"
    return output


def _benjamini_hochberg(values: Sequence[float]) -> list[float]:
    if not values:
        return []
    order = sorted(range(len(values)), key=lambda index: values[index])
    adjusted = [1.0] * len(values)
    running = 1.0
    total = len(values)
    for rank in range(total, 0, -1):
        index = order[rank - 1]
        running = min(running, values[index] * total / rank)
        adjusted[index] = min(1.0, running)
    return adjusted


def _preflight_warnings(
    summary: Mapping[str, Any],
    request: HierarchicalPanCancerRequest,
) -> list[str]:
    warnings = [
        "Expression matrices are never concatenated; only release-specific Cox effects enter the hierarchy.",
        "Study-level p-values and singleton-cancer effects are descriptive. Multiplicity control is applied only to cancers with independent within-cancer replication.",
        "A global Kaplan-Meier curve is intentionally unavailable because study populations remain separate.",
    ]
    replicated_cancers = int(summary.get("replicated_cancers") or 0)
    replicated_events = int(summary.get("replicated_events") or 0)
    if replicated_cancers < 2:
        warnings.append(
            "Fewer than two cancers have at least two independent primary study clusters; this run can produce study- and cancer-level descriptive results, but no global estimate."
        )
    if replicated_cancers < 5 or replicated_events < 100:
        warnings.append(
            "The two-stage evidence display requires at least five cancers with independent within-cancer replication and at least 100 events across those primary studies. This information threshold is not a guarantee of interval calibration."
        )
    if request.include_exploratory:
        warnings.append(
            "Exploratory 10/5/5 studies are fitted only for a labeled sensitivity analysis and never replace the primary synthesis."
        )
    return warnings


def _analysis_warnings(
    meta: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> list[str]:
    warnings = []
    failed = sum(row.get("status") != "completed" for row in rows)
    if failed:
        warnings.append(
            f"{failed} selected study effect(s) were not estimable; inspect the study ledger and result codes."
        )
    support = meta.get("formal_pan_cancer_support") or {}
    if not support.get("supported", False):
        reasons = "; ".join(str(value) for value in support.get("reasons") or [])
        warnings.append(
            "The two-stage summary does not meet the evidence threshold"
            + (f": {reasons}." if reasons else ".")
        )
    return warnings


def _reason_payload(reason: str) -> dict[str, str]:
    labels = {
        "release_not_active": "The release is not active.",
        "hierarchical_capability_unavailable": (
            "This release is catalogued but is not enabled for hierarchical OS."
        ),
        "endpoint_not_compatible_os": "Overall survival is unavailable or incompatible.",
        "universe_not_observed": "The release is not available in the active database snapshot.",
        "expression_not_available": "The requested gene is unavailable in this release.",
        "exploratory_evidence_only": "Meets exploratory 10/5/5 but not the primary information threshold.",
        "patients_below_exploratory_minimum": "Fewer than 10 analyzable patients.",
        "events_below_exploratory_minimum": "Fewer than 5 observed events.",
        "censored_below_exploratory_minimum": "Fewer than 5 censored observations.",
        "negative_preflight_count": "Invalid negative preflight count.",
        "inconsistent_event_and_censor_counts": "Events plus censored observations do not equal patients.",
    }
    code = reason.split(":", 1)[0]
    if code == "clinical_context_mismatch":
        label = f"Clinical context differs ({reason.split(':', 1)[1]})."
    elif code == "time_origin_mismatch":
        label = f"Time origin differs ({reason.split(':', 1)[1]})."
    elif code == "study_cluster_release_not_selected":
        label = (
            "A preferred independent release from the same study cluster was "
            f"selected ({reason.split(':', 1)[1]})."
        )
    else:
        label = labels.get(code, reason.replace("_", " ").capitalize())
    return {"code": code.upper(), "label": label}


def _preparation_error_code(exc: Exception) -> str:
    text = str(exc).lower()
    if "endpoint" in text or "overall survival" in text:
        return "OS_NOT_AVAILABLE"
    if "release" in text or "dataset" in text or "cohort" in text:
        return "UNIVERSE_NOT_AVAILABLE"
    return "PREPARATION_FAILED"


def _hierarchical_methodology(result: Mapping[str, Any]) -> str:
    request = result.get("request_snapshot") or {}
    return "\n".join(
        [
            "TRACE Explorer — hierarchical pan-cancer survival analysis",
            "",
            f"Scan: {result.get('scan_id')}",
            f"Pipeline: {result.get('pipeline_version')}",
            f"Study-universe registry: {result.get('registry_version')}",
            f"Gene: {result.get('gene_symbol')}",
            "Endpoint: overall survival only",
            f"Clinical context: {request.get('clinical_context')}",
            "",
            "Estimand",
            f"- {HIERARCHICAL_EFFECT_SCALE_LABEL}.",
            "- One deterministic expression-complete sample is retained per patient inside each release.",
            "- Expression matrices and patient populations are never concatenated across studies.",
            "",
            "Synthesis",
            "- A separate univariable Cox model is fitted in each eligible release with Efron ties.",
            "- Registered dependent releases are reduced to one preferred release per study cluster.",
            "- Compatible study effects are synthesized within cancer; only cancers supported by at least two independent study clusters can enter the global synthesis.",
            "- Random-effects estimation uses REML with modified HKSJ inference (variance scale max(1, q)); the unmodified scale, conventional standard error and floor application remain auditable.",
            "- Leave-one-study-out and leave-one-cancer-out analyses rerun the full hierarchy.",
            "",
            "Information thresholds",
            f"- Primary: {request.get('min_patients')} patients, {request.get('min_events')} events and {request.get('min_censored')} censored observations.",
            "- Exploratory sensitivity: 10 patients, 5 events and 5 censored observations.",
            "",
            "Interpretation",
            "- Study p-values and singleton-cancer effects are descriptive; Benjamini-Hochberg FDR is calculated only across independently replicated cancer effects.",
            "- A two-stage summary requires at least two replicated cancers; its evidence label requires at least five replicated cancers and 100 events across their primary studies.",
            "- The evidence label measures information, not nominal interval calibration, and the two-stage summary is not a universal biological effect.",
            "- No pooled Kaplan-Meier curve is produced.",
            "- Association does not establish causality or clinical utility.",
            "",
        ]
    )


def _render_audit_html(report: Mapping[str, Any]) -> str:
    encoded = html.escape(
        json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2)
    )
    title = html.escape(str(report.get("scan_id") or "Hierarchical audit"))
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{title}</title><style>body{{font:14px/1.5 monospace;max-width:1100px;margin:32px auto;padding:0 20px;color:#17313b}}"
        "pre{white-space:pre-wrap;background:#f4f8f8;border:1px solid #c7d8dc;padding:20px}</style>"
        f"</head><body><h1>{title}</h1><pre>{encoded}</pre></body></html>"
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    flattened = [_csv_row(row) for row in rows]
    fieldnames = sorted(
        {key for row in flattened for key in row},
        key=lambda key: (key not in {"universe_id", "release_id", "study_id", "cancer_id", "cancer_code", "status"}, key),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames or ["status"])
        writer.writeheader()
        writer.writerows(flattened)


def _csv_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: (
            json.dumps(value, ensure_ascii=False, sort_keys=True)
            if isinstance(value, (dict, list, tuple))
            else value
        )
        for key, value in row.items()
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None
