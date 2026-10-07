from dataclasses import dataclass, field
import json
from pathlib import Path

import pytest

from app.clinical_grouping import (
    CLINICAL_GROUPING_CATALOG_VERSION,
    apply_custom_clinical_filters,
    clinical_grouping_context,
    resolve_clinical_grouping_variable,
)
from app.gsea import clinical_group_assignments, group_assignment_rows
from app.schemas import (
    ExpressionComparisonRequest,
    FilterOptions,
    GseaAnalysisRequest,
    GseaGroupingDefinition,
)


@dataclass
class MockSample:
    patient_id: str
    barcode: str
    sample_type: str = "Primary Tumor"
    stage: str | None = "Stage II"
    grade: str | None = None
    gender: str | None = "female"
    race: str | None = "white"
    age_at_index: float | None = 55.0
    selection_rank: int = 0
    raw_metadata: dict = field(default_factory=dict)


def _write_brca_metadata(root: Path) -> list[MockSample]:
    cohort_dir = root / "TCGA-BRCA"
    cohort_dir.mkdir(parents=True)
    rows = []
    samples = []
    for index in range(12):
        patient = f"TCGA-AA-{index:04d}"
        barcode = f"{patient}-01A"
        subtype = "LumA" if index < 6 else "Basal"
        pathology = "IDC" if index < 8 else "ILC"
        nodal = "N0" if index % 2 == 0 else "N1"
        rows.append(
            f"{barcode}\t{patient}\t{subtype}\t{pathology}\t{nodal}\t1\t"
            f"{'Left' if index % 2 else 'Right'}\n"
        )
        samples.append(MockSample(patient, barcode))
    (cohort_dir / "col_data.tsv").write_text(
        "\tpatient_id\tpaper_BRCA_Subtype_PAM50\t"
        "paper_BRCA_Pathology\tajcc_pathologic_n\t"
        "diagnosis_is_primary_disease\tlaterality\n"
        + "".join(rows),
        encoding="utf-8",
    )
    return samples


def test_brca_pam50_and_cdr_fields_are_catalogued_and_assignable(
    tmp_path: Path,
) -> None:
    samples = _write_brca_metadata(tmp_path)
    cdr_path = tmp_path / "cdr.tsv"
    cdr_path.write_text(
        "bcr_patient_barcode\ttype\tmenopause_status\n"
        + "".join(
            f"{sample.patient_id}\tBRCA\t"
            f"{'Pre' if index < 6 else 'Post'}\n"
            for index, sample in enumerate(samples)
        ),
        encoding="utf-8",
    )

    catalog, _ = clinical_grouping_context(
        samples,
        cohort="TCGA-BRCA",
        tcga_data_dir=tmp_path,
        tcga_cdr_path=cdr_path,
    )
    pam50 = next(
        item for item in catalog if item["id"] == "paper_BRCA_Subtype_PAM50"
    )
    menopause = next(
        item for item in catalog if item["id"] == "cdr.menopause_status"
    )

    assert pam50["label"] == "PAM50 intrinsic subtype"
    assert pam50["catalog_version"] == CLINICAL_GROUPING_CATALOG_VERSION
    assert pam50["patient_count"] == 12
    assert pam50["non_missing_count"] == 12
    assert pam50["levels"] == [
        {
            "value": "Basal",
            "label": "Basal-like (PAM50)",
            "count": 6,
            "analysis_eligible": True,
            "unavailable_reason": None,
        },
        {
            "value": "LumA",
            "label": "Luminal A (PAM50)",
            "count": 6,
            "analysis_eligible": True,
            "unavailable_reason": None,
        },
    ]
    assert pam50["expression_derived"] is True
    assert "circular" in pam50["analysis_note"]
    assert pam50["provenance"] == {
        "origin": "source_reported_molecular",
        "label": "Published molecular call",
        "reported_by": "TCGA marker-paper annotation",
        "method_summary": (
            "Author-provided PAM50 call published with TCGA-BRCA; TRACE "
            "reads the reported call and does not rerun the classifier."
        ),
        "reference": {
            "label": "TCGA Breast Cancer, Nature 2012",
            "doi": "10.1038/nature11412",
            "url": "https://doi.org/10.1038/nature11412",
        },
        "expression_derived": True,
        "recomputed_by_trace": False,
        "comparability": (
            "Method-dependent. Do not assume equivalence to receptor-defined "
            "subtype, a clinical assay, or a call from another expression platform."
        ),
    }
    assert menopause["provenance"]["origin"] == "harmonized_clinical"
    assert menopause["analysis_eligible"] is True
    FilterOptions(
        sample_types=[],
        stages=[],
        grades=[],
        genders=[],
        races=[],
        clinical_grouping_variables=catalog,
    )

    definition, values = resolve_clinical_grouping_variable(
        samples,
        "paper_BRCA_Subtype_PAM50",
        cohort="TCGA-BRCA",
        tcga_data_dir=tmp_path,
        tcga_cdr_path=cdr_path,
    )
    grouping = GseaGroupingDefinition(
        source="clinical",
        clinical_variable="paper_BRCA_Subtype_PAM50",
        group_a_label="Luminal A",
        group_b_label="Basal",
        group_a_values=["LumA"],
        group_b_values=["Basal"],
    )
    assignments, details = clinical_group_assignments(
        samples,
        grouping,
        variable_values=values,
        variable_definition=definition,
    )
    assert list(assignments.values()).count("a") == 6
    assert list(assignments.values()).count("b") == 6
    assert details["variable_source_field"] == "paper_BRCA_Subtype_PAM50"
    assert details["expression_derived_grouping"] is True
    assert details["variable_provenance"] == pam50["provenance"]


