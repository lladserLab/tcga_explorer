import math

import pytest

from app.grouped_inference import batch_grouped_family, grouped_inference, valid_p
from app.multiverse import _grouped_inference as robustness_inference
from app.session_history import _grouped_inference as session_inference
from app.pipeline_versions import compute_cache_context
from app.schemas import AnalysisBatchOut


def test_maxstat_is_selection_corrected_before_between_test_correction():
    metrics = {"logrank_p_value": 0.001, "cutpoint_details": {
        "method": "maxstat", "corrected_p_status": "completed", "corrected_p_value": 0.3}}
    assert grouped_inference(metrics) == robustness_inference(metrics) == session_inference(metrics) == (0.3, "maxstat_lau94_corrected")
    items = [
        {"index": 0, "status": "completed", "result": {"metrics": metrics}},
        {"index": 1, "status": "completed", "result": {"metrics": {"logrank_p_value": 0.02}}},
        {"index": 2, "status": "failed"},
        {"index": 3, "status": "completed", "result": {"metrics": {"logrank_p_value": 0.0001}}},
    ]
    family = batch_grouped_family(items, ["maxstat", "median", "median", "maxstat"])
    assert (family["requested"], family["completed"], family["failed"], family["evaluable"], family["unavailable"]) == (4, 3, 1, 2, 2)
    assert family["tests"][0]["bh_q_value"] == 0.3
    assert family["tests"][0]["bonferroni_p_value"] == 0.6
    assert family["tests"][1]["bh_q_value"] == 0.04
    assert family["tests"][3]["p_value"] is None
    assert family["tests"][3]["bh_q_value"] is None
    assert AnalysisBatchOut(total=4, completed=3, failed=1, max_concurrency=1, results=[], grouped_family=family).model_dump()["grouped_family"] == family


@pytest.mark.parametrize("value", [None, True, False, "bad", math.nan, math.inf, -0.01, 1.01])
def test_invalid_p_is_not_inference(value):
    assert valid_p(value) is None


@pytest.mark.parametrize("status", [None, "failed", "skipped"])
def test_missing_maxstat_correction_never_falls_back(status):
    metrics = {"logrank_p_value": 0.001, "cutpoint_details": {"corrected_p_value": 0.3, "corrected_p_status": status}}
    assert grouped_inference(metrics, "maxstat") == (None, "maxstat_corrected_unavailable")


def test_zero_one_ties_and_unordered_items():
    items = [{"index": index, "status": "completed", "result": {"metrics": {"logrank_p_value": p}}}
             for index, p in [(2, 1), (0, 0), (1, 0)]]
    family = batch_grouped_family(items, ["median"] * 3)
    assert [row["bh_q_value"] for row in family["tests"]] == [1, 0, 0]
    assert batch_grouped_family([{"index": 0, "status": "failed"}], ["maxstat"])["evaluable"] == 0


def test_old_batch_cache_cannot_hide_the_new_family():
    assert compute_cache_context("batch")["grouped_family_contract"] == "compare-grouped-family-v1"
    assert "grouped_family_contract" not in compute_cache_context("analysis")


def test_batch_engine_and_mcp_keep_identical_family_without_running_models(monkeypatch):
    from contextlib import nullcontext
    from fastapi import HTTPException
    import app.main as main
    from app.mcp_server import _compact_result
    from app.schemas import AnalysisBatchRequest, AnalysisOut, AnalysisRequest

    def fake_analysis(request, _db):
        if request.gene_symbol == "MISSING":
            raise HTTPException(status_code=422, detail="Gene unavailable")
        return AnalysisOut(id=request.gene_symbol, status="completed", cohort=request.cohort,
            gene_symbol=request.gene_symbol, cutpoint_method=request.cutpoint_method,
            metrics={"logrank_p_value": 0.001, "cutpoint_details": {
                "method": request.cutpoint_method, "corrected_p_status": "completed", "corrected_p_value": 0.3}})

    monkeypatch.setattr(main, "SessionLocal", nullcontext)
    monkeypatch.setattr(main, "_create_analysis", fake_analysis)
    request = AnalysisBatchRequest(analyses=[AnalysisRequest(
        cohort="TCGA-KIRC", gene_symbol=gene, cutpoint_method=method,
        filters={"sample_population": "primary_solid"},
    ) for gene, method in [("CA9", "maxstat"), ("TP53", "median"), ("MISSING", "median")]])
    result = main._create_analysis_batch(request).model_dump(mode="json")
    assert result["completed"] == 2
    assert result["failed"] == 1
    assert result["grouped_family"]["tests"][0]["bh_q_value"] == 0.3
    assert _compact_result("batch", result)["grouped_family"] == result["grouped_family"]
