from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from app.pancancer_study_universes import (
    ClinicalContext,
    EvidenceTier,
    SourceKind,
    StudyUniverseDefinition,
    StudyUniverseObservation,
    StudyUniverseCategory,
    SynthesisTarget,
    TimeOriginClass,
    classify_time_origin,
    load_study_universe_registry,
    preflight_study_universes,
    preferred_release_by_cluster,
    require_study_registry_disposition,
)


def test_registry_resolves_all_active_study_universes() -> None:
    registry = load_study_universe_registry()
    smc_present = (
        Path(registry.source_path).parent
        / "studies"
        / "cbioportal-brca-smc-2018.json"
    ).is_file()
    molecular_addition = int(smc_present)

    assert registry.schema_version == (
        "tcga-trace-pancancer-study-universe-registry-v3"
    )
    assert registry.registry_version == "2026.08.20.v3"
    assert len(registry.definitions) == 178 + molecular_addition
    assert len(registry.tcga_definitions) == 33
    assert len(registry.external_definitions) == 145 + molecular_addition
    assert len(registry.hierarchical_definitions) == 91
    assert len(registry.catalog_only_definitions) == 87 + molecular_addition
    assert len(registry.inactive_definitions) == 4
    gbc = registry.by_id["fu-gbc-cancer-cell-2026"]
    assert gbc.registry_category is StudyUniverseCategory.CATALOG_ONLY
    assert gbc.capabilities.survival.available is True
    assert gbc.capabilities.hierarchical_pancancer.available is False
    assert gbc.time_origin_class is TimeOriginClass.UNKNOWN
    assert set(registry.by_id) == {
        row.universe_id for row in registry.definitions
    }


def test_v1_registry_remains_loadable_without_changing_its_frozen_file() -> None:
    default_registry = load_study_universe_registry()
    root = Path(default_registry.source_path).parent
    registry = load_study_universe_registry(
        root / "pancancer_study_universes_v1.json",
        manifest_dir=root / "studies",
        cancer_types_path=root / "cancer_types.json",
    )

    assert registry.schema_version == (
        "tcga-trace-pancancer-study-universe-registry-v1"
    )
    assert registry.registry_version == "2026.08.20"
    assert len(registry.definitions) == 177
    assert len(registry.tcga_definitions) == 33
    assert len(registry.external_definitions) == 144
    assert len(registry.inactive_definitions) == 4


def test_v2_categories_and_capabilities_are_exhaustive_and_explicit() -> None:
    default_registry = load_study_universe_registry()
    root = Path(default_registry.source_path).parent
    registry = load_study_universe_registry(
        root / "pancancer_study_universes_v2.json",
        manifest_dir=root / "studies",
        cancer_types_path=root / "cancer_types.json",
    )
    all_rows = registry.definitions + registry.inactive_definitions

    assert registry.schema_version == (
        "tcga-trace-pancancer-study-universe-registry-v2"
    )
    assert registry.registry_version == "2026.08.20.v2"
    assert len(registry.definitions) == 177
    assert len(registry.tcga_definitions) == 33
    assert all(
        row.registry_category is StudyUniverseCategory.HIERARCHICAL_ACTIVE
        and row.capabilities.hierarchical_pancancer.available
        for row in registry.tcga_definitions
    )
    assert {
        row.registry_category for row in registry.catalog_only_definitions
    } == {StudyUniverseCategory.CATALOG_ONLY}
    assert all(
        not row.capabilities.hierarchical_pancancer.available
        and row.capabilities.hierarchical_pancancer.reason != ""
        for row in registry.catalog_only_definitions
    )
    assert all(
        row.registry_category is StudyUniverseCategory.INACTIVE
        and not row.capabilities.catalog.available
        for row in registry.inactive_definitions
    )
    assert len({row.universe_id for row in all_rows}) == len(all_rows)


def test_v3_preserves_every_resolved_v2_definition() -> None:
    v3 = load_study_universe_registry()
    root = Path(v3.source_path).parent
    v2 = load_study_universe_registry(
        root / "pancancer_study_universes_v2.json",
        manifest_dir=root / "studies",
        cancer_types_path=root / "cancer_types.json",
    )

    assert {
        dataset_id: v3.all_by_id[dataset_id].as_dict()
        for dataset_id in v2.all_by_id
    } == {
        dataset_id: definition.as_dict()
        for dataset_id, definition in v2.all_by_id.items()
    }
    assert v3.relations == v2.relations
    assert v3.preflight_policy == v2.preflight_policy


