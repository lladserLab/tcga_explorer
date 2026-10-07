from __future__ import annotations

import csv
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.hierarchical_pancancer import (
    HIERARCHICAL_EFFECT_SCALE,
    hierarchical_meta_analysis,
)
from app.hierarchical_pancancer_service import (
    PREFLIGHT_SCHEMA,
    HierarchicalPreflightBundle,
    _annotate_cancer_results,
    _prepare_external_universe,
    _synthesis_target,
    build_hierarchical_preflight,
    hierarchical_download_files,
    hierarchical_repository_version,
    hierarchical_result_path,
    run_hierarchical_pancancer_analysis,
)
from app.pancancer_study_universes import (
    ClinicalContext,
    PreflightPolicy,
    SourceKind,
    StudyUniverseDefinition,
    TimeOriginClass,
)
from app.r_runner import stable_hash
from app.schemas import (
    HierarchicalPanCancerOut,
    HierarchicalPanCancerPreflightOut,
    HierarchicalPanCancerRequest,
)


SCAN_ID = "pch_0123456789abcdef01234567"


class _RepositoryVersionRows:
    def __init__(self, rows: list[tuple[str, str, str]]) -> None:
        self._rows = rows

    def execute(self, _query):
        return SimpleNamespace(all=lambda: list(self._rows))


def _effect(
    cancer: str,
    study: str,
    log_hr: float,
    *,
    events: int = 20,
) -> dict:
    return {
        "release_id": f"{study}-release",
        "study_id": study,
        "study_cluster_id": study,
        "cancer_id": cancer,
        "endpoint": "os",
        "time_origin": "diagnosis",
        "clinical_context": "primary_local",
        "model_family": "univariable_cox",
        "effect_scale": HIERARCHICAL_EFFECT_SCALE,
        "status": "completed",
        "n_patients": 40,
        "n_events": events,
        "n_censored": 40 - events,
        "log_hr": log_hr,
        "standard_error": 0.15,
    }


def _definition(
    universe_id: str = "external-study-a",
    *,
    cancer: str = "BRCA",
    source_kind: SourceKind = SourceKind.EXTERNAL,
    manifest_path: str | None = "/internal/registry/external-study-a.json",
) -> StudyUniverseDefinition:
    return StudyUniverseDefinition(
        universe_id=universe_id,
        study_cluster_id=universe_id,
        source_kind=source_kind,
        cancer_code=cancer,
        name=f"Study {universe_id}",
        clinical_context=ClinicalContext.PRIMARY_LOCAL,
        endpoint_class="OS",
        endpoint_id="OS",
        time_origin="Diagnosis",
        time_origin_class=TimeOriginClass.DIAGNOSIS,
        preferred_release=True,
        preferred_dataset_id=universe_id,
        release_id=f"{universe_id}-release",
        manifest_path=manifest_path,
    )


def _prepared_release(definition: StudyUniverseDefinition) -> dict:
    records = [
        {
            "patient_id": f"{definition.universe_id}-patient-{index}",
            "sample_id": f"{definition.universe_id}-sample-{index}",
            "expression_value": float(index),
            "time_days": float(100 + index),
            "event": int(index % 2 == 0),
        }
        for index in range(40)
    ]
    return {
        "release_id": definition.release_id,
        "study_id": definition.universe_id,
        "study_cluster_id": definition.study_cluster_id,
        "cancer_id": definition.cancer_code,
        "endpoint": "os",
        "time_origin": "diagnosis",
        "clinical_context": "primary_local",
        "model_family": "univariable_cox",
        "effect_scale": HIERARCHICAL_EFFECT_SCALE,
        "records": records,
        "expression_scale": {
            "source_unit": "TPM",
            "analysis_unit": "log2(TPM + 1)",
            "transform": "log2p",
        },
        "gene_mapping": {
            "resolved_symbol": "TP53",
            "source_gene_id": "ENSG00000141510",
            "source_identifier_type": "release_manifest_feature_id",
            "mapping_source": "test fixture",
            "mapping_status": "verified",
            "row_number": 17,
        },
        "sample_selection": {"retained_patients": 40},
        "warnings": [],
        "redistribution_allowed": False,
    }