def test_tcga_pam50_and_nodal_filters_combine_with_and_semantics(
    tmp_path: Path,
) -> None:
    samples = _write_brca_metadata(tmp_path)

    selected, audit, warnings = apply_custom_clinical_filters(
        samples,
        [
            {
                "variable_id": "paper_BRCA_Subtype_PAM50",
                "categorical_levels": ["LumA"],
            },
            {
                "variable_id": "ajcc_pathologic_n",
                "categorical_levels": ["N0"],
            },
        ],
        analysis_context="expression",
        cohort="TCGA-BRCA",
        tcga_data_dir=tmp_path,
        repository=False,
    )

    assert [sample.patient_id for sample in selected] == [
        "TCGA-AA-0000",
        "TCGA-AA-0002",
        "TCGA-AA-0004",
    ]
    assert [item["variable_id"] for item in audit] == [
        "paper_BRCA_Subtype_PAM50",
        "ajcc_pathologic_n",
    ]
    assert audit[0]["category"] == "tumor_specific"
    assert audit[0]["source"] == "TCGA marker-paper annotation"
    assert audit[0]["expression_derived"] is True
    assert audit[0]["provenance"]["origin"] == "source_reported_molecular"
    assert audit[0]["patients_considered"] == 12
    assert audit[0]["patients_retained"] == 6
    assert audit[0]["samples_considered"] == 12
    assert audit[1]["patients_considered"] == 6
    assert audit[1]["patients_retained"] == 3
    assert audit[1]["source_field"] == "ajcc_pathologic_n"
    assert any("circular" in warning for warning in warnings)


@pytest.mark.parametrize(
    "request_model, extra",
    [
        (GseaAnalysisRequest, {"gene_set_collection": "immport"}),
        (ExpressionComparisonRequest, {"genes": ["MKI67"]}),
    ],
)
def test_grouping_variable_cannot_also_be_a_clinical_filter(
    request_model,
    extra,
) -> None:
    payload = {
        "cohort": "TCGA-BRCA",
        "expression_scale": "log2_tpm",
        "filters": {
            "sample_population": "primary_solid",
            "custom_filters": [
                {
                    "variable_id": "paper_BRCA_Subtype_PAM50",
                    "categorical_levels": ["LumA"],
                }
            ],
        },
        "grouping": {
            "source": "clinical",
            "clinical_variable": "paper_BRCA_Subtype_PAM50",
            "group_a_label": "Luminal A",
            "group_b_label": "Basal-like",
            "group_a_values": ["LumA"],
            "group_b_values": ["Basal"],
        },
        **extra,
    }

    with pytest.raises(ValueError, match="cannot define the groups"):
        request_model(**payload)


def test_undeclared_tcga_field_is_rejected(tmp_path: Path) -> None:
    samples = _write_brca_metadata(tmp_path)
    with pytest.raises(ValueError, match="is not declared"):
        resolve_clinical_grouping_variable(
            samples,
            "paper_patient_identifier",
            cohort="TCGA-BRCA",
            tcga_data_dir=tmp_path,
        )


