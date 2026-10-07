"""Upload validation against isolated data, including the real queue/R path."""
import csv
import io
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import main as main_module, worker
from app.database import Base, get_db
from app.jobs import claim_next_compute_job, finish_compute_job
from app.models import CancerType, RepositoryDataset
from app.repository.service import resolve_repository_context, repository_samples
from app.clinical_grouping import clinical_grouping_context
from app.schemas import ExpressionComparisonRequest, UserDatasetMapping
from app.user_datasets import create_user_dataset, UserDatasetError
from test_user_datasets import (
    _clinical_table, _database, _genes_by_rows_table, _mapping,
    _samples_by_rows_table, _seed_cancer, _settings,
)


def expression_with_value(orientation, value):
    source = (_genes_by_rows_table() if orientation == "genes_by_rows"
              else _samples_by_rows_table())
    rows = list(csv.reader(io.StringIO(source.decode())))
    rows[1][1] = value
    output = io.StringIO()
    csv.writer(output).writerows(rows)
    return output.getvalue().encode()


def upload(db, settings, *, expression=None, clinical=None, mapping=None):
    return create_user_dataset(
        db, settings,
        expression_source=io.BytesIO(expression if expression is not None else _genes_by_rows_table()),
        clinical_source=io.BytesIO(clinical if clinical is not None else _clinical_table()),
        mapping=mapping or _mapping(), owner_key_hash="isolated-upload-test",
    )


@pytest.mark.parametrize("orientation", ["genes_by_rows", "samples_by_rows"])
@pytest.mark.parametrize("value,code", [
    ("oops", "INVALID_EXPRESSION_VALUE"),
    ("2,00", "INVALID_EXPRESSION_VALUE"),
    ("Inf", "INVALID_EXPRESSION_VALUE"),
    ("-Inf", "INVALID_EXPRESSION_VALUE"),
    ("1e999", "INVALID_EXPRESSION_VALUE"),
    ("1e100", "EXPRESSION_VALUE_OUT_OF_RANGE"),
    ("1e-100", "EXPRESSION_VALUE_OUT_OF_RANGE"),
    ("-2", "NEGATIVE_EXPRESSION"),
])
def test_bad_expression_reports_location_and_leaves_no_private_data(tmp_path, orientation, value, code):
    settings = _settings(tmp_path)
    mapping = _mapping(orientation=orientation, expression_id_column=(
        "gene_symbol" if orientation == "genes_by_rows" else "sample_id"
    ))
    with _database()() as db:
        _seed_cancer(db)
        with pytest.raises(UserDatasetError) as caught:
            upload(db, settings, expression=expression_with_value(orientation, value), mapping=mapping)
        error = caught.value
        assert error.code == code
        assert error.field == "expression_file"
        assert error.details == {
            "row": 2, "column": 2,
            "column_name": "S01" if orientation == "genes_by_rows" else "TP53",
        }
        assert "row 2, column 2" in error.message
        assert db.scalars(select(RepositoryDataset)).all() == []
        assert list(settings.user_dataset_dir.iterdir()) == []


@pytest.mark.parametrize("orientation", ["genes_by_rows", "samples_by_rows"])
@pytest.mark.parametrize("value", ["", "NA", "null", "unknown"])
def test_declared_missing_expression_remains_supported(tmp_path, orientation, value):
    mapping = _mapping(orientation=orientation, expression_id_column=(
        "gene_symbol" if orientation == "genes_by_rows" else "sample_id"
    ))
    with _database()() as db:
        _seed_cancer(db)
        data = upload(db, _settings(tmp_path), expression=expression_with_value(orientation, value), mapping=mapping)
        qc = data["qc"]["expression"]
        assert qc["nonmissing_cells"] == 35
        assert qc["missing_cells"] == 1
        assert any(n["code"] == "MISSING_EXPRESSION_RETAINED" for n in data["qc"]["notices"])


def test_signed_normalized_expression_is_not_rejected(tmp_path):
    with _database()() as db:
        _seed_cancer(db)
        data = upload(db, _settings(tmp_path),
                      expression=expression_with_value("genes_by_rows", "-2.5"),
                      mapping=_mapping().model_copy(update={"expression_unit": "normalized_log2"}))
        assert data["qc"]["expression"]["analysis_min"] == -2.5
        assert data["qc"]["expression"]["missing_cells"] == 0


