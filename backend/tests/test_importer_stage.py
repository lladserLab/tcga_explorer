import csv

from app.importer import clinical_rows_by_patient, normalize_stage


def test_normalize_stage_prefers_ajcc_and_falls_back_to_ensat():
    assert normalize_stage(
        {
            "ajcc_pathologic_stage": "Stage IIA",
            "ensat_pathologic_stage": "Stage IV",
        }
    ) == "Stage IIA"
    assert normalize_stage(
        {
            "ajcc_pathologic_stage": "",
            "ensat_pathologic_stage": "Stage III",
        }
    ) == "Stage III"


def test_clinical_rows_are_indexed_by_patient(tmp_path):
    clinical_path = tmp_path / "clinical_data.tsv"
    with clinical_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["submitter_id", "ensat_pathologic_stage"],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerow({"submitter_id": "TCGA-OR-A5JL", "ensat_pathologic_stage": "Stage I"})

    rows = clinical_rows_by_patient(tmp_path)

    assert normalize_stage(rows["TCGA-OR-A5JL"]) == "Stage I"