def test_candidate_registry_dispositions_every_sweep_candidate() -> None:
    registry = load_study_universe_registry()
    path = Path(registry.source_path).parent / "dataset_candidates_v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates = payload["candidates"]
    ids = [row["id"] for row in candidates]

    assert payload["schema_version"] == (
        "tcga-trace-dataset-candidate-registry-v1"
    )
    assert payload["source_cutoff"] == "2026-08-20"
    assert payload["inventory_coverage"]["complete"] is True
    assert len(candidates) == 182
    assert len(ids) == len(set(ids))
    assert payload["counts"]["candidates"] == len(candidates)
    assert payload["counts"]["explicitly_dispositioned"] == len(candidates)
    assert payload["counts"]["analysis_ready"] == 1
    assert payload["counts"]["by_tier"] == {
        tier: sum(row["tier"] == tier for row in candidates)
        for tier in ("S1", "S2", "E1", "E2", "C", "Q", "X")
    }
    assert payload["counts"]["by_status"] == {
        status: sum(row["status"] == status for row in candidates)
        for status in payload["counts"]["by_status"]
    }
    assert {row["status"] for row in candidates} <= {
        "promoted",
        "under_review",
        "access_required",
        "not_eligible",
    }
    candidate_id_digest = hashlib.sha256(
        "\n".join(sorted(ids)).encode("utf-8")
    ).hexdigest()
    assert candidate_id_digest == payload["inventory_coverage"][
        "candidate_id_set_sha256"
    ]

    required_capabilities = {
        "catalog",
        "expression_comparison",
        "gsea",
        "survival",
        "hierarchical_pancancer",
    }
    for row in candidates:
        assert set(row) >= {
            "id",
            "disease",
            "source",
            "tier",
            "status",
            "access_class",
            "capabilities",
            "decisions",
            "blockers",
            "links",
        }
        assert set(row["capabilities"]) == required_capabilities
        if row["id"] == "cbioportal-brca-smc-2018":
            assert row["status"] == "promoted"
            assert row["blockers"] == []
            assert row["decisions"]["promotion_state"] == "promoted"
            assert row["capabilities"]["expression_comparison"]["available"]
            assert row["capabilities"]["gsea"]["available"]
            assert not row["capabilities"]["survival"]["available"]
            assert not row["capabilities"]["hierarchical_pancancer"][
                "available"
            ]
        else:
            assert row["blockers"]
            assert row["decisions"]["promotion_state"] == "not_promoted"
            assert all(
                capability["available"] is False
                for name, capability in row["capabilities"].items()
                if name != "catalog"
            )

    by_id = {row["id"]: row for row in candidates}
    assert by_id["gdc-target-aml"]["tier"] == "S1"
    assert by_id["geo-gse227832-all"]["tier"] == "E1"
    assert by_id["ega-checkmate-214"]["access_class"] == "controlled"
    assert by_id["gdc-beataml10-cohort"]["status"] == "not_eligible"
    assert by_id["openpedcan-pooled"]["status"] == "under_review"


def test_every_external_manifest_is_active_or_catalogued_inactive() -> None:
    registry = load_study_universe_registry()
    manifest_dir = Path(registry.source_path).parent / "studies"
    manifest_ids = {path.stem for path in manifest_dir.glob("*.json")}
    catalogued = {
        row.universe_id for row in registry.external_definitions
    } | {row.universe_id for row in registry.inactive_definitions}

    assert catalogued == manifest_ids
    assert {
        row.universe_id for row in registry.inactive_definitions
    } == {
        "biostudies-brca-nottingham-icart1-2-2020",
        "biostudies-brca-nottingham-icart1-2024",
        "cbioportal-brca-iatlas-anders-2022",
        "cbioportal-gbm-iatlas-prins-2019",
    }