def test_custom_qc_and_notices_use_only_expression_matched_patients(tmp_path):
    lines = _clinical_table().decode().splitlines()
    clinical = "\n".join(
        [lines[0] + ",subtype,score"]
        + [line + ",A,1" for line in lines[1:]]
        + [f"S{i:02d},12,censored,50,Stage I,G1,B,{i}" for i in range(13, 25)]
    ).encode()
    mapping = _mapping(custom_variables=[
        dict(source_column="subtype", id="subtype", label="Subtype", value_type="categorical", timing="baseline"),
        dict(source_column="score", id="score", label="Score", value_type="numeric", timing="baseline"),
    ])
    with _database()() as db:
        _seed_cancer(db)
        data = upload(db, _settings(tmp_path), clinical=clinical, mapping=mapping)
        qc = data["qc"]
        assert qc["custom_clinical"]["summary_population"] == "expression_matched_patients"
        assert qc["custom_clinical"]["patient_count"] == 12
        subtype, score = qc["custom_clinical"]["variables"]
        assert subtype["observed_levels"] == [{"value": "A", "count": 12}]
        assert subtype["non_missing_count"] == score["non_missing_count"] == 12
        assert subtype["analysis_eligible"] is score["analysis_eligible"] is False
        assert score["min"] == score["max"] == 1
        assert qc["clinical"]["summary_population"] == "uploaded_metadata"
        assert qc["clinical"]["custom_clinical_variables"][0]["non_missing_count"] == 24
        codes = {n["code"] for n in qc["notices"]}
        assert "CUSTOM_CLINICAL_VARIABLE_INELIGIBLE:subtype" in codes
        assert "CUSTOM_CLINICAL_VARIABLE_INELIGIBLE:score" in codes
        context = resolve_repository_context(db, data["id"], data["active_release_id"], include_private=True)
        catalog, _ = clinical_grouping_context(repository_samples(db, context), cohort=data["tcga_cohort"], repository=True)
        assert next(v for v in catalog if v["id"] == "subtype")["analysis_eligible"] is False


@pytest.mark.parametrize("time,reason,notice", [
    ("0", "excluded_nonpositive_time", "NONPOSITIVE_TIMES_EXCLUDED_FROM_SURVIVAL"),
    ("-5", "excluded_nonpositive_time", "NONPOSITIVE_TIMES_EXCLUDED_FROM_SURVIVAL"),
    ("", "excluded_incomplete_outcome", "INCOMPLETE_OUTCOMES_EXCLUDED_FROM_SURVIVAL"),
    ("1e308", "excluded_incomplete_outcome", "INCOMPLETE_OUTCOMES_EXCLUDED_FROM_SURVIVAL"),
])
def test_outcome_exclusions_are_visible_and_count_only_matched_patients(tmp_path, time, reason, notice):
    clinical = _clinical_table().replace(b"S01,11,event", f"S01,{time},event".encode())
    clinical += f"S13,{time},event,50,Stage I,G1\n".encode()
    with _database()() as db:
        _seed_cancer(db)
        data = upload(db, _settings(tmp_path), clinical=clinical)
        assert data["patient_count"] == 12
        assert data["capabilities"]["expression_comparison"]["patient_count"] == 12
        assert data["capabilities"]["survival"]["patient_count"] == 11
        assert data["qc"]["clinical"][reason] == 2
        assert data["qc"]["endpoint"][reason] == 1
        text = next(n["message"] for n in data["qc"]["notices"] if n["code"] == notice)
        assert text.startswith("1 matched patient")
        assert "only from survival" in text
        assert "molecular analyses" in text


def test_template_subtypes_can_be_used_for_comparison(tmp_path):
    archive = zipfile.ZipFile(io.BytesIO(main_module.public_user_dataset_template().body))
    mapping = _mapping(custom_variables=[dict(source_column="breast_subtype", id="breast_subtype", label="Breast subtype", value_type="categorical", timing="baseline")])
    with _database()() as db:
        _seed_cancer(db)
        data = upload(db, _settings(tmp_path), expression=archive.read("expression.csv"), clinical=archive.read("clinical.csv"), mapping=mapping)
        assert data["patient_count"] == 18
        assert data["event_count"] == 9
        assert data["capabilities"]["survival"]["available"] is True
        variable = data["qc"]["custom_clinical"]["variables"][0]
        assert variable["analysis_eligible"] is True
        assert [v["count"] for v in variable["observed_levels"]] == [6, 6, 6]
        assert "not biological evidence" in archive.read("README.txt").decode()


