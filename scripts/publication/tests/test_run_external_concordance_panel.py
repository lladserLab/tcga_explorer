from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "run_external_concordance_panel.py"
)
SPEC = importlib.util.spec_from_file_location(
    "run_external_concordance_panel",
    MODULE_PATH,
)
assert SPEC is not None
sys.path.insert(0, str(MODULE_PATH.parent))
panel = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = panel
SPEC.loader.exec_module(panel)


def test_registered_panel_contains_prespecified_supported_and_null_cases() -> None:
    assert [case.case_id for case in panel.CASES] == [
        "kirc_ca9_os_median",
        "skcm_pdcd1_os_median",
        "luad_cd274_os_median",
    ]
    roles = {case.prespecified_role for case in panel.CASES}
    assert any("supported" in role for role in roles)
    assert any("unsupported" in role for role in roles)
    assert any("discordance" in role for role in roles)


def test_sample_selection_prefers_expression_complete_primary_sample() -> None:
    case = panel.CASES[0]
    snapshot = {
        "samples": [
            {
                "sampleId": "TCGA-AA-0001-06",
                "patientId": "TCGA-AA-0001",
                "sampleType": "Metastatic",
            },
            {
                "sampleId": "TCGA-AA-0001-01",
                "patientId": "TCGA-AA-0001",
                "sampleType": "Primary Solid Tumor",
            },
        ],
        "clinical_data": [
            {
                "patientId": "TCGA-AA-0001",
                "clinicalAttributeId": "OS_MONTHS",
                "value": "12",
            },
            {
                "patientId": "TCGA-AA-0001",
                "clinicalAttributeId": "OS_STATUS",
                "value": "1:DECEASED",
            },
        ],
        "expression_data": [
            {
                "entrezGeneId": case.entrez_gene_id,
                "patientId": "TCGA-AA-0001",
                "sampleId": "TCGA-AA-0001-06",
                "value": 4.0,
            },
            {
                "entrezGeneId": case.entrez_gene_id,
                "patientId": "TCGA-AA-0001",
                "sampleId": "TCGA-AA-0001-01",
                "value": 2.0,
            },
        ],
    }
    for index in range(2, 11):
        patient = f"TCGA-AA-{index:04d}"
        sample = f"{patient}-01"
        snapshot["samples"].append(
            {
                "sampleId": sample,
                "patientId": patient,
                "sampleType": "Primary Solid Tumor",
            }
        )
        snapshot["clinical_data"].extend(
            [
                {
                    "patientId": patient,
                    "clinicalAttributeId": "OS_MONTHS",
                    "value": str(index),
                },
                {
                    "patientId": patient,
                    "clinicalAttributeId": "OS_STATUS",
                    "value": "1:DECEASED" if index <= 5 else "0:LIVING",
                },
            ]
        )
        snapshot["expression_data"].append(
            {
                "entrezGeneId": case.entrez_gene_id,
                "patientId": patient,
                "sampleId": sample,
                "value": float(index),
            }
        )

    rows, selection = panel.build_external_input(snapshot, case)

    first = next(row for row in rows if row["patient_id"] == "TCGA-AA-0001")
    assert first["sample_id"] == "TCGA-AA-0001-01"
    assert first["expression"] == 2.0
    assert selection["patients_with_multiple_eligible_samples"] == 1


def test_comparison_keeps_direction_and_support_separate(tmp_path: Path) -> None:
    case = panel.CASES[0]
    snapshot_path = tmp_path / "snapshot.json.gz"
    snapshot_path.write_bytes(b"snapshot")
    original_root = panel.ROOT
    panel.ROOT = tmp_path
    try:
        result = panel.assemble_case_result(
            case,
            snapshot={
                "accessed_date": "2026-07-25",
                "study": {"studyId": case.study_id},
                "selected_profile": {"molecularProfileId": "profile"},
                "selected_sample_list": {"sampleListId": "samples"},
            },
            snapshot_path=snapshot_path,
            selection={"rule": "test"},
            external={
                "cox": {
                    "hazard_ratio": 0.8,
                    "p_value": 0.2,
                }
            },
            trace={
                "cox": {
                    "hazard_ratio": 0.6,
                    "p_value": 0.01,
                },
                "grouped_holm_p_value": 0.04,
            },
        )
    finally:
        panel.ROOT = original_root

    assert result["comparison"]["external_direction"] == result["comparison"][
        "tcga_trace_direction"
    ]
    assert result["comparison"]["decision"] == (
        "direction_concordant_nominal_support_discordant"
    )
    assert result["comparison"]["independent_validation"] is False


def test_unsupported_effects_are_not_called_directionally_discordant(
    tmp_path: Path,
) -> None:
    case = panel.CASES[2]
    snapshot_path = tmp_path / "snapshot.json.gz"
    snapshot_path.write_bytes(b"snapshot")
    original_root = panel.ROOT
    panel.ROOT = tmp_path
    try:
        result = panel.assemble_case_result(
            case,
            snapshot={
                "accessed_date": "2026-07-25",
                "study": {"studyId": case.study_id},
                "selected_profile": {"molecularProfileId": "profile"},
                "selected_sample_list": {"sampleListId": "samples"},
            },
            snapshot_path=snapshot_path,
            selection={"rule": "test"},
            external={"cox": {"hazard_ratio": 1.08, "p_value": 0.58}},
            trace={
                "cox": {"hazard_ratio": 0.99, "p_value": 0.96},
                "grouped_holm_p_value": 1.0,
            },
        )
    finally:
        panel.ROOT = original_root

    assert result["comparison"]["decision"] == (
        "both_unsupported_point_direction_differs"
    )