def test_external_catalog_discovers_only_semantic_categorical_metadata() -> None:
    samples = [
        MockSample(
            patient_id=f"P{index}",
            barcode=f"S{index}",
            stage=None,
            grade=f"T{1 + index % 2}",
            raw_metadata={
                "clinical": {
                    "PAM50_subtype": "LumA" if index < 6 else "Basal",
                    "patient_id": f"SECRET-{index}",
                    "OS_TIME_DAYS": 100 + index,
                }
            },
        )
        for index in range(12)
    ]

    catalog, _ = clinical_grouping_context(
        samples,
        cohort="TCGA-BRCA",
        repository=True,
    )
    pam50 = next(
        item
        for item in catalog
        if item["source_field"] == "clinical.PAM50_subtype"
    )
    grade = next(item for item in catalog if item["id"] == "grade")

    assert pam50["analysis_eligible"] is True
    assert pam50["category"] == "dataset_specific"
    assert pam50["provenance"]["origin"] == "source_reported_molecular"
    assert pam50["provenance"]["recomputed_by_trace"] is False
    assert not any("patient_id" in item["source_field"] for item in catalog)
    assert not any("OS_TIME" in item["source_field"] for item in catalog)
    assert grade["analysis_eligible"] is False
    assert "failed semantic QC" in grade["unavailable_reason"]


def test_external_catalog_decodes_serialized_geo_metadata_and_canonicalizes_levels(
) -> None:
    samples = []
    for index in range(12):
        sex = ("M", "Male", "MALE")[index % 3] if index < 6 else (
            "F",
            "Female",
            "FEMALE",
        )[index % 3]
        samples.append(
            MockSample(
                patient_id=f"P{index}",
                barcode=f"S{index}",
                stage=None,
                grade=None,
                gender=None,
                raw_metadata={
                    "sample": {
                        "GEO_SAMPLE_METADATA_JSON": json.dumps(
                            {
                                "characteristics": {
                                    "pam50 subtype": (
                                        "LumA" if index < 6 else "Basal"
                                    ),
                                    "er status": "1" if index < 6 else "0",
                                    "sex": sex,
                                }
                            }
                        )
                    }
                },
            )
        )

    catalog, values = clinical_grouping_context(
        samples,
        cohort="TCGA-BRCA",
        repository=True,
    )
    pam50 = next(
        item
        for item in catalog
        if item["source_field"].endswith("characteristics.pam50 subtype")
    )
    sex = next(
        item
        for item in catalog
        if item["source_field"].endswith("characteristics.sex")
    )

    assert pam50["analysis_eligible"] is True
    assert pam50["expression_derived"] is True
    assert {level["value"]: level["count"] for level in pam50["levels"]} == {
        "Basal": 6,
        "LumA": 6,
    }
    assert {level["value"]: level["count"] for level in sex["levels"]} == {
        "Female": 6,
        "Male": 6,
    }
    assert set(values[sex["id"]].values()) == {"Female", "Male"}


def test_external_duplicate_grade_cannot_bypass_semantic_qc() -> None:
    samples = [
        MockSample(
            patient_id=f"P{index}",
            barcode=f"S{index}",
            grade=None,
            raw_metadata={
                "sample": {"GRADE": "T1" if index < 6 else "T2"}
            },
        )
        for index in range(12)
    ]

    catalog, _ = clinical_grouping_context(
        samples,
        cohort="TCGA-BRCA",
        repository=True,
    )
    raw_grade = next(
        item for item in catalog if item["source_field"] == "sample.GRADE"
    )
    assert raw_grade["analysis_eligible"] is False
    assert "failed semantic QC" in raw_grade["unavailable_reason"]


def test_group_assignment_export_retains_missing_and_unselected_clinical_rows(
) -> None:
    samples = [
        MockSample("P1", "S1"),
        MockSample("P2", "S2"),
        MockSample("P3", "S3"),
        MockSample("P4", "S4"),
    ]
    rows = group_assignment_rows(
        samples,
        {"S1": "a", "S2": "b"},
        {
            "source": "clinical",
            "variable": "paper_BRCA_Subtype_PAM50",
            "variable_label": "PAM50 intrinsic subtype",
            "variable_source": "TCGA marker-paper annotation",
            "variable_source_field": "paper_BRCA_Subtype_PAM50",
            "group_a_label": "Luminal A",
            "group_b_label": "Basal-like",
        },
        clinical_values={
            "S1": "LumA",
            "S2": "Basal",
            "S3": "LumB",
            "S4": None,
        },
    )

    assert len(rows) == 4
    assert rows[0]["analysis_included"] is True
    assert rows[0]["clinical_value"] == "LumA"
    assert rows[2]["analysis_included"] is False
    assert rows[2]["exclusion_reason"] == "unselected_clinical_level"
    assert rows[3]["exclusion_reason"] == "missing_clinical_value"


