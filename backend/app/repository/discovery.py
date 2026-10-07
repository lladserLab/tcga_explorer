from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable
import urllib.parse

from app.repository.adapters.cbioportal import CBIOPORTAL_API, request_json


CBIOPORTAL_CANCER_TO_TCGA = {
    "acc": "ACC",
    "aml": "LAML",
    "blca": "BLCA",
    "brca": "BRCA",
    "breast": "BRCA",
    "ccrcc": "KIRC",
    "cesc": "CESC",
    "chol": "CHOL",
    "coad": "COAD",
    "coadread": "COAD",
    "crc": "COAD",
    "difg": "LGG",
    "dlbc": "DLBC",
    "esca": "ESCA",
    "gbm": "GBM",
    "hnsc": "HNSC",
    "hcc": "LIHC",
    "hgsoc": "OV",
    "kich": "KICH",
    "kirc": "KIRC",
    "kirp": "KIRP",
    "laml": "LAML",
    "lgg": "LGG",
    "lihc": "LIHC",
    "luad": "LUAD",
    "lusc": "LUSC",
    "mel": "SKCM",
    "meso": "MESO",
    "ov": "OV",
    "ovary": "OV",
    "ohnca": "HNSC",
    "paad": "PAAD",
    "pancreas": "PAAD",
    "pcpg": "PCPG",
    "prad": "PRAD",
    "read": "READ",
    "sarc": "SARC",
    "skcm": "SKCM",
    "stad": "STAD",
    "tgct": "TGCT",
    "thca": "THCA",
    "thym": "THYM",
    "ucec": "UCEC",
    "uec": "UCEC",
    "ucs": "UCS",
    "uvm": "UVM",
}

CBIOPORTAL_STUDY_PREFIX_TO_TCGA = {
    **CBIOPORTAL_CANCER_TO_TCGA,
    "angs": "SARC",
    "chrcc": "KICH",
    "gbm": "GBM",
    "mel": "SKCM",
    "mpm": "MESO",
    "nsgct": "TGCT",
    "plmeso": "MESO",
    "prcc": "KIRP",
    "rectal": "READ",
    "thpa": "THCA",
    "um": "UVM",
}

CBIOPORTAL_STUDY_TO_TCGA = {
    # This public study retains a legacy HNSC identifier in cBioPortal, but
    # contains hereditary SDHB-mutant pheochromocytomas/paragangliomas.
    "hnsc_a5consortium_2025": "PCPG",
}

ENDPOINT_COLUMN_PAIRS = {
    "OS": [
        ("OS_STATUS", "OS_MONTHS"),
        ("OS_STATUS", "OS_DAYS"),
    ],
    "DSS": [
        ("DSS_STATUS", "DSS_MONTHS"),
        ("DSS_STATUS", "DSS_DAYS"),
    ],
    "PFS": [
        ("PFS_STATUS", "PFS_MONTHS"),
        ("PFS_STATUS", "PFS_DAYS"),
    ],
    "PFI": [
        ("PFI_STATUS", "PFI_MONTHS"),
        ("PFI_STATUS", "PFI_DAYS"),
    ],
    "DFS": [
        ("DFS_STATUS", "DFS_MONTHS"),
        ("DFS_STATUS", "DFS_DAYS"),
    ],
    "DFI": [
        ("DFI_STATUS", "DFI_MONTHS"),
        ("DFI_STATUS", "DFI_DAYS"),
    ],
}

DISALLOWED_STUDY_TOKENS = (
    "_tcga",
    "tcga_",
    "_target",
    "target_",
    "pcawg",
    "cellline",
    "cell_line",
)