def test_metadata_upload_through_api_queue_r_plots_and_private_deletion(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    settings.derived_expression_dir = tmp_path / "derived"
    settings.attestation_private_key_path = tmp_path / "attestation/key.pem"
    settings.attestation_public_key_dir = tmp_path / "attestation/public"
    monkeypatch.setattr(main_module, "settings", settings)
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'upload-test.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(worker, "SessionLocal", factory)
    monkeypatch.setattr(worker, "settings", settings)
    with factory() as db:
        db.add(CancerType(code="BRCA", tcga_cohort="TCGA-BRCA", name="Breast Invasive Carcinoma", primary_site="Breast", sort_order=0, coverage_status="available"))
        db.commit()

    def isolated_db():
        with factory() as db:
            yield db

    app = FastAPI()
    app.include_router(main_module.public_router)
    app.dependency_overrides[get_db] = isolated_db
    with TestClient(app) as client:
        ids = [f"S{i:02d}" for i in range(1, 37)]
        expression = "\n".join([",".join(["gene_symbol", *ids])] + [
            ",".join([gene] + [str(2 + j * .1 + (i % 6) * .13 + (i % 12 >= 6) * (1 + j)) for i in range(36)])
            for j, gene in enumerate(["ESR1", "CD68", "CD163"])
        ])
        metadata = "\n".join(["sample_id,subtype,nodal_status"] + [
            f"{sample},{['Luminal A', 'Luminal B', 'TNBC'][i // 12]},{'N0' if i % 12 < 6 else 'N+'}"
            for i, sample in enumerate(ids)
        ])
        mapping = UserDatasetMapping(
            name="Isolated breast upload", cancer_code="BRCA", expression_orientation="genes_by_rows",
            expression_id_column="gene_symbol", clinical_id_column="sample_id", has_survival_outcome=False,
            expression_unit="log2_tpm", confirm_deidentified=True,
            custom_clinical_variables=[dict(source_column=x, id=x, label=x, value_type="categorical", timing="baseline") for x in ["subtype", "nodal_status"]],
        )
        invalid = client.post("/api/v1/user-datasets", files={
            "expression_file": ("expression.csv", expression.replace("ESR1,2.0,", "ESR1,oops,", 1).encode(), "text/csv"),
            "clinical_file": ("metadata.csv", metadata.encode(), "text/csv"),
        }, data={"mapping": mapping.model_dump_json()})
        assert invalid.status_code == 422, invalid.text
        assert invalid.json()["detail"]["code"] == "INVALID_EXPRESSION_VALUE"
        assert invalid.json()["detail"]["details"]["row"] == 2
        assert list(settings.user_dataset_dir.iterdir()) == []
        response = client.post("/api/v1/user-datasets", files={
            "expression_file": ("expression.csv", expression.encode(), "text/csv"),
            "clinical_file": ("metadata.csv", metadata.encode(), "text/csv"),
        }, data={"mapping": mapping.model_dump_json()})
        assert response.status_code == 201, response.text
        data = response.json()
        prefix = "/api/v1/user-datasets/" + data["id"]
        headers = {"X-TRACE-Dataset-Token": data["access_token"]}
        assert client.get(prefix).status_code == 404
        assert client.get(prefix, headers=headers).status_code == 200
        request = ExpressionComparisonRequest(
            cohort="TCGA-BRCA", dataset_id=data["id"], dataset_release_id=data["active_release_id"],
            expression_layer_id=data["expression_layer"]["value"], genes=["CD68", "CD163"],
            filters={"custom_filters": [{"variable_id": "subtype", "categorical_levels": ["Luminal A"]}]},
            grouping=dict(source="clinical", clinical_variable="nodal_status", group_a_label="N0", group_b_label="N+", group_a_values=["N0"], group_b_values=["N+"]),
        )
        submitted = client.post("/api/v1/analyses/expression-comparisons", json=request.model_dump(mode="json"), headers=headers)
        assert submitted.status_code == 202, submitted.text
        assert client.delete(prefix, headers=headers).status_code == 409
        with factory() as db:
            job = claim_next_compute_job(db)
        result, result_id = worker._execute_job(job)
        with factory() as db:
            assert finish_compute_job(job.id, result=result, result_id=result_id, db=db, attempt_token=job.attempt_token, settings=settings) is not None
        assert result["grouping"]["group_counts"] == {"N0": 6, "N+": 6}
        assert result["summary"]["genes_analyzed"] == 2
        assert result["statistics"][0]["mean_difference_b_minus_a"] == pytest.approx(2)
        for kind in ["violin_svg", "boxplot_svg", "heatmap_svg", "statistics_csv"]:
            url = f"/api/v1/analyses/expression-comparisons/{result_id}/download/{kind}"
            assert client.get(url).status_code == 404
            assert client.get(url, headers=headers).status_code == 200
        assert client.delete(prefix, headers=headers).status_code == 200
        assert not (settings.user_dataset_dir / data["id"]).exists()
        assert not (settings.artifact_dir / "expression_comparisons" / result_id).exists()
        assert client.get(prefix, headers=headers).status_code == 404
    engine.dispose()