def test_catalog_declared_numeric_field_uses_generic_cutpoint(tmp_path: Path) -> None:
    cohort_dir = tmp_path / "TCGA-HNSC"
    cohort_dir.mkdir(parents=True)
    samples = [
        MockSample(f"TCGA-AA-{index:04d}", f"TCGA-AA-{index:04d}-01A")
        for index in range(12)
    ]
    (cohort_dir / "col_data.tsv").write_text(
        "\tpatient_id\tpack_years_smoked\n"
        + "".join(
            f"{sample.barcode}\t{sample.patient_id}\t{index * 10}\n"
            for index, sample in enumerate(samples)
        ),
        encoding="utf-8",
    )

    definition, values = resolve_clinical_grouping_variable(
        samples,
        "pack_years_smoked",
        cohort="TCGA-HNSC",
        tcga_data_dir=tmp_path,
    )
    assignments, details = clinical_group_assignments(
        samples,
        GseaGroupingDefinition(
            source="clinical",
            clinical_variable="pack_years_smoked",
            clinical_cutpoint_method="value",
            clinical_cutpoint=50,
            group_a_label="Lower exposure",
            group_b_label="Higher exposure",
        ),
        variable_values=values,
        variable_definition=definition,
    )

    assert definition["value_type"] == "numeric"
    assert definition["numeric_summary"] == {
        "min": 0.0,
        "max": 110.0,
        "median": 55.0,
        "unit": "pack-years",
    }
    assert list(assignments.values()).count("a") == 6
    assert list(assignments.values()).count("b") == 6
    assert details["group_a_definition"] == "Pack-years smoked <= 50"


def test_external_catalog_coalesces_metadata_mirrors_and_excludes_sentinels(
) -> None:
    samples = []
    for index in range(12):
        response = "Responder" if index < 6 else "Non-Responder"
        fish = "P" if index < 6 else ("N" if index < 11 else "missing")
        samples.append(
            MockSample(
                patient_id=f"P{index}",
                barcode=f"S{index}",
                stage=None,
                raw_metadata={
                    "patient": {
                        "Response": response,
                        "PMC_CLINICAL_METADATA_JSON": json.dumps(
                            {"Response": response}
                        ),
                        "GEO_SAMPLE_METADATA_JSON": json.dumps(
                            {"characteristics": {"her2 dna_fish": fish}}
                        ),
                    }
                },
            )
        )

    catalog, _ = clinical_grouping_context(
        samples,
        cohort="TCGA-BRCA",
        repository=True,
    )
    responses = [item for item in catalog if item["label"] == "Response"]
    fish = next(item for item in catalog if item["label"] == "HER2 dna FISH")

    assert len(responses) == 1
    assert fish["non_missing_count"] == 11
    assert fish["missing_count"] == 1
    assert {level["value"] for level in fish["levels"]} == {"N", "P"}


def test_external_breast_fields_have_readable_labels_and_numeric_irs() -> None:
    samples = [
        MockSample(
            patient_id=f"P{index}",
            barcode=f"S{index}",
            stage=None,
            raw_metadata={
                "patient": {
                    "GEO_SAMPLE_METADATA_JSON": json.dumps(
                        {
                            "characteristics": {
                                "pam50 subtype": "LumA" if index < 6 else "Her2",
                                "er status": "1" if index < 6 else "0",
                                "pr negpos": "P" if index < 6 else "N",
                                "pr irs": index,
                            }
                        }
                    )
                }
            },
        )
        for index in range(12)
    ]

    catalog, _ = clinical_grouping_context(
        samples,
        cohort="TCGA-BRCA",
        repository=True,
    )
    pam50 = next(item for item in catalog if item["label"] == "PAM50 intrinsic subtype")
    er = next(item for item in catalog if item["label"] == "ER status (observed)")
    pr = next(item for item in catalog if item["label"] == "PR status (observed)")
    irs = next(
        item
        for item in catalog
        if item["label"] == "PR immunoreactive score (IRS)"
    )

    assert {level["label"] for level in pam50["levels"]} == {
        "HER2-enriched (PAM50)",
        "Luminal A (PAM50)",
    }
    assert {level["label"] for level in er["levels"]} == {"Negative", "Positive"}
    assert {level["label"] for level in pr["levels"]} == {"Negative", "Positive"}
    assert irs["value_type"] == "numeric"
    assert irs["numeric_summary"]["median"] == 5.5