def discover_cbioportal_candidates(
    registry_dir: Path,
    *,
    requester: Callable[..., Any] = request_json,
) -> dict[str, Any]:
    cancer_types = _registry_cancer_types(registry_dir)
    registered = _registered_accessions(registry_dir)
    coverage = _coverage_by_code(registry_dir)
    studies = requester(
        _api_url("/studies", projection="DETAILED", pageSize=10_000_000)
    )
    profiles = requester(
        _api_url(
            "/molecular-profiles",
            projection="DETAILED",
            pageSize=10_000_000,
        )
    )
    profiles_by_study: dict[str, list[dict[str, Any]]] = {}
    for profile in profiles:
        if _is_bulk_rna_profile(profile):
            profiles_by_study.setdefault(
                str(profile.get("studyId") or ""), []
            ).append(profile)

    candidates_by_cancer: dict[str, list[dict[str, Any]]] = {
        code: [] for code in cancer_types
    }
    rejections_by_cancer: dict[str, list[dict[str, Any]]] = {
        code: [] for code in cancer_types
    }
    screened_studies = 0
    endpoint_queries = 0
    sample_list_queries = 0
    mapped_studies = 0
    unmapped_studies = 0
    for study in studies:
        study_id = str(study.get("studyId") or "")
        study_prefix = study_id.lower().split("_", 1)[0]
        cancer_code = (
            CBIOPORTAL_STUDY_TO_TCGA.get(study_id.lower())
            or CBIOPORTAL_STUDY_PREFIX_TO_TCGA.get(study_prefix)
            or CBIOPORTAL_CANCER_TO_TCGA.get(
                str(study.get("cancerTypeId") or "").lower()
            )
        )
        if cancer_code not in candidates_by_cancer:
            unmapped_studies += 1
            continue
        mapped_studies += 1
        if _is_disallowed_study(study):
            rejections_by_cancer[cancer_code].append(
                _rejection_record(study, "disallowed_accession")
            )
            continue
        study_profiles = profiles_by_study.get(study_id) or []
        if not study_profiles:
            rejections_by_cancer[cancer_code].append(
                _rejection_record(study, "no_eligible_bulk_rna_profile")
            )
            continue
        rna_samples = int(study.get("mrnaRnaSeqSampleCount") or 0)
        rna_sample_count_source = "study.mrnaRnaSeqSampleCount"
        if rna_samples < 10:
            sample_lists = requester(
                f"{CBIOPORTAL_API}/studies/"
                f"{urllib.parse.quote(study_id, safe='')}/sample-lists"
                "?projection=DETAILED"
            )
            sample_list_queries += 1
            listed_rna_samples = _rna_seq_sample_count(sample_lists)
            if listed_rna_samples > rna_samples:
                rna_samples = listed_rna_samples
                rna_sample_count_source = (
                    "study sample list: "
                    "all_cases_with_mrna_rnaseq_data"
                )
        if rna_samples < 10:
            rejections_by_cancer[cancer_code].append(
                _rejection_record(
                    study,
                    "fewer_than_10_rna_samples",
                    rna_seq_sample_count=rna_samples,
                    rna_sample_count_source=rna_sample_count_source,
                )
            )
            continue
        screened_studies += 1
        attributes = requester(
            f"{CBIOPORTAL_API}/studies/"
            f"{urllib.parse.quote(study_id, safe='')}/clinical-attributes"
        )
        endpoint_queries += 1
        endpoint_pairs = _available_endpoint_pairs(attributes)
        if not endpoint_pairs:
            rejections_by_cancer[cancer_code].append(
                _rejection_record(
                    study,
                    "no_recognized_survival_endpoint_pair",
                    rna_seq_sample_count=rna_samples,
                )
            )
            continue
        registry_entry = registered.get(study_id)
        coverage_candidates = {
            str(row.get("accession")): row
            for row in (coverage.get(cancer_code) or {}).get(
                "candidates", []
            )
        }
        reviewed_entry = coverage_candidates.get(study_id)
        candidates_by_cancer[cancer_code].append(
            {
                "study_id": study_id,
                "study_name": study.get("name"),
                "cancer_type_id": study.get("cancerTypeId"),
                "sample_count": int(study.get("allSampleCount") or 0),
                "rna_seq_sample_count": rna_samples,
                "rna_sample_count_source": rna_sample_count_source,
                "reference_genome": study.get("referenceGenome"),
                "pmid": study.get("pmid"),
                "citation": study.get("citation"),
                "import_date": study.get("importDate"),
                "rna_profiles": [
                    {
                        "id": profile.get("molecularProfileId"),
                        "name": profile.get("name"),
                        "description": profile.get("description"),
                        "datatype": profile.get("datatype"),
                    }
                    for profile in sorted(
                        study_profiles,
                        key=lambda row: str(
                            row.get("molecularProfileId") or ""
                        ),
                    )
                ],
                "endpoint_pairs": endpoint_pairs,
                "independence_screen": "not_tcga_by_accession_or_description",
                "license_review": (
                    "passed"
                    if reviewed_entry
                    and reviewed_entry.get("review_status") == "promoted"
                    else "required"
                ),
                "review_status": (
                    "promoted"
                    if reviewed_entry
                    and reviewed_entry.get("review_status") == "promoted"
                    else "registered_spec"
                    if registry_entry
                    else "screening_candidate"
                ),
                "dataset_id": (
                    registry_entry.get("dataset_id")
                    if registry_entry
                    else None
                ),
                "source_url": (
                    "https://www.cbioportal.org/study/summary?id="
                    + urllib.parse.quote(study_id, safe="")
                ),
            }
        )

    cancers = []
    for code, metadata in cancer_types.items():
        candidates = sorted(
            candidates_by_cancer[code],
            key=lambda row: (
                row["review_status"] != "promoted",
                -int(row["rna_seq_sample_count"]),
                row["study_id"],
            ),
        )
        rejections = sorted(
            rejections_by_cancer[code],
            key=lambda row: (row["reason"], row["study_id"]),
        )
        rejection_reasons: dict[str, int] = {}
        for rejection in rejections:
            reason = str(rejection["reason"])
            rejection_reasons[reason] = (
                rejection_reasons.get(reason, 0) + 1
            )
        cancers.append(
            {
                "code": code,
                "tcga_cohort": metadata["tcga_cohort"],
                "name": metadata["name"],
                "coverage_status": (
                    coverage.get(code) or {}
                ).get("status", "unsearched"),
                "candidate_count": len(candidates),
                "candidates": candidates,
                "rejection_count": len(rejections),
                "rejection_reasons": rejection_reasons,
                "rejections": rejections,
            }
        )
    rejection_reason_counts: dict[str, int] = {}
    for rows in rejections_by_cancer.values():
        for rejection in rows:
            reason = str(rejection["reason"])
            rejection_reason_counts[reason] = (
                rejection_reason_counts.get(reason, 0) + 1
            )
    return {
        "schema_version": "tcga-trace-cbioportal-discovery-v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "provider": "cBioPortal public API",
            "base_url": CBIOPORTAL_API,
            "study_count": len(studies),
            "molecular_profile_count": len(profiles),
            "mapped_studies": mapped_studies,
            "unmapped_studies": unmapped_studies,
            "screened_rna_studies": screened_studies,
            "sample_list_queries": sample_list_queries,
            "clinical_attribute_queries": endpoint_queries,
        },
        "screening_policy": {
            "minimum_rna_seq_samples": 10,
            "requires_recognized_survival_time_and_status_columns": True,
            "excludes_tcga_target_pcawg_and_cell_line_accessions": True,
            "candidate_is_not_published_dataset": True,
            "manual_checks_still_required": [
                "patient-level endpoint completeness and event count",
                "bulk RNA-seq matrix semantics and transform",
                "gene identifier mapping",
                "TCGA independence",
                "license and redistribution terms",
                "sample-to-patient linkage",
            ],
        },
        "summary": {
            "tcga_cancer_types": len(cancers),
            "cancer_types_with_candidates": sum(
                bool(row["candidate_count"]) for row in cancers
            ),
            "candidate_studies": sum(
                int(row["candidate_count"]) for row in cancers
            ),
            "promoted_studies": sum(
                candidate["review_status"] == "promoted"
                for row in cancers
                for candidate in row["candidates"]
            ),
            "rejected_mapped_studies": sum(
                int(row["rejection_count"]) for row in cancers
            ),
            "rejection_reason_counts": rejection_reason_counts,
        },
        "cancers": cancers,
    }