def _copy_registry_for_transition_test(tmp_path: Path) -> Path:
    source_root = Path(load_study_universe_registry().source_path).parent
    target_root = tmp_path / "repository_registry"
    target_root.mkdir()
    for name in (
        "cancer_types.json",
        "pancancer_study_universes_v2.json",
        "pancancer_study_universes_v3.json",
    ):
        shutil.copy2(source_root / name, target_root / name)
    shutil.copytree(source_root / "studies", target_root / "studies")
    return target_root


def test_v3_activates_smc_as_molecular_only_and_never_hierarchical(
    tmp_path: Path,
) -> None:
    root = _copy_registry_for_transition_test(tmp_path)
    smc_path = root / "studies" / "cbioportal-brca-smc-2018.json"
    smc_path.write_text(
        json.dumps(
            {
                "schema_version": "tcga-trace-study-spec-v2",
                "dataset": {
                    "id": "cbioportal-brca-smc-2018",
                    "cancer_code": "BRCA",
                    "name": "SMC breast cancer cohort (2018)",
                },
                "samples": {
                    "sample_type_default": "Primary breast tumor",
                    "sample_role": "Primary breast tumor",
                },
                "endpoints": [],
            }
        ),
        encoding="utf-8",
    )

    registry = load_study_universe_registry(
        root / "pancancer_study_universes_v3.json",
        manifest_dir=root / "studies",
        cancer_types_path=root / "cancer_types.json",
    )
    smc = registry.by_id["cbioportal-brca-smc-2018"]

    assert smc.registry_category is StudyUniverseCategory.CATALOG_ONLY
    assert smc.capabilities.catalog.available is True
    assert smc.capabilities.expression_comparison.available is True
    assert smc.capabilities.gsea.available is True
    assert smc.capabilities.survival.available is False
    assert smc.capabilities.hierarchical_pancancer.available is False
    assert smc.endpoint_class is None
    assert smc not in registry.hierarchical_definitions

    report = preflight_study_universes(
        (smc,),
        (StudyUniverseObservation(smc.universe_id, 100, 50, 50),),
    )
    assert report.decisions[0].evidence_tier is EvidenceTier.EXCLUDED
    assert any(
        reason.startswith("hierarchical_capability_unavailable:")
        for reason in report.decisions[0].reasons
    )


