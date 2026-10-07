import csv
import json
from types import SimpleNamespace

from app.analysis_report import render_cohort_section, selection_manifest, write_audit_tables
from app.schemas import AnalysisFilters
from app.survival import filter_sample_candidates, select_expression_complete_samples
from app.provenance import analysis_data_provenance, selected_gdc_identifiers


def sample(patient, barcode, **kwargs):
    return SimpleNamespace(patient_id=patient, barcode=barcode, cohort="TCGA-TEST",
                           sample_type=kwargs.get("sample_type", "Primary Tumor"),
                           stage=kwargs.get("stage", "Stage I"), grade=None, gender=None,
                           race=None, age_at_index=50, os_time_days=kwargs.get("time", 100),
                           os_event=1)


def test_selection_ledger_reconciles_samples_patients_and_grouping(tmp_path):
    samples = [
        sample("P1", "S1"), sample("P1", "S2"),
        sample("P2", "S3", stage="Stage II"),
        sample("P3", "S4", time=None),
        sample("P4", "S5"), sample("P5", "S6"),
        sample("P1", "S7", sample_type="Solid Tissue Normal"),
    ]
    candidates, warnings, summary = filter_sample_candidates(samples, AnalysisFilters(stages=["Stage I"]))
    original = json.dumps(summary, sort_keys=True)
    retained, _, final = select_expression_complete_samples(
        candidates, {"S1", "S2", "S6"}, summary=summary, warnings=warnings,
    )
    assert json.dumps(summary, sort_keys=True) == original
    assert {s.barcode for s in retained} == {"S1", "S6"}
    audit = final["selection_audit"]
    stages = audit["stages"]
    assert sum(s["removed_samples"] for s in stages) + len(retained) == 7
    assert sum(s["removed_patients"] for s in stages) + len(retained) == 5
    by_barcode = {row["sample_barcode"]: row for row in audit["records"]}
    assert by_barcode["S2"]["excluded_at"] == "one_sample_per_patient"
    assert by_barcode["S2"]["patient_retained"] is True
    assert by_barcode["S7"]["excluded_at"] == "molecular_population"
    assert by_barcode["S7"]["patient_retained"] is True
    assert by_barcode["S3"]["excluded_at"] == "filter_stage"
    assert by_barcode["S4"]["excluded_at"] == "endpoint_completeness"
    assert by_barcode["S5"]["excluded_at"] == "expression_completeness"
    manifest = selection_manifest(final, [{"sample_barcode": "S1", "group": "High"}],
                                  [{"sample_barcode": s.barcode} for s in retained])
    s6 = next(r for r in manifest if r["sample_barcode"] == "S6")
    assert s6["in_continuous_input"] is True
    assert s6["in_grouped_analysis"] is False
    assert s6["grouping_exclusion"] == "not_assigned_to_a_retained_group"
    paths = write_audit_tables(tmp_path, manifest, {})
    with open(paths["cohort_manifest"]) as handle:
        assert len(list(csv.DictReader(handle))) == 7
    assert "source_files" not in paths


def test_gdc_file_id_is_directory_uuid_not_filename_prefix(tmp_path):
    path = tmp_path / "map.json"
    file_id = "931442ba-af81-4b68-beca-7285fc44b1df"
    filename_id = "f2dda955-5a39-43c1-93a2-83953b2b91d1"
    path.write_text(json.dumps({"barcode_to_file": {"S1": f"/cache/{file_id}/{filename_id}.rna_seq.tsv", "S2": "unverifiable.tsv"}}))
    rows = selected_gdc_identifiers(path, {"S1", "S2"})
    assert rows[0]["gdc_file_uuid"] == file_id
    assert rows[0]["gdc_filename_prefix"] == filename_id
    assert rows[1]["gdc_file_uuid"] is None


def test_metadata_checksum_cannot_stand_in_for_missing_expression_matrix(tmp_path):
    matrix_dir = tmp_path / "derived/matrices/TCGA-TEST"
    matrix_dir.mkdir(parents=True)
    (matrix_dir / "metadata.json").write_text('{"status":"ready"}')
    settings = SimpleNamespace(tcga_data_dir=tmp_path, derived_expression_dir=tmp_path / "derived",
                               tcga_cdr_path=tmp_path / "cdr.xlsx", tcga_sync_state_dir=tmp_path / "sync",
                               publication_benchmark_dir=tmp_path / "publication")
    for scale in ("log2_tpm", "log2_cpm"):
        result = analysis_data_provenance(settings, cohort="TCGA-TEST", expression_scale=scale, selected_barcodes={"S1"})
        assert result["provenance_completeness"]["exact_expression_artifact_hashed"] is False
        assert result["provenance_completeness"]["selected_gdc_identifiers_recorded"] is False
        assert result["source_metadata"]["data_release"] is None


def test_legacy_report_does_not_invent_exclusion_records():
    output = render_cohort_section({"cohort_selection": {"sample_selection": {"input_samples": 123}}})
    assert "Step-level records were not captured" in output
    assert "first 0" not in output


def test_report_escapes_user_identifiers():
    output = render_cohort_section({"cohort_selection": {"selection_manifest": [
        {"patient_id": "<script>alert(1)</script>", "sample_barcode": "S1"}
    ]}})
    assert "<script>" not in output
    assert "&lt;script&gt;" in output


def test_bundle_keeps_legacy_compatibility_and_includes_new_manifests(tmp_path, monkeypatch):
    import io
    import zipfile
    from app import main

    monkeypatch.setattr(main.settings, "artifact_dir", tmp_path)
    directory = tmp_path / "example"
    directory.mkdir()
    required = ["plot.png", "plot.svg", "raw_data.csv", "metrics.json", "methodology.txt",
                "audit_report.json", "audit_report.html", "attestation_receipt.json", "input.json",
                "rerun_analysis.R", "clinical_covariates.R", "cox_diagnostics.R", "renv.lock",
                "Dockerfile.reproduce", "REPRODUCE.md", "reproduction_manifest.json",
                "km_analysis.R", "competing_risks.R"]
    for filename in required:
        (directory / filename).write_text("fixture")
    monkeypatch.setattr(main, "ensure_svg_artifact", lambda *_: directory / "plot.svg")
    job = SimpleNamespace(id="example", status="completed", cutpoint_method="median",
                          png_path=str(directory / "plot.png"), svg_path=str(directory / "plot.svg"),
                          csv_path=str(directory / "raw_data.csv"), json_path=str(directory / "metrics.json"))
    legacy = main.analysis_zip_response(job, None)
    with zipfile.ZipFile(io.BytesIO(legacy.body)) as archive:
        assert "cohort_manifest.csv" not in archive.namelist()
    for name in ("cohort_manifest.csv", "source_files.csv"):
        (directory / name).write_text("sample_barcode\nS1\n")
    current = main.analysis_zip_response(job, None)
    with zipfile.ZipFile(io.BytesIO(current.body)) as archive:
        assert archive.read("cohort_manifest.csv") == b"sample_barcode\nS1\n"
        assert "source_files.csv" in archive.namelist()