def _api_url(path: str, **query: Any) -> str:
    return f"{CBIOPORTAL_API}{path}?{urllib.parse.urlencode(query)}"


def _rejection_record(
    study: dict[str, Any],
    reason: str,
    *,
    rna_seq_sample_count: int | None = None,
    rna_sample_count_source: str | None = None,
) -> dict[str, Any]:
    record = {
        "study_id": str(study.get("studyId") or ""),
        "study_name": study.get("name"),
        "cancer_type_id": study.get("cancerTypeId"),
        "reason": reason,
        "sample_count": int(study.get("allSampleCount") or 0),
    }
    if rna_seq_sample_count is not None:
        record["rna_seq_sample_count"] = rna_seq_sample_count
    if rna_sample_count_source is not None:
        record["rna_sample_count_source"] = rna_sample_count_source
    return record


def _rna_seq_sample_count(sample_lists: list[dict[str, Any]]) -> int:
    sample_ids: set[str] = set()
    for sample_list in sample_lists:
        if (
            str(sample_list.get("category") or "")
            != "all_cases_with_mrna_rnaseq_data"
        ):
            continue
        sample_ids.update(
            str(sample_id)
            for sample_id in sample_list.get("sampleIds") or []
            if str(sample_id)
        )
    return len(sample_ids)