def test_latest_registry_disposition_gate_rejects_an_orphan_manifest(
    tmp_path: Path,
) -> None:
    root = _copy_registry_for_transition_test(tmp_path)
    orphan_id = "orphan-study"
    (root / "studies" / f"{orphan_id}.json").write_text(
        json.dumps(
            {
                "schema_version": "tcga-trace-study-spec-v1",
                "dataset": {
                    "id": orphan_id,
                    "cancer_code": "BRCA",
                    "name": "Orphan test study",
                },
                "samples": {},
                "endpoints": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="undispositioned manifests: orphan-study"):
        require_study_registry_disposition(root, orphan_id)


def test_latest_registry_disposition_gate_accepts_catalog_only_study() -> None:
    root = Path(load_study_universe_registry().source_path).parent

    definition = require_study_registry_disposition(
        root, "fu-gbc-cancer-cell-2026"
    )

    assert definition.registry_category is StudyUniverseCategory.CATALOG_ONLY
    assert definition.capabilities.hierarchical_pancancer.available is False


def test_confirmed_overlap_clusters_have_one_preferred_release() -> None:
    registry = load_study_universe_registry()
    all_definitions = registry.definitions + registry.inactive_definitions
    preferred = preferred_release_by_cluster(all_definitions)

    assert preferred["kirc-checkmate-009-010-025-biomarker"] == (
        "pmc-kirc-checkmate-nivolumab-2020"
    )
    assert preferred["brca-nottingham-primary-icart1"] == (
        "biostudies-brca-nottingham-icart1-2024"
    )
    assert preferred["paad-apgi-paca-au"] == "icgc-paad-paca-au-2016"

    choueiri = registry.by_id["cbioportal-kirc-iatlas-choueiri-2016"]
    assert choueiri.preferred_release is False
    assert any(
        relation.relation_type == "confirmed_subset"
        and relation.suppresses_joint_inclusion
        for relation in choueiri.overlap_relations
    )


def test_related_partitions_are_linked_without_collapsing_universes() -> None:
    registry = load_study_universe_registry()

    pog = registry.by_id["cbioportal-brca-pog570-2020"]
    assert "pog570-cancer-partitions" in pog.partition_group_ids
    assert pog.study_cluster_id != registry.by_id[
        "cbioportal-coad-pog570-2020"
    ].study_cluster_id
    assert any(
        relation.relation_type == "disjoint_cancer_partition"
        and not relation.suppresses_joint_inclusion
        for relation in pog.overlap_relations
    )

    cgga = registry.by_id["cgga-gbm-mrnaseq-325-2020"]
    glass = registry.by_id["cbioportal-gbm-glass-2022"]
    gse = registry.by_id["geo-luad-steiner-gse273377-discovery-2026"]
    assert "cgga-release-and-disease-partitions" in cgga.partition_group_ids
    assert "glass-disease-partitions" in glass.partition_group_ids
    assert "gse273377-validation-partitions" in gse.partition_group_ids


def test_registry_classifies_context_and_os_time_origin() -> None:
    registry = load_study_universe_registry()

    assert registry.by_id["TCGA-BRCA"].clinical_context is (
        ClinicalContext.PRIMARY_LOCAL
    )
    assert registry.by_id["TCGA-LAML"].clinical_context is (
        ClinicalContext.HEMATOLOGIC
    )
    assert registry.by_id[
        "pmc-kirc-checkmate-nivolumab-2020"
    ].clinical_context is ClinicalContext.METASTATIC
    assert registry.by_id[
        "geo-blca-unc-gse176307-2021"
    ].clinical_context is ClinicalContext.METASTATIC
    assert registry.by_id[
        "geo-gbm-ucla-pembrolizumab-expansion-gse264695-2024"
    ].clinical_context is ClinicalContext.RECURRENT
    assert registry.by_id[
        "geo-brca-nsabp-b41-residual-gse275065-2025"
    ].clinical_context is ClinicalContext.POST_TREATMENT_RESIDUAL
    assert registry.by_id[
        "biostudies-blca-uromol-2016"
    ].clinical_context is ClinicalContext.UNKNOWN
    assert registry.by_id[
        "cbioportal-paad-cptac-gdc-2025"
    ].clinical_context is ClinicalContext.PRIMARY_LOCAL
    assert registry.by_id[
        "pmc-kirc-checkmate-nivolumab-2020"
    ].time_origin_class is TimeOriginClass.TREATMENT_START
    assert registry.by_id[
        "geo-brca-scanb-gse96058-2018"
    ].time_origin_class is TimeOriginClass.DIAGNOSIS


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Primary diagnosis", TimeOriginClass.DIAGNOSIS),
        ("Date of surgery", TimeOriginClass.SURGERY),
        ("First anti-PD-1 administration", TimeOriginClass.TREATMENT_START),
        ("Study entry", TimeOriginClass.STUDY_ENTRY),
        ("Study biopsy used for RNA profiling", TimeOriginClass.SPECIMEN_COLLECTION),
        ("Source-defined clinical origin, not specified", TimeOriginClass.UNKNOWN),
        (
            "Trial follow-up origin not more precisely specified",
            TimeOriginClass.UNKNOWN,
        ),
    ],
)
def test_time_origin_classification(
    value: str, expected: TimeOriginClass
) -> None:
    assert classify_time_origin(value) is expected


def test_release_ids_can_be_bound_at_the_database_boundary() -> None:
    registry = load_study_universe_registry(
        active_release_ids={
            "geo-brca-scanb-gse96058-2018": "scanb-release-sha",
            "TCGA-BRCA": "gdc-release-sha",
        }
    )

    assert registry.by_id[
        "geo-brca-scanb-gse96058-2018"
    ].release_id == "scanb-release-sha"
    assert registry.by_id["TCGA-BRCA"].release_id == "gdc-release-sha"