@pytest.mark.parametrize(
    ("clinical_context", "expected_context", "expected_origin"),
    [
        (
            "advanced_diagnostic",
            ClinicalContext.METASTATIC,
            TimeOriginClass.DIAGNOSIS,
        ),
        (
            "hematologic_treatment",
            ClinicalContext.HEMATOLOGIC,
            TimeOriginClass.TREATMENT_START,
        ),
    ],
)
def test_additional_scientific_strata_resolve_without_pooling_contexts(
    clinical_context: str,
    expected_context: ClinicalContext,
    expected_origin: TimeOriginClass,
) -> None:
    request = HierarchicalPanCancerRequest(
        gene_symbol="TP53",
        clinical_context=clinical_context,
    )

    target = _synthesis_target(request)

    assert target.clinical_context is expected_context
    assert target.time_origin_class is expected_origin


def test_external_preparation_enforces_survival_capability_and_declared_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definition = replace(_definition(), endpoint_id="SOURCE_OS")
    context = SimpleNamespace(
        release=SimpleNamespace(id="release-1"),
        dataset=SimpleNamespace(redistribution_allowed=False),
    )
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        "app.hierarchical_pancancer_service.resolve_repository_context",
        lambda _db, _dataset_id, _release_id: context,
    )

    def require_capability(source, analysis_type):
        calls["capability"] = (source, analysis_type)

    def endpoint_outcomes(_db, source, endpoint_id):
        calls["endpoint"] = (source, endpoint_id)
        return {}, {"label": "Overall survival", "source": "fixture"}

    monkeypatch.setattr(
        "app.hierarchical_pancancer_service.require_repository_capability",
        require_capability,
    )
    monkeypatch.setattr(
        "app.hierarchical_pancancer_service.repository_samples",
        lambda _db, _context: [],
    )
    monkeypatch.setattr(
        "app.hierarchical_pancancer_service.repository_endpoint_outcomes",
        endpoint_outcomes,
    )
    monkeypatch.setattr(
        "app.hierarchical_pancancer_service.filter_sample_candidates",
        lambda *args, **kwargs: ([], [], {}),
    )
    monkeypatch.setattr(
        "app.hierarchical_pancancer_service.repository_gene_expression",
        lambda _db, _context, _gene: (
            {},
            SimpleNamespace(
                layer_id="rna",
                source_unit="TPM",
                analysis_unit="log2(TPM + 1)",
                transform="log2p",
            ),
            SimpleNamespace(
                gene_symbol="TP53",
                original_gene_id="ENSG00000141510",
                mapping_source="fixture",
                row_number=0,
            ),
        ),
    )
    monkeypatch.setattr(
        "app.hierarchical_pancancer_service.select_expression_complete_samples",
        lambda *args, **kwargs: ([], [], {}),
    )

    prepared = _prepare_external_universe(definition, "TP53", object())

    assert calls["capability"] == (context, "survival")
    assert calls["endpoint"] == (context, "SOURCE_OS")
    assert prepared["release_id"] == "release-1"


def _bundle(
    definitions: list[StudyUniverseDefinition],
    *,
    tiers: list[str] | None = None,
) -> HierarchicalPreflightBundle:
    resolved_tiers = tiers or ["primary"] * len(definitions)
    prepared = {
        definition.universe_id: _prepared_release(definition)
        for definition in definitions
    }
    universes = [
        {
            "universe_id": definition.universe_id,
            "name": definition.name,
            "source_kind": definition.source_kind.value,
            "cancer_code": definition.cancer_code,
            "status": tier,
            "expression_scale": prepared[definition.universe_id][
                "expression_scale"
            ],
            "gene_mapping": prepared[definition.universe_id]["gene_mapping"],
        }
        for definition, tier in zip(definitions, resolved_tiers, strict=True)
    ]
    return HierarchicalPreflightBundle(
        payload={
            "schema_version": PREFLIGHT_SCHEMA,
            "pipeline_version": "test-pipeline",
            "registry_version": "test-registry",
            "request": {},
            "summary": {
                "selected_universes": len(universes),
                "primary_studies": sum(
                    row["status"] == "primary" for row in universes
                ),
            },
            "universes": universes,
            "cancer_groups": [],
            "warnings": [],
        },
        prepared=prepared,
        registry_version="test-registry",
        data_version={"external_releases": {}},
    )


