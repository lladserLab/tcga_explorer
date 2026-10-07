import json
from pathlib import Path

import pytest

from app.repository.adapters.cbioportal import sample_passes_eligibility
from app.repository.adapters.gdc import (
    resolve_gdc_sample_type_priority,
    select_gdc_expression_files,
    validate_expected_gdc_count,
    validate_expected_gdc_value,
    validate_gdc_project_policy,
)
from app.repository.contracts import (
    STUDY_SPEC_SCHEMA_VERSION_V2,
    require_supported_study_spec,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_SPEC_DIR = (
    PROJECT_ROOT / "repository_registry" / "candidate_specs"
)
PROMOTED_SPEC_DIR = PROJECT_ROOT / "repository_registry" / "studies"

GDC_CONTRACTS = {
    "gdc-target-aml": {
        "cancer_code": "PAML",
        "project_id": "TARGET-AML",
        "sample_types": [
            "Primary Blood Derived Cancer - Bone Marrow",
            "Primary Blood Derived Cancer - Peripheral Blood",
        ],
        "source_files": 3227,
        "patients": 2112,
    },
    "gdc-rc-ptcl": {
        "cancer_code": "PTCL",
        "project_id": "RC-PTCL",
        "sample_types": ["Tumor"],
        "source_files": 55,
        "patients": 54,
    },
    "gdc-ccg-cupp": {
        "cancer_code": "CUP",
        "project_id": "CCG-CUPP",
        "sample_types": ["Metastatic", "FFPE Scrolls"],
        "source_files": 29,
        "patients": 29,
    },
    "gdc-target-all-p2": {
        "cancer_code": "ALL",
        "project_id": "TARGET-ALL-P2",
        "sample_types": [
            "Primary Blood Derived Cancer - Bone Marrow",
            "Primary Blood Derived Cancer - Peripheral Blood",
        ],
        "source_files": 532,
        "patients": 452,
    },
    "gdc-target-nbl": {
        "cancer_code": "NBL",
        "project_id": "TARGET-NBL",
        "sample_types": ["Primary Tumor"],
        "source_files": 162,
        "patients": 153,
    },
    "gdc-target-os": {
        "cancer_code": "OSARC",
        "project_id": "TARGET-OS",
        "sample_types": ["Primary Tumor"],
        "source_files": 88,
        "patients": 88,
    },
    "gdc-target-rt": {
        "cancer_code": "RT",
        "project_id": "TARGET-RT",
        "sample_types": ["Primary Tumor"],
        "source_files": 69,
        "patients": 63,
    },
    "gdc-target-wt": {
        "cancer_code": "WT",
        "project_id": "TARGET-WT",
        "sample_types": ["Primary Tumor"],
        "source_files": 136,
        "patients": 124,
    },
}
BRCA_SMC_ID = "cbioportal-brca-smc-2018"
EXPECTED_IDS = frozenset(GDC_CONTRACTS)

NEW_TAXONOMIES = {
    "PAML",
    "ALL",
    "PTCL",
    "CUP",
    "OSARC",
    "RT",
    "WT",
    "MM",
    "EPN",
    "BL",
    "HIVLC",
    "MB",
    "PHGG",
    "ATRT",
    "ALCL",
    "MDSAML",
    "MTC",
    "MNG",
    "OCCC",
    "FHRCC",
    "MFSUPS",
    "EOCNHG",
    "UTUC",
    "CHS",
    "NST",
    "ASCC",
}


def _candidate_specs() -> dict[str, dict]:
    specs = {}
    for path in sorted(CANDIDATE_SPEC_DIR.glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        dataset_id = str(spec["dataset"]["id"])
        assert path.stem == dataset_id
        specs[dataset_id] = spec
    return specs


def _gdc_hit(
    patient_id: str,
    sample_id: str,
    file_id: str,
    *,
    sample_type: str = "",
    tissue_type: str = "Tumor",
) -> dict:
    return {
        "file_id": file_id,
        "file_name": f"{file_id}.tsv",
        "file_size": 100,
        "md5sum": "a" * 32,
        "associated_entities": [
            {
                "entity_id": f"aliquot-{file_id}",
                "entity_type": "aliquot",
            }
        ],
        "cases": [
            {
                "case_id": f"case-{patient_id}",
                "submitter_id": patient_id,
                "samples": [
                    {
                        "sample_id": f"uuid-{sample_id}",
                        "submitter_id": sample_id,
                        "sample_type": sample_type,
                        "tissue_type": tissue_type,
                        "portions": [
                            {
                                "analytes": [
                                    {
                                        "aliquots": [
                                            {
                                                "aliquot_id": (
                                                    f"aliquot-{file_id}"
                                                ),
                                                "submitter_id": (
                                                    f"{sample_id}-RNA"
                                                ),
                                            }
                                        ]
                                    }
                                ]
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_candidate_specs_are_complete_and_not_promoted():
    specs = _candidate_specs()

    assert set(specs) == EXPECTED_IDS
    assert not {
        path.stem for path in PROMOTED_SPEC_DIR.glob("*.json")
    }.intersection(EXPECTED_IDS)

    candidate_inventory = json.loads(
        (
            PROJECT_ROOT
            / "repository_registry"
            / "dataset_candidates_v1.json"
        ).read_text(encoding="utf-8")
    )
    by_id = {
        row["id"]: row
        for row in candidate_inventory["candidates"]
        if row["id"] in EXPECTED_IDS
    }
    assert set(by_id) == EXPECTED_IDS
    for dataset_id, row in by_id.items():
        assert row["status"] == "under_review"
        assert row["decisions"]["promotion_state"] == "not_promoted"
        assert row["tier"] == "S1"


def test_new_disease_taxonomies_are_external_only_without_ready_counts():
    registry = json.loads(
        (
            PROJECT_ROOT / "repository_registry" / "cancer_types.json"
        ).read_text(encoding="utf-8")
    )
    rows = registry["cancer_types"]
    by_code = {row["code"]: row for row in rows}

    assert len(by_code) == len(rows)
    assert NEW_TAXONOMIES.issubset(by_code)
    for code in NEW_TAXONOMIES:
        assert by_code[code]["cohort_kind"] == "external_only"
        assert by_code[code]["tcga_cohort"] == f"EXT-{code}"
        assert "summary" not in by_code[code]

    assert by_code["NBL"]["cohort_kind"] == "external_only"
    assert by_code["NBL"]["tcga_cohort"] == "EXT-NBL"


@pytest.mark.parametrize("dataset_id", sorted(GDC_CONTRACTS))
def test_s1_gdc_specs_pin_population_and_os_contract(dataset_id):
    spec = _candidate_specs()[dataset_id]
    expected = GDC_CONTRACTS[dataset_id]
    dataset = spec["dataset"]
    source = spec["source"]

    assert require_supported_study_spec(spec) == (
        STUDY_SPEC_SCHEMA_VERSION_V2
    )
    assert dataset["cancer_code"] == expected["cancer_code"]
    assert dataset["cohort_context"].strip()
    assert dataset["metadata"]["candidate_tier"] == "S1"
    assert dataset["metadata"]["promotion_state"] == "not_promoted"
    assert source["provider"] == "gdc_api"
    assert source["project_id"] == expected["project_id"]
    assert source["sample_type_priority"] == expected["sample_types"]
    assert resolve_gdc_sample_type_priority(
        STUDY_SPEC_SCHEMA_VERSION_V2, source
    ) == expected["sample_types"]
    assert source["expected_expression_files"] == expected["source_files"]
    assert source["expected_selected_patients"] == expected["patients"]
    assert source["expected_data_release"] == (
        "Data Release 46.0 - August 10, 2026"
    )
    assert source["expected_api_version"] == "8.5.0"
    assert source["license_evidence_url"].startswith(
        "https://gdc.cancer.gov/"
    )

    if expected["project_id"].startswith("TARGET-"):
        assert source["target_project_opt_in"] == expected["project_id"]
    else:
        assert "target_project_opt_in" not in source
    validate_gdc_project_policy(
        STUDY_SPEC_SCHEMA_VERSION_V2,
        source,
        expected["project_id"],
    )

    assert [endpoint["endpoint_id"] for endpoint in spec["endpoints"]] == [
        "OS"
    ]
    endpoint = spec["endpoints"][0]
    assert endpoint["standard_code"] == "OS"
    assert endpoint["time_column"] == "GDC_OS_DAYS"
    assert endpoint["event_column"] == "GDC_OS_STATUS"
    assert endpoint["time_unit"] == "days"
    assert endpoint["time_origin"].startswith("Diagnosis")
    assert endpoint["event_definition"] == "Death from any cause"
    assert endpoint["censor_prefix"] == "0:"
    assert endpoint["event_prefix"] == "1:"


def test_target_sample_allowlists_cannot_fall_back_to_other_disease_states():
    specs = _candidate_specs()
    disallowed = {
        "Solid Tissue Normal",
        "Blood Derived Normal",
        "Bone Marrow Normal",
        "Recurrent Tumor",
        "Recurrent Blood Derived Cancer - Bone Marrow",
        "Recurrent Blood Derived Cancer - Peripheral Blood",
        "Metastatic",
        "Cell Lines",
        "Next Generation Cancer Model",
        "Blood Derived Cancer - Bone Marrow, Post-treatment",
        "Blood Derived Cancer - Peripheral Blood, Post-treatment",
    }
    for dataset_id, expected in GDC_CONTRACTS.items():
        if not expected["project_id"].startswith("TARGET-"):
            continue
        source_types = set(specs[dataset_id]["source"]["sample_type_priority"])
        assert source_types.isdisjoint(disallowed)
        sample_type_rule = specs[dataset_id]["samples"][
            "eligibility_rules"
        ][0]
        assert set(sample_type_rule["include"]) == source_types
        assert sample_type_rule["required"] is True


def test_rc_ptcl_missing_sample_type_and_recurrence_are_fail_closed():
    spec = _candidate_specs()["gdc-rc-ptcl"]
    source = spec["source"]
    primary = _gdc_hit(
        "RC-B5D0", "RC-B5D0-TBP1-A", "primary-file"
    )
    recurrence = _gdc_hit(
        "RC-B5D0", "RC-B5D0-TBR1-A", "recurrence-file"
    )

    selected, summary = select_gdc_expression_files(
        [recurrence, primary],
        None,
        sample_type_priority=source["sample_type_priority"],
        sample_eligibility_rules=source["sample_eligibility_rules"],
        missing_sample_type_policy=source["missing_sample_type_policy"],
    )

    assert [row["sample_id"] for row in selected] == ["RC-B5D0-TBP1-A"]
    assert selected[0]["sample_type"] == "Tumor"
    assert selected[0]["sample_type_resolution"] == (
        "explicit_missing_sample_type_policy"
    )
    assert summary["excluded_by_sample_eligibility"] == 1
    assert summary["resolved_missing_sample_types"] == 2

    selected_without_policy, _ = select_gdc_expression_files(
        [primary],
        None,
        sample_type_priority=["Tumor"],
    )
    assert selected_without_policy == []

    selected_wrong_tissue, _ = select_gdc_expression_files(
        [
            _gdc_hit(
                "RC-NORMAL",
                "RC-NORMAL-TBP1-A",
                "normal-file",
                tissue_type="Normal",
            )
        ],
        None,
        sample_type_priority=["Tumor"],
        missing_sample_type_policy=source["missing_sample_type_policy"],
    )
    assert selected_wrong_tissue == []


def test_ccg_cupp_contract_is_metastatic_and_never_primary_fallback():
    spec = _candidate_specs()["gdc-ccg-cupp"]
    source_types = spec["source"]["sample_type_priority"]

    assert source_types == ["Metastatic", "FFPE Scrolls"]
    assert "metastatic" in spec["dataset"]["cohort_context"].casefold()
    assert "Primary Tumor" not in source_types
    assert "Recurrent Tumor" not in source_types
    assert "Solid Tissue Normal" not in source_types
    assert spec["source"]["sample_eligibility_rules"] == [
        {
            "field": "sample.sample_type",
            "include": ["Metastatic", "FFPE Scrolls"],
            "required": True,
        },
        {
            "field": "sample.tissue_type",
            "include": ["Tumor"],
            "required": True,
        },
    ]


def test_brca_smc_is_primary_pam50_expression_only():
    spec = json.loads(
        (PROMOTED_SPEC_DIR / f"{BRCA_SMC_ID}.json").read_text(
            encoding="utf-8"
        )
    )
    source = spec["source"]

    assert require_supported_study_spec(spec) == (
        STUDY_SPEC_SCHEMA_VERSION_V2
    )
    assert spec["dataset"]["cancer_code"] == "BRCA"
    assert spec["dataset"]["metadata"]["candidate_tier"] == "E1"
    assert spec["dataset"]["metadata"]["promotion_state"] == "promoted"
    assert source["provider"] == "cbioportal_api"
    assert source["study_id"] == "brca_smc_2018"
    assert source["molecular_profile_id"] == (
        "brca_smc_2018_mrna_seq_tpm"
    )
    assert source["sample_list_id"] == "brca_smc_2018_tpm"
    assert source["expected_expression_samples"] == 168
    assert source["expected_eligible_expression_samples"] == 168
    assert source["expected_eligible_expression_patients"] == 168
    assert spec["expression"]["source_unit"] == "TPM"
    assert spec["expression"]["transform"] == "log2p"

    assert sample_passes_eligibility(
        {},
        {
            "SAMPLE_TYPE": "Primary",
            "SAMPLE_CLASS": "Tumor",
            "ONCOTREE_CODE": "IDC",
            "PAM50_SUBTYPE": "LuminalA",
        },
        source["sample_eligibility_rules"],
    )
    assert not sample_passes_eligibility(
        {},
        {
            "SAMPLE_TYPE": "Metastasis",
            "SAMPLE_CLASS": "Tumor",
            "ONCOTREE_CODE": "IDC",
            "PAM50_SUBTYPE": "LuminalA",
        },
        source["sample_eligibility_rules"],
    )
    assert not sample_passes_eligibility(
        {},
        {
            "SAMPLE_TYPE": "Primary",
            "SAMPLE_CLASS": "Tumor",
            "ONCOTREE_CODE": "IDC",
            "PAM50_SUBTYPE": "",
        },
        source["sample_eligibility_rules"],
    )

    audited = spec["dataset"]["metadata"]["audited_population"]
    assert audited["status"] == "passed_bundle_qc"
    assert audited["mapped_complete_genes"] == 21389
    assert audited["variable_genes"] == 20935
    assert audited["nonfinite_expression_values"] == 0
    pam50_counts = audited[
        "pam50_counts"
    ]
    assert pam50_counts == {
        "Basal": 36,
        "Her2": 18,
        "LuminalA": 47,
        "LuminalB": 65,
        "Normal": 2,
    }
    assert sum(pam50_counts.values()) == 168
    assert spec["endpoints"] == []
    prohibited = spec["capability_policy"]["prohibited"]
    assert set(prohibited) == {"survival"}
    assert "time-to-event" in prohibited["survival"]


def test_pinned_gdc_counts_stop_source_drift_before_download():
    source = {"expected_expression_files": 55}
    validate_expected_gdc_count(
        source,
        "expected_expression_files",
        55,
        "GDC expression file",
    )
    with pytest.raises(ValueError, match="count changed"):
        validate_expected_gdc_count(
            source,
            "expected_expression_files",
            56,
            "GDC expression file",
        )

    validate_expected_gdc_value(
        {"expected_data_release": "Data Release 46.0"},
        "expected_data_release",
        "Data Release 46.0",
        "GDC data release",
    )
    with pytest.raises(ValueError, match="data release changed"):
        validate_expected_gdc_value(
            {"expected_data_release": "Data Release 46.0"},
            "expected_data_release",
            "Data Release 47.0",
            "GDC data release",
        )