def test_preflight_applies_primary_and_exploratory_thresholds() -> None:
    registry = load_study_universe_registry()
    definitions = (
        registry.by_id["TCGA-BRCA"],
        registry.by_id["geo-brca-scanb-gse96058-2018"],
        registry.by_id["geo-brca-mdx-gse283522-2025"],
    )
    report = preflight_study_universes(
        definitions,
        (
            StudyUniverseObservation("TCGA-BRCA", 20, 10, 10),
            StudyUniverseObservation(
                "geo-brca-scanb-gse96058-2018", 18, 8, 10
            ),
            StudyUniverseObservation(
                "geo-brca-mdx-gse283522-2025", 9, 4, 5
            ),
        ),
    )
    by_id = {row.universe_id: row for row in report.decisions}

    assert by_id["TCGA-BRCA"].evidence_tier is EvidenceTier.PRIMARY
    assert by_id[
        "geo-brca-scanb-gse96058-2018"
    ].evidence_tier is EvidenceTier.EXPLORATORY
    mdx = by_id["geo-brca-mdx-gse283522-2025"]
    assert mdx.evidence_tier is EvidenceTier.EXCLUDED
    assert "patients_below_exploratory_minimum" in mdx.reasons
    assert "events_below_exploratory_minimum" in mdx.reasons


def test_preflight_keeps_context_and_time_origin_strict() -> None:
    registry = load_study_universe_registry()
    definitions = (
        registry.by_id["TCGA-BRCA"],
        registry.by_id["pmc-kirc-checkmate-nivolumab-2020"],
        registry.by_id["cgga-gbm-mrnaseq-325-2020"],
    )
    observations = tuple(
        StudyUniverseObservation(row.universe_id, 50, 25, 25)
        for row in definitions
    )
    report = preflight_study_universes(
        definitions,
        observations,
        target=SynthesisTarget(
            clinical_context=ClinicalContext.PRIMARY_LOCAL,
            time_origin_class=TimeOriginClass.DIAGNOSIS,
        ),
    )
    by_id = {row.universe_id: row for row in report.decisions}

    assert by_id["TCGA-BRCA"].primary_eligible
    checkmate = by_id["pmc-kirc-checkmate-nivolumab-2020"]
    assert checkmate.evidence_tier is EvidenceTier.EXCLUDED
    assert "clinical_context_mismatch:metastatic" in checkmate.reasons
    assert "time_origin_mismatch:treatment_start" in checkmate.reasons
    cgga = by_id["cgga-gbm-mrnaseq-325-2020"]
    assert "time_origin_mismatch:surgery" in cgga.reasons


def test_preflight_never_promotes_catalog_only_compatibility_strata() -> None:
    registry = load_study_universe_registry()
    definitions = (
        registry.by_id["TCGA-BRCA"],
        registry.by_id["cgga-gbm-mrnaseq-325-2020"],
    )
    report = preflight_study_universes(
        definitions,
        tuple(
            StudyUniverseObservation(row.universe_id, 50, 25, 25)
            for row in definitions
        ),
    )

    strata = report.synthesis_strata()
    assert strata == {
        "OS|diagnosis|primary_local": ("TCGA-BRCA",),
    }
    cgga = {
        row.universe_id: row for row in report.decisions
    }["cgga-gbm-mrnaseq-325-2020"]
    assert cgga.evidence_tier is EvidenceTier.EXCLUDED
    assert any(
        reason.startswith("hierarchical_capability_unavailable:")
        for reason in cgga.reasons
    )


def test_preflight_requires_observations_only_for_hierarchical_releases() -> None:
    registry = load_study_universe_registry()
    tcga = registry.by_id["TCGA-BRCA"]
    smc = registry.by_id["cbioportal-brca-smc-2018"]

    report = preflight_study_universes((tcga, smc), ())
    by_id = {row.universe_id: row for row in report.decisions}

    tcga_decision = by_id[tcga.universe_id]
    assert tcga_decision.evidence_tier is EvidenceTier.EXCLUDED
    assert "universe_not_observed" in tcga_decision.reasons

    smc_decision = by_id[smc.universe_id]
    assert smc_decision.evidence_tier is EvidenceTier.EXCLUDED
    assert "universe_not_observed" not in smc_decision.reasons
    assert any(
        reason.startswith("hierarchical_capability_unavailable:")
        for reason in smc_decision.reasons
    )