def test_repository_version_hashes_the_complete_registry_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "pancancer_study_universes_v1.json"
    cancer_types_path = tmp_path / "cancer_types.json"
    studies_path = tmp_path / "studies"
    studies_path.mkdir()
    active_manifest = studies_path / "active.json"
    inactive_manifest = studies_path / "inactive.json"
    registry_path.write_text('{"registry":"one"}', encoding="utf-8")
    cancer_types_path.write_text('{"BRCA":"Breast"}', encoding="utf-8")
    active_manifest.write_text('{"context":"primary"}', encoding="utf-8")
    inactive_manifest.write_text('{"context":"advanced"}', encoding="utf-8")

    registry = SimpleNamespace(
        registry_version="registry-v1",
        schema_version="schema-v1",
        source_path=str(registry_path),
    )
    monkeypatch.setattr(
        "app.hierarchical_pancancer_service._load_registry",
        lambda _settings, _releases: registry,
    )
    settings = SimpleNamespace(cancer_repository_registry_dir=tmp_path)

    def identity(
        rows: list[tuple[str, str, str]] | None = None,
    ) -> dict:
        return hierarchical_repository_version(
            _RepositoryVersionRows(
                rows or [("active", "release-1", "release-manifest-1")]
            ),
            settings,
        )

    baseline = identity()
    baseline_digest = baseline["registry_bundle"]["sha256"]
    baseline_cache_hash = stable_hash(
        {"hierarchical_repository_version": baseline}
    )
    assert baseline["registry_bundle_sha256"] == baseline_digest
    assert baseline["registry_bundle"]["file_count"] == 4
    assert baseline["registry_bundle"]["study_manifests"]["count"] == 2

    mutations = (
        (registry_path, '{"registry":"two"}'),
        (cancer_types_path, '{"BRCA":"Breast cancer"}'),
        (active_manifest, '{"context":"primary_local"}'),
        (inactive_manifest, '{"context":"hematologic"}'),
    )
    for path, replacement in mutations:
        original = path.read_text(encoding="utf-8")
        path.write_text(replacement, encoding="utf-8")
        changed = identity()
        assert changed["registry_bundle"]["sha256"] != baseline_digest
        assert stable_hash(
            {"hierarchical_repository_version": changed}
        ) != baseline_cache_hash
        path.write_text(original, encoding="utf-8")

    changed_release = identity(
        [("active", "release-2", "release-manifest-2")]
    )
    assert changed_release["registry_bundle"]["sha256"] != baseline_digest


def test_preflight_is_gene_specific_and_never_exposes_absolute_manifest_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definition = _definition()
    registry = SimpleNamespace(
        definitions=(definition,),
        registry_version="registry-v1",
        preflight_policy=PreflightPolicy(),
    )
    monkeypatch.setattr(
        "app.hierarchical_pancancer_service.hierarchical_repository_version",
        lambda _db, _settings: {"external_releases": {}},
    )
    monkeypatch.setattr(
        "app.hierarchical_pancancer_service._load_registry",
        lambda _settings, _releases: registry,
    )
    monkeypatch.setattr(
        "app.hierarchical_pancancer_service._prepare_universe",
        lambda _definition, _gene, _db, _settings: _prepared_release(
            _definition
        ),
    )

    bundle = build_hierarchical_preflight(
        HierarchicalPanCancerRequest(gene_symbol=" tp53 "),
        db=object(),
        settings=object(),
    )

    assert bundle.payload["request"]["gene_symbol"] == "TP53"
    assert bundle.payload["summary"]["primary_studies"] == 1
    assert bundle.payload["summary"]["can_run"] is True
    assert bundle.payload["summary"]["primary_cancers"] == 1
    assert bundle.payload["summary"]["replicated_cancers"] == 0
    assert bundle.payload["summary"]["replicated_patients"] == 0
    assert bundle.payload["summary"]["replicated_events"] == 0
    assert bundle.payload["summary"]["preliminary_global_ready"] is False
    assert bundle.payload["summary"]["formal_global_ready"] is False
    assert any(
        "no global estimate" in warning
        for warning in bundle.payload["warnings"]
    )
    row = bundle.payload["universes"][0]
    assert row["status"] == "primary"
    assert row["manifest_path"] == (
        "repository_registry/studies/external-study-a.json"
    )
    assert not Path(row["manifest_path"]).is_absolute()