def _is_bulk_rna_profile(profile: dict[str, Any]) -> bool:
    if profile.get("molecularAlterationType") != "MRNA_EXPRESSION":
        return False
    if profile.get("datatype") != "CONTINUOUS":
        return False
    searchable = " ".join(
        str(profile.get(field) or "").lower()
        for field in (
            "molecularProfileId",
            "name",
            "description",
        )
    )
    if (
        "z-score" in searchable
        or "zscore" in searchable
        or "mirna" in searchable
        or "micro rna" in searchable
    ):
        return False
    return any(
        token in searchable
        for token in (
            "rna_seq",
            "rna seq",
            "rpkm",
            "fpkm",
            "tpm",
            "rsem",
        )
    )


def _is_disallowed_study(study: dict[str, Any]) -> bool:
    searchable = " ".join(
        str(study.get(field) or "").lower()
        for field in ("studyId", "name", "description")
    )
    return any(token in searchable for token in DISALLOWED_STUDY_TOKENS)


def _available_endpoint_pairs(
    attributes: list[dict[str, Any]],
) -> list[dict[str, str]]:
    available = {
        str(row.get("clinicalAttributeId") or "").upper()
        for row in attributes
        if row.get("patientAttribute")
    }
    pairs: list[dict[str, str]] = []
    for endpoint, candidates in ENDPOINT_COLUMN_PAIRS.items():
        for status_column, time_column in candidates:
            if status_column in available and time_column in available:
                pairs.append(
                    {
                        "endpoint": endpoint,
                        "status_column": status_column,
                        "time_column": time_column,
                    }
                )
                break
    return pairs


def _registry_cancer_types(
    registry_dir: Path,
) -> dict[str, dict[str, Any]]:
    payload = json.loads(
        (registry_dir / "cancer_types.json").read_text(encoding="utf-8")
    )
    return {
        str(row["code"]): row
        for row in payload.get("cancer_types") or []
    }


def _registered_accessions(
    registry_dir: Path,
) -> dict[str, dict[str, Any]]:
    registered: dict[str, dict[str, Any]] = {}
    for path in sorted((registry_dir / "studies").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        dataset = payload.get("dataset") or {}
        accession = str(dataset.get("source_accession") or "")
        if accession:
            registered[accession] = {
                "dataset_id": dataset.get("id"),
                "spec_path": str(path.relative_to(registry_dir)),
            }
    return registered


def _coverage_by_code(
    registry_dir: Path,
) -> dict[str, dict[str, Any]]:
    payload = json.loads(
        (registry_dir / "coverage.json").read_text(encoding="utf-8")
    )
    return {
        str(row["code"]): row for row in payload.get("cancers") or []
    }