def test_preflight_selects_only_the_preferred_release_in_overlap_cluster() -> None:
    registry = load_study_universe_registry()
    choueiri = registry.by_id["cbioportal-kirc-iatlas-choueiri-2016"]
    checkmate = registry.by_id["pmc-kirc-checkmate-nivolumab-2020"]
    report = preflight_study_universes(
        (choueiri, checkmate),
        (
            StudyUniverseObservation(choueiri.universe_id, 40, 20, 20),
            StudyUniverseObservation(checkmate.universe_id, 181, 123, 58),
        ),
    )
    by_id = {row.universe_id: row for row in report.decisions}

    assert by_id[checkmate.universe_id].primary_eligible
    assert by_id[choueiri.universe_id].evidence_tier is EvidenceTier.EXCLUDED
    assert by_id[choueiri.universe_id].reasons[-1] == (
        "study_cluster_release_not_selected:"
        "pmc-kirc-checkmate-nivolumab-2020"
    )


def test_preflight_can_fall_back_when_preferred_release_is_not_eligible() -> None:
    registry = load_study_universe_registry()
    choueiri = registry.by_id["cbioportal-kirc-iatlas-choueiri-2016"]
    checkmate = registry.by_id["pmc-kirc-checkmate-nivolumab-2020"]
    report = preflight_study_universes(
        (choueiri, checkmate),
        (
            StudyUniverseObservation(choueiri.universe_id, 40, 20, 20),
            StudyUniverseObservation(checkmate.universe_id, 8, 4, 4),
        ),
    )
    by_id = {row.universe_id: row for row in report.decisions}

    assert by_id[choueiri.universe_id].primary_eligible
    assert "preferred_release_unavailable_fallback" in by_id[
        choueiri.universe_id
    ].reasons
    assert by_id[checkmate.universe_id].evidence_tier is EvidenceTier.EXCLUDED


def test_preflight_rejects_non_os_and_inconsistent_counts() -> None:
    registry = load_study_universe_registry()
    no_os = registry.by_id["geo-brca-nsabp-b41-residual-gse275065-2025"]
    inconsistent = replace(
        registry.by_id["TCGA-BRCA"], universe_id="test-inconsistent"
    )
    report = preflight_study_universes(
        (no_os, inconsistent),
        (
            StudyUniverseObservation(no_os.universe_id, 50, 20, 30),
            StudyUniverseObservation("test-inconsistent", 50, 20, 20),
        ),
    )
    by_id = {row.universe_id: row for row in report.decisions}

    assert "endpoint_not_compatible_os" in by_id[no_os.universe_id].reasons
    assert "inconsistent_event_and_censor_counts" in by_id[
        "test-inconsistent"
    ].reasons


def test_preflight_does_not_pool_unclassified_origin_or_context() -> None:
    registry = load_study_universe_registry()
    unknown_origin = registry.by_id["geo-blca-unc-gse176307-2021"]
    unknown_context = registry.by_id[
        "geo-skcm-sunexposed-yale-gse190113-2022"
    ]
    report = preflight_study_universes(
        (unknown_origin, unknown_context),
        (
            StudyUniverseObservation(unknown_origin.universe_id, 78, 40, 38),
            StudyUniverseObservation(unknown_context.universe_id, 58, 30, 28),
        ),
    )
    by_id = {row.universe_id: row for row in report.decisions}

    assert "time_origin_not_classifiable" in by_id[
        unknown_origin.universe_id
    ].reasons
    assert "clinical_context_not_classifiable" in by_id[
        unknown_context.universe_id
    ].reasons
    assert report.synthesis_strata() == {}


def test_preflight_rejects_unknown_observation_ids() -> None:
    definition = StudyUniverseDefinition(
        universe_id="known",
        study_cluster_id="known",
        source_kind=SourceKind.EXTERNAL,
        cancer_code="BRCA",
        name="Known",
        clinical_context=ClinicalContext.PRIMARY_LOCAL,
        endpoint_class="OS",
        endpoint_id="OS",
        time_origin="Diagnosis",
        time_origin_class=TimeOriginClass.DIAGNOSIS,
        preferred_release=True,
        preferred_dataset_id="known",
    )

    with pytest.raises(ValueError, match="unknown study universes"):
        preflight_study_universes(
            (definition,),
            (StudyUniverseObservation("unknown", 50, 20, 30),),
        )