def test_standard_fallback_and_rare_level_eligibility_are_explicit() -> None:
    samples = []
    for index in range(12):
        subtype = "A" if index < 6 else ("B" if index < 11 else "Rare")
        samples.append(
            MockSample(
                patient_id=f"P{index}",
                barcode=f"S{index}",
                stage=None,
                gender=None,
                raw_metadata={
                    "patient": {
                        "Sex 0=male 1=female": "0" if index < 6 else "1",
                        "molecular subtype": subtype,
                    }
                },
            )
        )

    catalog, _ = clinical_grouping_context(
        samples,
        cohort="TCGA-BRCA",
        repository=True,
    )
    gender = next(item for item in catalog if item["id"] == "gender")
    subtype = next(item for item in catalog if item["label"] == "Molecular subtype")

    assert gender["analysis_eligible"] is True
    assert {level["value"] for level in gender["levels"]} == {"Female", "Male"}
    assert not any(
        item["category"] == "dataset_specific" and "Sex 0" in item["source_field"]
        for item in catalog
    )
    rare = next(level for level in subtype["levels"] if level["value"] == "Rare")
    assert subtype["analysis_eligible"] is True
    assert rare["analysis_eligible"] is False
    assert "Fewer than 5 patients" in rare["unavailable_reason"]


def test_external_histology_stage_and_dotted_labels_are_canonicalized() -> None:
    samples = []
    for index in range(12):
        histology = (
            "85003_Infiltrating_duct_carcinoma"
            if index < 6
            else ("IDC" if index < 11 else "81403_Adenocarcinoma_NOS")
        )
        stage = "TNM Stage IIIA" if index < 5 else (
            "TNM Stage III A" if index == 5 else "TNM Stage II"
        )
        samples.append(
            MockSample(
                patient_id=f"P{index}",
                barcode=f"S{index}",
                stage=None,
                raw_metadata={
                    "sample": {
                        "TUMOUR_HISTOLOGICAL_TYPE": histology,
                        "ICGC_SPECIMEN_METADATA_JSON": json.dumps(
                            {"tumour_histological_type": histology}
                        ),
                    },
                    "patient": {
                        "TNM Stage": stage,
                        "GEO_SAMPLE_METADATA_JSON": json.dumps(
                            {
                                "characteristics": {
                                    "d.stage.at.diagnosis": "M0" if index < 6 else "M1",
                                    "n.stage.at.diagnosis": "N0" if index < 6 else "N1",
                                    "t.stage.at.diagnosis": "T2" if index < 6 else "T3",
                                }
                            }
                        ),
                    },
                },
            )
        )

    catalog, _ = clinical_grouping_context(
        samples,
        cohort="TCGA-BRCA",
        repository=True,
    )
    histology = [item for item in catalog if "histological type" in item["label"].casefold()]
    tnm_stage = next(item for item in catalog if item["label"] == "TNM stage")
    dotted_labels = {
        item["label"]
        for item in catalog
        if item["label"].endswith("stage at diagnosis")
    }

    assert len(histology) == 1
    assert histology[0]["levels"][0]["value"] == "Invasive ductal carcinoma (IDC)"
    assert histology[0]["levels"][0]["count"] == 11
    assert {level["value"]: level["count"] for level in tnm_stage["levels"]} == {
        "TNM Stage IIIA": 6,
        "TNM Stage II": 6,
    }
    assert dotted_labels == {
        "D stage at diagnosis",
        "N stage at diagnosis",
        "T stage at diagnosis",
    }


def test_custom_filter_accepts_longest_external_catalog_variable_id():
    from app.clinical_grouping import _external_variable_id
    from app.schemas import AnalysisFilters

    path = "patient.GEO_SAMPLE_METADATA_JSON.characteristics." + "x" * 200
    variable_id = _external_variable_id(path)
    assert len(variable_id) > 64

    filters = AnalysisFilters(
        custom_filters=[{"variable_id": variable_id, "categorical_levels": ["1"]}]
    )

    assert filters.custom_filters[0].variable_id == variable_id