def test_alias_and_canonical_requests_select_identical_universes_with_resolved_gene(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definitions = (
        _definition("external-study-a"),
        _definition(
            "TCGA-BRCA",
            source_kind=SourceKind.TCGA,
            manifest_path="/internal/registry/tcga-brca.json",
        ),
    )
    registry = SimpleNamespace(
        definitions=definitions,
        registry_version="registry-v1",
        preflight_policy=PreflightPolicy(),
    )
    observed_genes: list[tuple[SourceKind, str]] = []

    monkeypatch.setattr(
        "app.hierarchical_pancancer_service.hierarchical_repository_version",
        lambda _db, _settings: {"external_releases": {}},
    )
    monkeypatch.setattr(
        "app.hierarchical_pancancer_service._load_registry",
        lambda _settings, _releases: registry,
    )

    def prepare(definition, gene_symbol, _db, _settings):
        observed_genes.append((definition.source_kind, gene_symbol))
        return _prepared_release(definition)

    monkeypatch.setattr(
        "app.hierarchical_pancancer_service._prepare_universe",
        prepare,
    )

    alias_bundle = build_hierarchical_preflight(
        HierarchicalPanCancerRequest(gene_symbol="p53"),
        db=object(),
        settings=object(),
    )
    canonical_bundle = build_hierarchical_preflight(
        HierarchicalPanCancerRequest(gene_symbol="TP53"),
        db=object(),
        settings=object(),
    )
    validated_alias = HierarchicalPanCancerPreflightOut(
        **alias_bundle.payload
    )

    assert observed_genes == [
        (SourceKind.EXTERNAL, "TP53"),
        (SourceKind.TCGA, "TP53"),
        (SourceKind.EXTERNAL, "TP53"),
        (SourceKind.TCGA, "TP53"),
    ]
    assert alias_bundle.payload["requested_gene_symbol"] == "P53"
    assert alias_bundle.payload["resolved_gene_symbol"] == "TP53"
    assert validated_alias.requested_gene_symbol == "P53"
    assert validated_alias.resolved_gene_symbol == "TP53"
    assert alias_bundle.payload["request"]["resolution"] == "alias"
    assert canonical_bundle.payload["request"]["resolution"] == "exact"
    assert alias_bundle.payload["universes"] == canonical_bundle.payload[
        "universes"
    ]
    assert alias_bundle.payload["summary"] == canonical_bundle.payload[
        "summary"
    ]
    assert alias_bundle.payload["cancer_groups"] == canonical_bundle.payload[
        "cancer_groups"
    ]
    assert set(alias_bundle.prepared) == set(canonical_bundle.prepared)


def test_exploratory_studies_cannot_replace_an_empty_primary_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    definition = _definition()
    monkeypatch.setattr(
        "app.hierarchical_pancancer_service.build_hierarchical_preflight",
        lambda _request, _db, _settings: _bundle(
            [definition], tiers=["exploratory"]
        ),
    )

    def unexpected_runner(**_kwargs):
        raise AssertionError("R must not run without a primary study universe")

    monkeypatch.setattr(
        "app.hierarchical_pancancer_service.run_hierarchical_release_cox",
        unexpected_runner,
    )

    with pytest.raises(ValueError, match="cannot replace the primary set"):
        run_hierarchical_pancancer_analysis(
            HierarchicalPanCancerRequest(
                gene_symbol="TP53",
                include_exploratory=True,
            ),
            db=object(),
            settings=SimpleNamespace(artifact_dir=tmp_path),
            scan_id=SCAN_ID,
        )


def test_single_study_cancers_remain_descriptive_and_do_not_enter_global() -> None:
    rows = [
        _effect("BRCA", "brca-a", 0.20),
        _effect("BRCA", "brca-b", 0.25),
        _effect("LUAD", "luad-a", 0.10),
    ]

    result = hierarchical_meta_analysis(rows)

    assert result["available"] is False
    assert result["global_effect"]["cancers"] == 1
    assert result["within_cancer_replication"] == {
        "minimum_independent_studies": 2,
        "replicated_cancers": ["BRCA"],
        "replicated_cancer_count": 1,
        "single_study_cancers": ["LUAD"],
        "single_study_effects_are_descriptive_only": True,
    }
    assert {row["cancer_id"] for row in result["cancer_effects"]} == {
        "BRCA",
        "LUAD",
    }


def test_formal_support_counts_only_replicated_cancers() -> None:
    rows = [
        _effect(cancer, f"{cancer.lower()}-only", 0.1, events=25)
        for cancer in ("BRCA", "COAD", "KIRC", "LUAD", "OV")
    ]

    result = hierarchical_meta_analysis(rows)

    assert result["available"] is False
    assert result["formal_pan_cancer_support"]["supported"] is False
    assert result["formal_pan_cancer_support"]["observed_cancers"] == 0
    assert result["formal_pan_cancer_support"]["observed_events"] == 0
    assert result["classification"] == "insufficient_support"


def test_cancer_fdr_excludes_single_study_descriptive_estimates() -> None:
    rows = [
        {
            "cancer_id": "BRCA",
            "n_studies": 2,
            "log_hr": 0.4,
            "standard_error": 0.1,
        },
        {
            "cancer_id": "LUAD",
            "n_studies": 1,
            "log_hr": 0.8,
            "standard_error": 0.1,
        },
    ]

    annotated = _annotate_cancer_results(rows, fdr_threshold=0.05)
    by_cancer = {row["cancer_id"]: row for row in annotated}

    assert by_cancer["BRCA"]["inference_eligible"] is True
    assert by_cancer["BRCA"]["fdr"] is not None
    assert by_cancer["LUAD"]["inference_eligible"] is False
    assert by_cancer["LUAD"]["fdr"] is None
    assert by_cancer["LUAD"]["significant"] is False


@pytest.mark.parametrize(
    "unsafe_scan_id",
    ["", ".", "..", "pch_short", "pch_0123456789abcdef0123456g"],
)
def test_result_path_rejects_noncanonical_or_traversal_ids(
    unsafe_scan_id: str,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="Invalid hierarchical"):
        hierarchical_result_path(
            SimpleNamespace(artifact_dir=tmp_path), unsafe_scan_id
        )


def test_analysis_writes_complete_auditable_bundle_without_patient_export(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    definitions = [
        _definition("brca-study-a", cancer="BRCA"),
        _definition("brca-study-b", cancer="BRCA"),
        _definition("luad-study-a", cancer="LUAD"),
        _definition("luad-study-b", cancer="LUAD"),
    ]
    bundle = _bundle(definitions)
    effects = [
        _effect("BRCA", "brca-study-a", 0.20),
        _effect("BRCA", "brca-study-b", 0.25),
        _effect("LUAD", "luad-study-a", 0.10),
        _effect("LUAD", "luad-study-b", 0.15),
    ]
    monkeypatch.setattr(
        "app.hierarchical_pancancer_service.build_hierarchical_preflight",
        lambda _request, _db, _settings: bundle,
    )

    def fake_cox_runner(**kwargs):
        output_path = kwargs["output_path"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "results": effects,
            "software_versions": {
                "R": "test",
                "survival": "test",
            },
        }
        output_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    monkeypatch.setattr(
        "app.hierarchical_pancancer_service.run_hierarchical_release_cox",
        fake_cox_runner,
    )

    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        artifact_dir=tmp_path / "artifacts",
        derived_expression_dir=tmp_path / "derived",
        public_base_url="https://example.test/tcga_explorer",
        attestation_private_key_path=tmp_path / "keys" / "private.pem",
        attestation_public_key_dir=tmp_path / "keys" / "public",
    )

    result = run_hierarchical_pancancer_analysis(
        HierarchicalPanCancerRequest(gene_symbol="TP53"),
        db=object(),
        settings=settings,
        scan_id=SCAN_ID,
        tcga_data_version={"manifest": "fixture"},
    )

    validated = HierarchicalPanCancerOut(**result)
    assert validated.global_result["available"] is True
    assert validated.global_result["cancers"] == 2
    assert all(
        row["gene_mapping"] == {
            "resolved_symbol": "TP53",
            "source_gene_id": "ENSG00000141510",
            "source_identifier_type": "release_manifest_feature_id",
            "mapping_source": "test fixture",
            "mapping_status": "verified",
            "row_number": 17,
        }
        for row in validated.study_results
    )
    assert validated.audit["server_attestation"]["receipt_url"] == (
        "https://example.test/tcga_explorer/api/v1/pancancer/"
        f"hierarchical-survival/{SCAN_ID}/download/attestation"
    )
    result_dir = hierarchical_result_path(settings, SCAN_ID).parent
    assert {
        filename for filename, _media_type in hierarchical_download_files().values()
    }.issubset({path.name for path in result_dir.iterdir()})

    persisted = json.loads(
        (result_dir / "result.json").read_text(encoding="utf-8")
    )
    assert persisted["schema_version"] == (
        "tcga-trace-hierarchical-pancancer-result-v1"
    )
    assert "patient_id" not in json.dumps(persisted)

    audit = json.loads(
        (result_dir / "audit_report.json").read_text(encoding="utf-8")
    )
    assert audit["patient_records"]["rows"] == 160
    assert audit["patient_records"]["public_exported"] is False
    assert len(audit["patient_records"]["sha256"]) == 64

    with (result_dir / "inclusion_ledger.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        ledger = list(csv.DictReader(handle))
    assert len(ledger) == 4
