"""Study-universe registry and pure preflight for hierarchical pan-cancer only.

This module deliberately has no dependency on FastAPI, SQLAlchemy, or the general
survival workflow. It combines evidence definitions; it never concatenates raw
expression matrices or changes how single-cohort analyses behave.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from enum import Enum
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


__all__ = [
    "CapabilityDecision",
    "ClinicalContext",
    "DEFAULT_STUDY_UNIVERSE_REGISTRY_FILENAME",
    "DEFAULT_STUDY_UNIVERSE_REGISTRY_PATH",
    "EvidenceTier",
    "OverlapRelation",
    "PreflightDecision",
    "PreflightPolicy",
    "PreflightReport",
    "PreflightThresholds",
    "SourceKind",
    "StudyUniverseCapabilities",
    "StudyUniverseCategory",
    "StudyUniverseDefinition",
    "StudyUniverseObservation",
    "StudyUniverseRegistry",
    "SynthesisTarget",
    "TimeOriginClass",
    "classify_clinical_context",
    "classify_time_origin",
    "load_study_universe_registry",
    "preferred_release_by_cluster",
    "preflight_study_universes",
    "require_study_registry_disposition",
]


STUDY_UNIVERSE_REGISTRY_SCHEMA_V1 = (
    "tcga-trace-pancancer-study-universe-registry-v1"
)
STUDY_UNIVERSE_REGISTRY_SCHEMA_V2 = (
    "tcga-trace-pancancer-study-universe-registry-v2"
)
STUDY_UNIVERSE_REGISTRY_SCHEMA_V3 = (
    "tcga-trace-pancancer-study-universe-registry-v3"
)
STUDY_UNIVERSE_REGISTRY_SCHEMA = STUDY_UNIVERSE_REGISTRY_SCHEMA_V3
SUPPORTED_STUDY_UNIVERSE_REGISTRY_SCHEMAS = {
    STUDY_UNIVERSE_REGISTRY_SCHEMA_V1,
    STUDY_UNIVERSE_REGISTRY_SCHEMA_V2,
    STUDY_UNIVERSE_REGISTRY_SCHEMA_V3,
}
DEFAULT_STUDY_UNIVERSE_REGISTRY_FILENAME = (
    "pancancer_study_universes_v3.json"
)

_MODULE_PATH = Path(__file__).resolve()
PROJECT_ROOT = next(
    (
        candidate
        for candidate in _MODULE_PATH.parents
        if (
            candidate
            / "repository_registry"
            / DEFAULT_STUDY_UNIVERSE_REGISTRY_FILENAME
        ).is_file()
    ),
    _MODULE_PATH.parents[2],
)
DEFAULT_STUDY_UNIVERSE_REGISTRY_PATH = (
    PROJECT_ROOT
    / "repository_registry"
    / DEFAULT_STUDY_UNIVERSE_REGISTRY_FILENAME
)
DEFAULT_STUDY_MANIFEST_DIR = PROJECT_ROOT / "repository_registry" / "studies"
DEFAULT_CANCER_TYPES_PATH = (
    PROJECT_ROOT / "repository_registry" / "cancer_types.json"
)


class SourceKind(str, Enum):
    TCGA = "tcga"
    EXTERNAL = "external"


class StudyUniverseCategory(str, Enum):
    HIERARCHICAL_ACTIVE = "hierarchical_active"
    CATALOG_ONLY = "catalog_only"
    INACTIVE = "inactive"


@dataclass(frozen=True)
class CapabilityDecision:
    available: bool = True
    reason: str = "available"

    def as_dict(self) -> dict[str, Any]:
        return {"available": self.available, "reason": self.reason}


@dataclass(frozen=True)
class StudyUniverseCapabilities:
    catalog: CapabilityDecision = CapabilityDecision()
    expression_comparison: CapabilityDecision = CapabilityDecision()
    gsea: CapabilityDecision = CapabilityDecision()
    survival: CapabilityDecision = CapabilityDecision()
    hierarchical_pancancer: CapabilityDecision = CapabilityDecision()

    def as_dict(self) -> dict[str, dict[str, Any]]:
        return {
            "catalog": self.catalog.as_dict(),
            "expression_comparison": self.expression_comparison.as_dict(),
            "gsea": self.gsea.as_dict(),
            "survival": self.survival.as_dict(),
            "hierarchical_pancancer": (
                self.hierarchical_pancancer.as_dict()
            ),
        }


class ClinicalContext(str, Enum):
    PRIMARY_LOCAL = "primary_local"
    METASTATIC = "metastatic"
    RECURRENT = "recurrent"
    POST_TREATMENT_RESIDUAL = "post_treatment_residual"
    HEMATOLOGIC = "hematologic"
    UNKNOWN = "unknown"


class TimeOriginClass(str, Enum):
    DIAGNOSIS = "diagnosis"
    SURGERY = "surgery"
    TREATMENT_START = "treatment_start"
    STUDY_ENTRY = "study_entry"
    SPECIMEN_COLLECTION = "specimen_collection"
    UNKNOWN = "unknown"


class EvidenceTier(str, Enum):
    PRIMARY = "primary"
    EXPLORATORY = "exploratory"
    EXCLUDED = "excluded"


@dataclass(frozen=True)
class OverlapRelation:
    source_universe_id: str
    target_universe_id: str
    relation_type: str
    synthesis_action: str
    evidence: str
    group_id: str | None = None

    @property
    def suppresses_joint_inclusion(self) -> bool:
        return self.synthesis_action in {
            "prefer_source_release",
            "prefer_target_release",
        }


@dataclass(frozen=True)
class StudyUniverseDefinition:
    universe_id: str
    study_cluster_id: str
    source_kind: SourceKind
    cancer_code: str
    name: str
    clinical_context: ClinicalContext
    endpoint_class: str | None
    endpoint_id: str | None
    time_origin: str | None
    time_origin_class: TimeOriginClass
    preferred_release: bool
    preferred_dataset_id: str
    release_id: str | None = None
    source_accession: str | None = None
    manifest_path: str | None = None
    active: bool = True
    partition_group_ids: tuple[str, ...] = ()
    overlap_relations: tuple[OverlapRelation, ...] = ()
    registry_category: StudyUniverseCategory = (
        StudyUniverseCategory.HIERARCHICAL_ACTIVE
    )
    capabilities: StudyUniverseCapabilities = StudyUniverseCapabilities()
    registry_reasons: tuple[str, ...] = ()

    @property
    def synthesis_stratum(self) -> str:
        endpoint = self.endpoint_class or "none"
        return "|".join(
            (
                endpoint,
                self.time_origin_class.value,
                self.clinical_context.value,
            )
        )

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source_kind"] = self.source_kind.value
        payload["clinical_context"] = self.clinical_context.value
        payload["time_origin_class"] = self.time_origin_class.value
        payload["registry_category"] = self.registry_category.value
        payload["capabilities"] = self.capabilities.as_dict()
        payload["registry_reasons"] = list(self.registry_reasons)
        payload["synthesis_stratum"] = self.synthesis_stratum
        return payload


@dataclass(frozen=True)
class PreflightThresholds:
    min_patients: int
    min_events: int
    min_censored: int


@dataclass(frozen=True)
class PreflightPolicy:
    primary: PreflightThresholds = PreflightThresholds(20, 10, 5)
    exploratory: PreflightThresholds = PreflightThresholds(10, 5, 5)
    endpoint_class: str = "OS"
    require_known_clinical_context: bool = True
    require_known_time_origin: bool = True


@dataclass(frozen=True)
class SynthesisTarget:
    endpoint_class: str = "OS"
    clinical_context: ClinicalContext | None = None
    time_origin_class: TimeOriginClass | None = None


@dataclass(frozen=True)
class StudyUniverseObservation:
    universe_id: str
    n_patients: int
    n_events: int
    n_censored: int | None = None
    release_id: str | None = None
    expression_available: bool = True

    @property
    def resolved_censored(self) -> int:
        if self.n_censored is not None:
            return self.n_censored
        return self.n_patients - self.n_events


@dataclass(frozen=True)
class PreflightDecision:
    universe_id: str
    study_cluster_id: str
    cancer_code: str
    source_kind: SourceKind
    evidence_tier: EvidenceTier
    synthesis_stratum: str
    n_patients: int | None
    n_events: int | None
    n_censored: int | None
    release_id: str | None
    preferred_release: bool
    selected_for_cluster: bool
    reasons: tuple[str, ...] = ()

    @property
    def eligible(self) -> bool:
        return self.evidence_tier is not EvidenceTier.EXCLUDED

    @property
    def primary_eligible(self) -> bool:
        return self.evidence_tier is EvidenceTier.PRIMARY

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source_kind"] = self.source_kind.value
        payload["evidence_tier"] = self.evidence_tier.value
        payload["eligible"] = self.eligible
        payload["primary_eligible"] = self.primary_eligible
        return payload


@dataclass(frozen=True)
class PreflightReport:
    decisions: tuple[PreflightDecision, ...]
    target: SynthesisTarget
    policy: PreflightPolicy

    @property
    def primary(self) -> tuple[PreflightDecision, ...]:
        return tuple(
            row
            for row in self.decisions
            if row.evidence_tier is EvidenceTier.PRIMARY
        )

    @property
    def exploratory(self) -> tuple[PreflightDecision, ...]:
        return tuple(
            row
            for row in self.decisions
            if row.evidence_tier is EvidenceTier.EXPLORATORY
        )

    @property
    def excluded(self) -> tuple[PreflightDecision, ...]:
        return tuple(
            row
            for row in self.decisions
            if row.evidence_tier is EvidenceTier.EXCLUDED
        )

    def synthesis_strata(
        self, *, include_exploratory: bool = False
    ) -> dict[str, tuple[str, ...]]:
        accepted = {EvidenceTier.PRIMARY}
        if include_exploratory:
            accepted.add(EvidenceTier.EXPLORATORY)
        grouped: dict[str, list[str]] = {}
        for row in self.decisions:
            if row.evidence_tier not in accepted:
                continue
            grouped.setdefault(row.synthesis_stratum, []).append(row.universe_id)
        return {
            key: tuple(sorted(universe_ids))
            for key, universe_ids in sorted(grouped.items())
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "target": {
                "endpoint_class": self.target.endpoint_class,
                "clinical_context": (
                    self.target.clinical_context.value
                    if self.target.clinical_context
                    else None
                ),
                "time_origin_class": (
                    self.target.time_origin_class.value
                    if self.target.time_origin_class
                    else None
                ),
            },
            "policy": asdict(self.policy),
            "counts": {
                "primary": len(self.primary),
                "exploratory": len(self.exploratory),
                "excluded": len(self.excluded),
            },
            "synthesis_strata": self.synthesis_strata(),
            "decisions": [row.as_dict() for row in self.decisions],
        }


@dataclass(frozen=True)
class StudyUniverseRegistry:
    schema_version: str
    registry_version: str
    definitions: tuple[StudyUniverseDefinition, ...]
    inactive_definitions: tuple[StudyUniverseDefinition, ...]
    relations: tuple[OverlapRelation, ...]
    preflight_policy: PreflightPolicy
    source_path: str

    @property
    def by_id(self) -> dict[str, StudyUniverseDefinition]:
        return {row.universe_id: row for row in self.definitions}

    @property
    def all_by_id(self) -> dict[str, StudyUniverseDefinition]:
        return {
            row.universe_id: row
            for row in self.definitions + self.inactive_definitions
        }

    @property
    def tcga_definitions(self) -> tuple[StudyUniverseDefinition, ...]:
        return tuple(
            row for row in self.definitions if row.source_kind is SourceKind.TCGA
        )

    @property
    def external_definitions(self) -> tuple[StudyUniverseDefinition, ...]:
        return tuple(
            row
            for row in self.definitions
            if row.source_kind is SourceKind.EXTERNAL
        )

    @property
    def hierarchical_definitions(self) -> tuple[StudyUniverseDefinition, ...]:
        return tuple(
            row
            for row in self.definitions
            if row.registry_category
            is StudyUniverseCategory.HIERARCHICAL_ACTIVE
        )

    @property
    def catalog_only_definitions(self) -> tuple[StudyUniverseDefinition, ...]:
        return tuple(
            row
            for row in self.definitions
            if row.registry_category is StudyUniverseCategory.CATALOG_ONLY
        )

    def definitions_for_cancer(
        self, cancer_code: str
    ) -> tuple[StudyUniverseDefinition, ...]:
        code = cancer_code.strip().upper()
        return tuple(row for row in self.definitions if row.cancer_code == code)


def load_study_universe_registry(
    registry_path: Path | str = DEFAULT_STUDY_UNIVERSE_REGISTRY_PATH,
    *,
    manifest_dir: Path | str = DEFAULT_STUDY_MANIFEST_DIR,
    cancer_types_path: Path | str = DEFAULT_CANCER_TYPES_PATH,
    active_release_ids: Mapping[str, str] | None = None,
    validate_counts: bool = True,
) -> StudyUniverseRegistry:
    """Resolve the versioned pan-cancer universe catalog without database access.

    ``active_release_ids`` may be populated from the repository database at an API
    boundary. Keeping it optional makes registry resolution and preflight fully pure
    and deterministic in tests and offline reproduction capsules.
    """

    registry_file = Path(registry_path)
    manifest_root = Path(manifest_dir)
    cancer_file = Path(cancer_types_path)
    raw_registry = _resolve_registry_payload(registry_file, manifest_root)
    schema_version = str(raw_registry.get("schema_version") or "")
    if schema_version not in SUPPORTED_STUDY_UNIVERSE_REGISTRY_SCHEMAS:
        raise ValueError(
            "Unsupported study-universe registry schema: "
            f"{schema_version!r}."
        )
    requires_explicit_decisions = schema_version in {
        STUDY_UNIVERSE_REGISTRY_SCHEMA_V2,
        STUDY_UNIVERSE_REGISTRY_SCHEMA_V3,
    }

    release_ids = dict(active_release_ids or {})
    relations = _registry_relations(raw_registry)
    relation_index = _relation_index(relations)
    partition_index = _partition_index(raw_registry)
    cluster_index, preferred_index = _cluster_indexes(raw_registry)
    tcga_capabilities = (
        _study_universe_capabilities(
            (raw_registry.get("tcga_reference") or {}).get("capabilities"),
            require_explicit=requires_explicit_decisions,
        )
        if requires_explicit_decisions
        else StudyUniverseCapabilities()
    )

    cancer_payload = _load_json_object(cancer_file)
    tcga_rows: list[StudyUniverseDefinition] = []
    for raw in cancer_payload.get("cancer_types") or []:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("cohort_kind") or "").strip() == "external_only":
            continue
        cancer_code = str(raw.get("code") or "").strip().upper()
        cohort = str(raw.get("tcga_cohort") or "").strip()
        if not cancer_code or not cohort:
            raise ValueError("Every TCGA cancer type requires code and tcga_cohort.")
        tcga_rows.append(
            StudyUniverseDefinition(
                universe_id=cohort,
                study_cluster_id=f"tcga-{cancer_code.lower()}",
                source_kind=SourceKind.TCGA,
                cancer_code=cancer_code,
                name=str(raw.get("name") or cohort),
                clinical_context=(
                    ClinicalContext.HEMATOLOGIC
                    if cancer_code
                    in _context_set(
                        raw_registry, "hematologic_cancer_codes"
                    )
                    else ClinicalContext.PRIMARY_LOCAL
                ),
                endpoint_class="OS",
                endpoint_id="OS",
                time_origin="Diagnosis as implemented by the TCGA CDR endpoint",
                time_origin_class=TimeOriginClass.DIAGNOSIS,
                preferred_release=True,
                preferred_dataset_id=cohort,
                release_id=release_ids.get(cohort),
                source_accession=cohort,
                registry_category=(
                    StudyUniverseCategory.HIERARCHICAL_ACTIVE
                ),
                capabilities=tcga_capabilities,
            )
        )

    manifest_payloads: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in sorted(manifest_root.glob("*.json")):
        payload = _load_json_object(path)
        dataset = payload.get("dataset") or {}
        dataset_id = str(dataset.get("id") or "").strip()
        if not dataset_id:
            raise ValueError(f"Study manifest {path} has no dataset.id.")
        if dataset_id != path.stem:
            raise ValueError(
                f"Study manifest {path} declares unexpected id {dataset_id!r}."
            )
        if dataset_id in manifest_payloads:
            raise ValueError(f"Duplicate study manifest id {dataset_id!r}.")
        manifest_payloads[dataset_id] = (path, payload)

    # Historical registries remain closed over the manifests they originally
    # dispositioned. New study specs belong to a later registry and must not
    # silently change the meaning or expected counts of v1/v2.
    if schema_version == STUDY_UNIVERSE_REGISTRY_SCHEMA_V1:
        companion_v2 = registry_file.with_name(
            "pancancer_study_universes_v2.json"
        )
        if companion_v2.is_file():
            companion_ids = {
                str(row.get("dataset_id") or "").strip()
                for row in _load_json_object(companion_v2).get(
                    "universe_decisions"
                )
                or []
                if isinstance(row, Mapping)
            }
            manifest_payloads = {
                dataset_id: value
                for dataset_id, value in manifest_payloads.items()
                if dataset_id in companion_ids
            }

    universe_decisions = (
        _universe_decision_index(raw_registry)
        if requires_explicit_decisions
        else {}
    )
    if requires_explicit_decisions:
        decision_ids = set(universe_decisions)
        manifest_ids = set(manifest_payloads)
        missing_manifests = sorted(decision_ids - manifest_ids)
        undispositioned_manifests = sorted(manifest_ids - decision_ids)
        if missing_manifests or (
            schema_version == STUDY_UNIVERSE_REGISTRY_SCHEMA_V3
            and undispositioned_manifests
        ):
            details = []
            if missing_manifests:
                details.append(
                    "missing manifests: " + ", ".join(missing_manifests)
                )
            if undispositioned_manifests:
                details.append(
                    "undispositioned manifests: "
                    + ", ".join(undispositioned_manifests)
                )
            raise ValueError(
                "The study-universe registry and manifests do not match ("
                + "; ".join(details)
                + ")."
            )
        manifest_payloads = {
            dataset_id: value
            for dataset_id, value in manifest_payloads.items()
            if dataset_id in decision_ids
        }
        inactive_ids = {
            dataset_id
            for dataset_id, decision in universe_decisions.items()
            if decision["category"] is StudyUniverseCategory.INACTIVE
        }
        declared_inactive = {
            str(value)
            for value in raw_registry.get("inactive_manifest_ids") or []
        }
        if declared_inactive != inactive_ids:
            raise ValueError(
                "inactive_manifest_ids must match inactive universe decisions."
            )
    else:
        inactive_ids = {
            str(value)
            for value in raw_registry.get("inactive_manifest_ids") or []
        }
    missing_inactive = sorted(inactive_ids - set(manifest_payloads))
    if missing_inactive:
        raise ValueError(
            "Inactive study-universe manifests are missing: "
            + ", ".join(missing_inactive)
        )

    external_rows: list[StudyUniverseDefinition] = []
    inactive_rows: list[StudyUniverseDefinition] = []
    for dataset_id, (path, payload) in sorted(manifest_payloads.items()):
        dataset = payload.get("dataset") or {}
        cancer_code = str(dataset.get("cancer_code") or "").strip().upper()
        if not cancer_code:
            raise ValueError(f"Study manifest {path} has no cancer code.")
        os_endpoint = _overall_survival_endpoint(payload.get("endpoints") or [])
        time_origin = (
            str(os_endpoint.get("time_origin") or "").strip()
            if os_endpoint
            else None
        )
        cluster_id = cluster_index.get(dataset_id, f"study-{dataset_id}")
        preferred_dataset_id = preferred_index.get(dataset_id, dataset_id)
        if requires_explicit_decisions:
            registry_decision = universe_decisions[dataset_id]
            registry_category = registry_decision["category"]
            capabilities = registry_decision["capabilities"]
            registry_reasons = registry_decision["reasons"]
        else:
            registry_category = (
                StudyUniverseCategory.INACTIVE
                if dataset_id in inactive_ids
                else StudyUniverseCategory.HIERARCHICAL_ACTIVE
            )
            capabilities = (
                _inactive_capabilities("release_inactive")
                if registry_category is StudyUniverseCategory.INACTIVE
                else StudyUniverseCapabilities()
            )
            registry_reasons = (
                ("release_inactive",)
                if registry_category is StudyUniverseCategory.INACTIVE
                else ()
            )
        active = registry_category is not StudyUniverseCategory.INACTIVE
        definition = StudyUniverseDefinition(
            universe_id=dataset_id,
            study_cluster_id=cluster_id,
            source_kind=SourceKind.EXTERNAL,
            cancer_code=cancer_code,
            name=str(dataset.get("name") or dataset_id),
            clinical_context=classify_clinical_context(
                dataset_id, cancer_code, payload, raw_registry
            ),
            endpoint_class="OS" if os_endpoint else None,
            endpoint_id=(
                str(os_endpoint.get("endpoint_id") or "OS")
                if os_endpoint
                else None
            ),
            time_origin=time_origin,
            time_origin_class=classify_time_origin(time_origin),
            preferred_release=dataset_id == preferred_dataset_id,
            preferred_dataset_id=preferred_dataset_id,
            release_id=release_ids.get(dataset_id),
            source_accession=(
                str(dataset.get("source_accession") or "").strip() or None
            ),
            manifest_path=str(path),
            active=active,
            partition_group_ids=partition_index.get(dataset_id, ()),
            overlap_relations=relation_index.get(dataset_id, ()),
            registry_category=registry_category,
            capabilities=capabilities,
            registry_reasons=registry_reasons,
        )
        if active:
            external_rows.append(definition)
        else:
            inactive_rows.append(definition)

    definitions = tuple(
        sorted(tcga_rows + external_rows, key=lambda row: row.universe_id)
    )
    inactive_definitions = tuple(
        sorted(inactive_rows, key=lambda row: row.universe_id)
    )
    _validate_registry_members(
        definitions,
        inactive_definitions,
        raw_registry,
        relations,
        validate_counts=validate_counts,
    )

    return StudyUniverseRegistry(
        schema_version=schema_version,
        registry_version=str(raw_registry.get("registry_version") or ""),
        definitions=definitions,
        inactive_definitions=inactive_definitions,
        relations=relations,
        preflight_policy=_preflight_policy(raw_registry),
        source_path=str(registry_file),
    )


def require_study_registry_disposition(
    registry_root: Path | str,
    dataset_id: str,
) -> StudyUniverseDefinition:
    """Require a study spec and explicit disposition in the latest registry.

    Promotion uses this as a fail-closed integrity gate. It prevents a public
    release from becoming analysis-ready while remaining absent from the
    pan-cancer study ledger, including releases intentionally limited to
    catalog, expression or GSEA use.
    """

    root = Path(registry_root)
    resolved_id = str(dataset_id or "").strip()
    if not resolved_id or Path(resolved_id).name != resolved_id:
        raise ValueError("A safe dataset_id is required for registry disposition.")
    manifest_path = root / "studies" / f"{resolved_id}.json"
    if not manifest_path.is_file():
        raise ValueError(
            f"Study registry manifest is missing for {resolved_id!r}."
        )
    manifest = _load_json_object(manifest_path)
    manifest_id = str((manifest.get("dataset") or {}).get("id") or "").strip()
    if manifest_id != resolved_id:
        raise ValueError(
            f"Study registry manifest for {resolved_id!r} declares "
            f"{manifest_id!r}."
        )
    registry = load_study_universe_registry(
        root / DEFAULT_STUDY_UNIVERSE_REGISTRY_FILENAME,
        manifest_dir=root / "studies",
        cancer_types_path=root / "cancer_types.json",
    )
    definition = registry.all_by_id.get(resolved_id)
    if definition is None:
        raise ValueError(
            f"Latest study-universe registry has no disposition for {resolved_id!r}."
        )
    return definition


def classify_clinical_context(
    dataset_id: str,
    cancer_code: str,
    manifest: Mapping[str, Any],
    registry_payload: Mapping[str, Any],
) -> ClinicalContext:
    if cancer_code.upper() in _context_set(
        registry_payload, "hematologic_cancer_codes"
    ):
        return ClinicalContext.HEMATOLOGIC
    for key, context in (
        (
            "post_treatment_residual_dataset_ids",
            ClinicalContext.POST_TREATMENT_RESIDUAL,
        ),
        ("recurrent_dataset_ids", ClinicalContext.RECURRENT),
        ("metastatic_dataset_ids", ClinicalContext.METASTATIC),
        ("unknown_dataset_ids", ClinicalContext.UNKNOWN),
    ):
        if dataset_id in _context_set(registry_payload, key):
            return context

    samples = manifest.get("samples") or {}
    text = " ".join(
        str(value or "")
        for value in (
            samples.get("sample_role"),
            samples.get("sample_type_default"),
        )
    ).lower()
    if (
        "primary and metastatic" in text
        or "primary or metastatic" in text
        or "local or metastatic" in text
        or "primary and recurrent" in text
        or "primary or recurrent" in text
    ):
        return ClinicalContext.UNKNOWN
    if "post-treatment" in text or "residual tumor" in text:
        return ClinicalContext.POST_TREATMENT_RESIDUAL
    if "recurrent" in text and "primary" not in text:
        return ClinicalContext.RECURRENT
    if (
        "advanced or metastatic" in text
        or "metastatic disease" in text
        or "metastatic cohort" in text
    ):
        return ClinicalContext.METASTATIC
    return ClinicalContext.PRIMARY_LOCAL


def classify_time_origin(value: str | None) -> TimeOriginClass:
    text = str(value or "").strip().lower()
    if not text:
        return TimeOriginClass.UNKNOWN
    if any(
        token in text
        for token in (
            "not specified",
            "not explicitly specified",
            "not more precisely specified",
            "not restated",
            "exact day-zero definition is not specified",
            "exact calendar origin is not stated",
        )
    ):
        return TimeOriginClass.UNKNOWN
    if any(
        token in text
        for token in (
            "treatment start",
            "therapy start",
            "start of ",
            "initiation",
            "administration",
            "immune-checkpoint regimen",
        )
    ):
        return TimeOriginClass.TREATMENT_START
    if any(
        token in text
        for token in (
            "surgery",
            "surgical",
            "resection",
            "enucleation",
        )
    ):
        return TimeOriginClass.SURGERY
    if any(
        token in text
        for token in (
            "diagnosis",
            "diagnostic",
            "pathologic diagnosis",
            "age at rcc diagnosis",
        )
    ):
        return TimeOriginClass.DIAGNOSIS
    if any(
        token in text
        for token in (
            "study entry",
            "study baseline",
            "trial inclusion",
            "trial follow-up",
            "source study baseline",
        )
    ):
        return TimeOriginClass.STUDY_ENTRY
    if any(
        token in text
        for token in (
            "specimen collection",
            "tumor collection",
            "study biopsy",
            "profiled tumor",
        )
    ):
        return TimeOriginClass.SPECIMEN_COLLECTION
    return TimeOriginClass.UNKNOWN


def preflight_study_universes(
    definitions: Sequence[StudyUniverseDefinition],
    observations: Sequence[StudyUniverseObservation]
    | Mapping[str, StudyUniverseObservation],
    *,
    target: SynthesisTarget | None = None,
    policy: PreflightPolicy | None = None,
) -> PreflightReport:
    """Evaluate study-level evidence without pooling incompatible universes.

    When context or time origin are omitted from ``target``, eligible universes
    remain separated by ``synthesis_stratum``. Consequently this function never
    implies that different time origins or clinical contexts may be pooled.
    """

    resolved_target = target or SynthesisTarget()
    resolved_policy = policy or PreflightPolicy()
    observed = _observation_index(observations)
    rows: list[PreflightDecision] = []
    definitions_by_id = {row.universe_id: row for row in definitions}
    if len(definitions_by_id) != len(definitions):
        raise ValueError("Study-universe definitions contain duplicate ids.")

    unknown_observations = sorted(set(observed) - set(definitions_by_id))
    if unknown_observations:
        raise ValueError(
            "Observations reference unknown study universes: "
            + ", ".join(unknown_observations)
        )

    for definition in sorted(definitions, key=lambda row: row.universe_id):
        observation = observed.get(definition.universe_id)
        rows.append(
            _preflight_one(
                definition,
                observation,
                resolved_target,
                resolved_policy,
            )
        )

    rows = _select_cluster_releases(rows, definitions_by_id)
    return PreflightReport(
        decisions=tuple(rows),
        target=resolved_target,
        policy=resolved_policy,
    )


def preferred_release_by_cluster(
    definitions: Iterable[StudyUniverseDefinition],
) -> dict[str, str]:
    grouped: dict[str, list[StudyUniverseDefinition]] = {}
    for definition in definitions:
        grouped.setdefault(definition.study_cluster_id, []).append(definition)
    selected: dict[str, str] = {}
    for cluster_id, members in sorted(grouped.items()):
        preferred = [row for row in members if row.preferred_release]
        candidates = preferred or members
        selected[cluster_id] = sorted(
            candidates, key=lambda row: row.universe_id
        )[0].universe_id
    return selected


def _preflight_one(
    definition: StudyUniverseDefinition,
    observation: StudyUniverseObservation | None,
    target: SynthesisTarget,
    policy: PreflightPolicy,
) -> PreflightDecision:
    reasons: list[str] = []
    if not definition.active:
        reasons.append("release_not_active")
    if not definition.capabilities.hierarchical_pancancer.available:
        reasons.append(
            "hierarchical_capability_unavailable:"
            + definition.capabilities.hierarchical_pancancer.reason
        )
    if definition.endpoint_class != target.endpoint_class:
        reasons.append("endpoint_not_compatible_os")
    if (
        policy.require_known_clinical_context
        and definition.clinical_context is ClinicalContext.UNKNOWN
    ):
        reasons.append("clinical_context_not_classifiable")
    if (
        policy.require_known_time_origin
        and definition.time_origin_class is TimeOriginClass.UNKNOWN
    ):
        reasons.append("time_origin_not_classifiable")
    if (
        target.clinical_context is not None
        and definition.clinical_context is not target.clinical_context
    ):
        reasons.append(
            "clinical_context_mismatch:"
            f"{definition.clinical_context.value}"
        )
    if (
        target.time_origin_class is not None
        and definition.time_origin_class is not target.time_origin_class
    ):
        reasons.append(
            "time_origin_mismatch:"
            f"{definition.time_origin_class.value}"
        )
    if observation is None:
        # A database observation is an input requirement only for active
        # releases enabled for hierarchical synthesis. Catalog-only molecular
        # releases are intentionally not prepared for this OS workflow, so
        # their absent observation must not be presented as a missing active
        # database release.
        if (
            definition.active
            and definition.capabilities.hierarchical_pancancer.available
        ):
            reasons.append("universe_not_observed")
        return PreflightDecision(
            universe_id=definition.universe_id,
            study_cluster_id=definition.study_cluster_id,
            cancer_code=definition.cancer_code,
            source_kind=definition.source_kind,
            evidence_tier=EvidenceTier.EXCLUDED,
            synthesis_stratum=definition.synthesis_stratum,
            n_patients=None,
            n_events=None,
            n_censored=None,
            release_id=definition.release_id,
            preferred_release=definition.preferred_release,
            selected_for_cluster=False,
            reasons=tuple(reasons),
        )

    n_patients = observation.n_patients
    n_events = observation.n_events
    n_censored = observation.resolved_censored
    if not observation.expression_available:
        reasons.append("expression_not_available")
    if min(n_patients, n_events, n_censored) < 0:
        reasons.append("negative_preflight_count")
    if n_events + n_censored != n_patients:
        reasons.append("inconsistent_event_and_censor_counts")
    if reasons:
        tier = EvidenceTier.EXCLUDED
    elif _meets_thresholds(
        n_patients, n_events, n_censored, policy.primary
    ):
        tier = EvidenceTier.PRIMARY
    elif _meets_thresholds(
        n_patients, n_events, n_censored, policy.exploratory
    ):
        tier = EvidenceTier.EXPLORATORY
        reasons.append("exploratory_evidence_only")
    else:
        tier = EvidenceTier.EXCLUDED
        _append_threshold_reasons(
            reasons,
            n_patients,
            n_events,
            n_censored,
            policy.exploratory,
        )

    return PreflightDecision(
        universe_id=definition.universe_id,
        study_cluster_id=definition.study_cluster_id,
        cancer_code=definition.cancer_code,
        source_kind=definition.source_kind,
        evidence_tier=tier,
        synthesis_stratum=definition.synthesis_stratum,
        n_patients=n_patients,
        n_events=n_events,
        n_censored=n_censored,
        release_id=observation.release_id or definition.release_id,
        preferred_release=definition.preferred_release,
        selected_for_cluster=tier is not EvidenceTier.EXCLUDED,
        reasons=tuple(reasons),
    )


def _select_cluster_releases(
    decisions: list[PreflightDecision],
    definitions_by_id: Mapping[str, StudyUniverseDefinition],
) -> list[PreflightDecision]:
    index = {row.universe_id: position for position, row in enumerate(decisions)}
    grouped: dict[str, list[PreflightDecision]] = {}
    for row in decisions:
        if row.evidence_tier is EvidenceTier.EXCLUDED:
            continue
        grouped.setdefault(row.study_cluster_id, []).append(row)

    definitions_per_cluster: dict[str, int] = {}
    for definition in definitions_by_id.values():
        definitions_per_cluster[definition.study_cluster_id] = (
            definitions_per_cluster.get(definition.study_cluster_id, 0) + 1
        )

    for cluster_id, members in grouped.items():
        if len(members) < 2:
            only = members[0]
            if (
                definitions_per_cluster.get(cluster_id, 0) > 1
                and not only.preferred_release
            ):
                position = index[only.universe_id]
                decisions[position] = replace(
                    only,
                    reasons=only.reasons
                    + ("preferred_release_unavailable_fallback",),
                )
            continue
        winner = max(
            members,
            key=lambda row: (
                definitions_by_id[row.universe_id].preferred_release,
                row.evidence_tier is EvidenceTier.PRIMARY,
                row.n_events or 0,
                row.n_patients or 0,
                row.universe_id,
            ),
        )
        if not winner.preferred_release:
            winner_position = index[winner.universe_id]
            decisions[winner_position] = replace(
                winner,
                reasons=winner.reasons
                + ("preferred_release_unavailable_fallback",),
            )
        for row in members:
            if row.universe_id == winner.universe_id:
                continue
            position = index[row.universe_id]
            decisions[position] = replace(
                row,
                evidence_tier=EvidenceTier.EXCLUDED,
                selected_for_cluster=False,
                reasons=row.reasons
                + (
                    "study_cluster_release_not_selected:"
                    f"{winner.universe_id}",
                ),
            )
    return decisions


def _observation_index(
    observations: Sequence[StudyUniverseObservation]
    | Mapping[str, StudyUniverseObservation],
) -> dict[str, StudyUniverseObservation]:
    if isinstance(observations, Mapping):
        rows = dict(observations)
        mismatches = [
            key for key, row in rows.items() if key != row.universe_id
        ]
        if mismatches:
            raise ValueError(
                "Observation mapping keys must equal universe_id: "
                + ", ".join(sorted(mismatches))
            )
        return rows
    rows: dict[str, StudyUniverseObservation] = {}
    for row in observations:
        if row.universe_id in rows:
            raise ValueError(
                f"Duplicate observation for universe {row.universe_id!r}."
            )
        rows[row.universe_id] = row
    return rows


def _meets_thresholds(
    n_patients: int,
    n_events: int,
    n_censored: int,
    thresholds: PreflightThresholds,
) -> bool:
    return (
        n_patients >= thresholds.min_patients
        and n_events >= thresholds.min_events
        and n_censored >= thresholds.min_censored
    )


def _append_threshold_reasons(
    reasons: list[str],
    n_patients: int,
    n_events: int,
    n_censored: int,
    thresholds: PreflightThresholds,
) -> None:
    if n_patients < thresholds.min_patients:
        reasons.append("patients_below_exploratory_minimum")
    if n_events < thresholds.min_events:
        reasons.append("events_below_exploratory_minimum")
    if n_censored < thresholds.min_censored:
        reasons.append("censored_below_exploratory_minimum")


def _overall_survival_endpoint(
    endpoints: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    for endpoint in endpoints:
        standard = str(
            endpoint.get("standard_code") or endpoint.get("endpoint_id") or ""
        ).strip().upper()
        if standard == "OS":
            return endpoint
    return None


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return payload


def _resolve_registry_payload(
    registry_file: Path,
    manifest_root: Path,
) -> dict[str, Any]:
    """Resolve a v3 overlay while keeping the publication-frozen v2 immutable.

    A manifest addition may be marked ``required`` or
    ``when_manifest_present``. The latter supports an atomic rollout: the v3
    disposition can ship before a separately reviewed study manifest without
    making the current registry unloadable. As soon as that manifest exists,
    its explicit decision and count deltas become mandatory registry state.
    """

    overlay = _load_json_object(registry_file)
    schema_version = str(overlay.get("schema_version") or "")
    if schema_version != STUDY_UNIVERSE_REGISTRY_SCHEMA_V3:
        return overlay

    base_name = str(overlay.get("base_registry") or "").strip()
    if not base_name or Path(base_name).name != base_name:
        raise ValueError(
            "A v3 study-universe registry requires a local base_registry filename."
        )
    base_path = registry_file.parent / base_name
    base = _load_json_object(base_path)
    if base.get("schema_version") != STUDY_UNIVERSE_REGISTRY_SCHEMA_V2:
        raise ValueError("A v3 study-universe registry must extend schema v2.")

    resolved = deepcopy(base)
    for key in (
        "schema_version",
        "registry_version",
        "source_cutoff",
        "updated_at",
        "description",
    ):
        if key not in overlay:
            raise ValueError(f"A v3 study-universe registry requires {key!r}.")
        resolved[key] = overlay[key]
    resolved["base_registry"] = base_name

    decisions = resolved.get("universe_decisions")
    categories = resolved.get("universe_categories")
    expected_counts = resolved.get("expected_counts")
    if not isinstance(decisions, list):
        raise ValueError("The v2 base registry has no universe_decisions list.")
    if not isinstance(categories, dict):
        raise ValueError("The v2 base registry has no universe_categories object.")
    if not isinstance(expected_counts, dict):
        raise ValueError("The v2 base registry has no expected_counts object.")

    known_ids = {
        str(row.get("dataset_id") or "").strip()
        for row in decisions
        if isinstance(row, Mapping)
    }
    additions = overlay.get("manifest_additions") or []
    if not isinstance(additions, list):
        raise ValueError("v3 manifest_additions must be a list.")
    for raw in additions:
        if not isinstance(raw, Mapping):
            raise ValueError("Every v3 manifest addition must be an object.")
        dataset_id = str(raw.get("dataset_id") or "").strip()
        if not dataset_id or Path(dataset_id).name != dataset_id:
            raise ValueError(
                "Every v3 manifest addition requires a safe dataset_id."
            )
        activation = str(raw.get("activation") or "required").strip()
        if activation not in {"required", "when_manifest_present"}:
            raise ValueError(
                f"Unsupported v3 activation policy for {dataset_id!r}."
            )
        manifest_exists = (manifest_root / f"{dataset_id}.json").is_file()
        if activation == "required" and not manifest_exists:
            raise ValueError(
                f"Required v3 study manifest is missing: {dataset_id}."
            )
        if not manifest_exists:
            continue
        if dataset_id in known_ids:
            raise ValueError(
                f"v3 study manifest addition duplicates {dataset_id!r}."
            )
        category = str(raw.get("category") or "").strip()
        if category not in {value.value for value in StudyUniverseCategory}:
            raise ValueError(
                f"Unsupported v3 universe category for {dataset_id!r}."
            )
        reasons = [
            str(value).strip()
            for value in raw.get("reasons") or []
            if str(value).strip()
        ]
        if not reasons:
            raise ValueError(
                f"v3 study manifest addition {dataset_id!r} requires reasons."
            )
        decisions.append(
            {
                "dataset_id": dataset_id,
                "category": category,
                "capabilities": deepcopy(raw.get("capabilities")),
                "reasons": reasons,
            }
        )
        category_members = categories.get(category)
        if not isinstance(category_members, list):
            raise ValueError(
                f"The v2 base registry has no {category!r} category list."
            )
        category_members.append(dataset_id)
        if category == StudyUniverseCategory.INACTIVE.value:
            inactive = resolved.get("inactive_manifest_ids")
            if not isinstance(inactive, list):
                raise ValueError(
                    "The v2 base registry has no inactive_manifest_ids list."
                )
            inactive.append(dataset_id)
        deltas = raw.get("expected_count_deltas") or {}
        if not isinstance(deltas, Mapping):
            raise ValueError(
                f"v3 count deltas for {dataset_id!r} must be an object."
            )
        for key, delta in deltas.items():
            if key not in expected_counts:
                raise ValueError(
                    f"Unknown v3 expected-count field {str(key)!r}."
                )
            if not isinstance(delta, int) or isinstance(delta, bool):
                raise ValueError(
                    f"v3 expected-count delta {str(key)!r} must be an integer."
                )
            expected_counts[key] = int(expected_counts[key]) + delta
        known_ids.add(dataset_id)

    return resolved


def _context_set(
    registry_payload: Mapping[str, Any], key: str
) -> set[str]:
    context = registry_payload.get("clinical_context") or {}
    return {str(value) for value in context.get(key) or []}


_CAPABILITY_NAMES = (
    "catalog",
    "expression_comparison",
    "gsea",
    "survival",
    "hierarchical_pancancer",
)


def _study_universe_capabilities(
    raw: Any,
    *,
    require_explicit: bool,
) -> StudyUniverseCapabilities:
    payload = raw if isinstance(raw, Mapping) else {}
    if require_explicit:
        missing = sorted(set(_CAPABILITY_NAMES) - set(payload))
        unknown = sorted(set(payload) - set(_CAPABILITY_NAMES))
        if missing or unknown:
            details = []
            if missing:
                details.append("missing: " + ", ".join(missing))
            if unknown:
                details.append("unknown: " + ", ".join(unknown))
            raise ValueError(
                "Study-universe capabilities must be explicit ("
                + "; ".join(details)
                + ")."
            )

    resolved: dict[str, CapabilityDecision] = {}
    for name in _CAPABILITY_NAMES:
        value = payload.get(name)
        if value is None and not require_explicit:
            resolved[name] = CapabilityDecision()
            continue
        if not isinstance(value, Mapping):
            raise ValueError(
                f"Capability {name!r} must be an object with available and reason."
            )
        available = value.get("available")
        reason = str(value.get("reason") or "").strip()
        if not isinstance(available, bool) or not reason:
            raise ValueError(
                f"Capability {name!r} requires boolean available and a reason."
            )
        resolved[name] = CapabilityDecision(available, reason)
    return StudyUniverseCapabilities(**resolved)


def _inactive_capabilities(reason: str) -> StudyUniverseCapabilities:
    decision = CapabilityDecision(False, reason)
    return StudyUniverseCapabilities(
        catalog=decision,
        expression_comparison=decision,
        gsea=decision,
        survival=decision,
        hierarchical_pancancer=decision,
    )


def _universe_decision_index(
    registry_payload: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    decisions: dict[str, dict[str, Any]] = {}
    for raw in registry_payload.get("universe_decisions") or []:
        if not isinstance(raw, Mapping):
            raise ValueError("Every explicit universe decision must be an object.")
        dataset_id = str(raw.get("dataset_id") or "").strip()
        if not dataset_id or dataset_id in decisions:
            raise ValueError(
                "Every explicit universe decision requires a unique dataset_id."
            )
        try:
            category = StudyUniverseCategory(str(raw.get("category") or ""))
        except ValueError as exc:
            raise ValueError(
                f"Unsupported universe category for {dataset_id!r}."
            ) from exc
        reasons = tuple(
            str(value).strip()
            for value in raw.get("reasons") or []
            if str(value).strip()
        )
        capabilities = _study_universe_capabilities(
            raw.get("capabilities"),
            require_explicit=True,
        )
        if (
            category is StudyUniverseCategory.HIERARCHICAL_ACTIVE
            and not capabilities.hierarchical_pancancer.available
        ):
            raise ValueError(
                f"Hierarchical-active universe {dataset_id!r} must enable "
                "hierarchical_pancancer."
            )
        if (
            category is not StudyUniverseCategory.HIERARCHICAL_ACTIVE
            and capabilities.hierarchical_pancancer.available
        ):
            raise ValueError(
                f"Non-hierarchical universe {dataset_id!r} cannot enable "
                "hierarchical_pancancer."
            )
        decisions[dataset_id] = {
            "category": category,
            "capabilities": capabilities,
            "reasons": reasons,
        }

    declared_categories = registry_payload.get("universe_categories") or {}
    category_members: dict[str, set[str]] = {}
    for category in StudyUniverseCategory:
        values = [
            str(value).strip()
            for value in declared_categories.get(category.value) or []
            if str(value).strip()
        ]
        if len(values) != len(set(values)):
            raise ValueError(
                f"Universe category {category.value!r} contains duplicate ids."
            )
        category_members[category.value] = set(values)
    flattened = [
        dataset_id
        for values in category_members.values()
        for dataset_id in values
    ]
    if len(flattened) != len(set(flattened)):
        raise ValueError("A universe may belong to only one registry category.")
    decision_members = {
        category.value: {
            dataset_id
            for dataset_id, decision in decisions.items()
            if decision["category"] is category
        }
        for category in StudyUniverseCategory
    }
    if category_members != decision_members:
        raise ValueError(
            "universe_categories must exactly match universe_decisions."
        )
    return decisions


def _cluster_indexes(
    registry_payload: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    clusters: dict[str, str] = {}
    preferred: dict[str, str] = {}
    for raw in registry_payload.get("release_clusters") or []:
        cluster_id = str(raw.get("study_cluster_id") or "").strip()
        preferred_id = str(raw.get("preferred_dataset_id") or "").strip()
        members = [str(value) for value in raw.get("members") or []]
        if not cluster_id or not preferred_id or preferred_id not in members:
            raise ValueError(
                "Every release cluster requires an id and a preferred member."
            )
        for member in members:
            if member in clusters:
                raise ValueError(
                    f"Study universe {member!r} belongs to multiple release clusters."
                )
            clusters[member] = cluster_id
            preferred[member] = preferred_id
    return clusters, preferred


def _registry_relations(
    registry_payload: Mapping[str, Any],
) -> tuple[OverlapRelation, ...]:
    relations: list[OverlapRelation] = []
    for raw in registry_payload.get("overlap_relations") or []:
        relations.append(
            OverlapRelation(
                source_universe_id=str(raw.get("source_dataset_id") or ""),
                target_universe_id=str(raw.get("target_dataset_id") or ""),
                relation_type=str(raw.get("relation_type") or "unknown"),
                synthesis_action=str(
                    raw.get("synthesis_action") or "keep_separate"
                ),
                evidence=str(raw.get("evidence") or ""),
            )
        )
    for raw in registry_payload.get("partition_groups") or []:
        group_id = str(raw.get("group_id") or "").strip()
        relation_type = str(raw.get("relation_type") or "partition")
        evidence = str(raw.get("evidence") or "")
        members = sorted({str(value) for value in raw.get("members") or []})
        for index, source in enumerate(members):
            for target in members[index + 1 :]:
                relations.append(
                    OverlapRelation(
                        source_universe_id=source,
                        target_universe_id=target,
                        relation_type=relation_type,
                        synthesis_action="keep_separate",
                        evidence=evidence,
                        group_id=group_id,
                    )
                )
    return tuple(relations)


def _relation_index(
    relations: Sequence[OverlapRelation],
) -> dict[str, tuple[OverlapRelation, ...]]:
    grouped: dict[str, list[OverlapRelation]] = {}
    for relation in relations:
        grouped.setdefault(relation.source_universe_id, []).append(relation)
        grouped.setdefault(relation.target_universe_id, []).append(relation)
    return {
        key: tuple(
            sorted(
                values,
                key=lambda row: (
                    row.source_universe_id,
                    row.target_universe_id,
                    row.relation_type,
                ),
            )
        )
        for key, values in grouped.items()
    }


def _partition_index(
    registry_payload: Mapping[str, Any],
) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for raw in registry_payload.get("partition_groups") or []:
        group_id = str(raw.get("group_id") or "").strip()
        if not group_id:
            raise ValueError("Every partition group requires group_id.")
        for member in raw.get("members") or []:
            grouped.setdefault(str(member), []).append(group_id)
    return {
        key: tuple(sorted(values)) for key, values in grouped.items()
    }


def _preflight_policy(
    registry_payload: Mapping[str, Any],
) -> PreflightPolicy:
    raw = registry_payload.get("preflight_policy") or {}
    primary = raw.get("primary") or {}
    exploratory = raw.get("exploratory") or {}
    return PreflightPolicy(
        primary=PreflightThresholds(
            min_patients=int(primary.get("min_patients", 20)),
            min_events=int(primary.get("min_events", 10)),
            min_censored=int(primary.get("min_censored", 5)),
        ),
        exploratory=PreflightThresholds(
            min_patients=int(exploratory.get("min_patients", 10)),
            min_events=int(exploratory.get("min_events", 5)),
            min_censored=int(exploratory.get("min_censored", 5)),
        ),
        endpoint_class=str(raw.get("endpoint_class") or "OS"),
        require_known_clinical_context=bool(
            raw.get("require_known_clinical_context", True)
        ),
        require_known_time_origin=bool(
            raw.get("require_known_time_origin", True)
        ),
    )


def _validate_registry_members(
    definitions: Sequence[StudyUniverseDefinition],
    inactive_definitions: Sequence[StudyUniverseDefinition],
    registry_payload: Mapping[str, Any],
    relations: Sequence[OverlapRelation],
    *,
    validate_counts: bool,
) -> None:
    all_rows = tuple(definitions) + tuple(inactive_definitions)
    all_ids = {row.universe_id for row in all_rows}
    if len(all_ids) != len(all_rows):
        raise ValueError("Study-universe registry contains duplicate ids.")

    for relation in relations:
        missing = {
            relation.source_universe_id,
            relation.target_universe_id,
        } - all_ids
        if missing:
            raise ValueError(
                "Overlap relation references unknown universes: "
                + ", ".join(sorted(missing))
            )

    grouped: dict[str, list[StudyUniverseDefinition]] = {}
    for row in all_rows:
        grouped.setdefault(row.study_cluster_id, []).append(row)
    for cluster_id, members in grouped.items():
        if len(members) == 1:
            continue
        preferred = [row for row in members if row.preferred_release]
        if len(preferred) != 1:
            raise ValueError(
                f"Study cluster {cluster_id!r} requires exactly one preferred release."
            )

    for row in definitions:
        if row.registry_category is StudyUniverseCategory.INACTIVE:
            raise ValueError(
                f"Selectable universe {row.universe_id!r} cannot be inactive."
            )
        if (
            row.registry_category is StudyUniverseCategory.HIERARCHICAL_ACTIVE
            and not row.capabilities.hierarchical_pancancer.available
        ):
            raise ValueError(
                f"Hierarchical universe {row.universe_id!r} lacks its capability."
            )
    for row in inactive_definitions:
        if row.registry_category is not StudyUniverseCategory.INACTIVE:
            raise ValueError(
                f"Inactive universe {row.universe_id!r} has a non-inactive category."
            )

    if not validate_counts:
        return
    expected = registry_payload.get("expected_counts") or {}
    tcga_count = sum(
        row.source_kind is SourceKind.TCGA for row in definitions
    )
    external_count = sum(
        row.source_kind is SourceKind.EXTERNAL for row in definitions
    )
    hierarchical_external_count = sum(
        row.source_kind is SourceKind.EXTERNAL
        and row.registry_category
        is StudyUniverseCategory.HIERARCHICAL_ACTIVE
        for row in definitions
    )
    catalog_only_count = sum(
        row.registry_category is StudyUniverseCategory.CATALOG_ONLY
        for row in definitions
    )
    count_checks = {
        "tcga": tcga_count,
        "tcga_reference": tcga_count,
        "external_active": external_count,
        "external_hierarchical_active": hierarchical_external_count,
        "external_catalog_only": catalog_only_count,
        "external_inactive": len(inactive_definitions),
        "hierarchical_active_total": tcga_count
        + hierarchical_external_count,
        "total_active": len(definitions),
        "total_selectable": len(definitions),
        "total_catalogued": len(all_rows),
    }
    for key, expected_value in expected.items():
        if key not in count_checks:
            continue
        observed = count_checks[key]
        expected_count = int(expected_value)
        if observed != expected_count:
            raise ValueError(
                f"Study-universe count mismatch for {key}: "
                f"expected {expected_count}, observed {observed}."
            )
