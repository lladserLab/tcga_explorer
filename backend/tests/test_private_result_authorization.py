from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app import main, mcp_server
from app.models import AnalysisJob, ComputeJob
from app.user_datasets import UserDatasetError


TOKEN = "correct-private-token"


def request_with_token(token: str | None = None) -> Request:
    headers = []
    if token is not None:
        headers.append((b"x-trace-dataset-token", token.encode("utf-8")))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
        }
    )


def token_guard(_db, _dataset_id, token):
    if token != TOKEN:
        raise UserDatasetError(
            "USER_DATASET_NOT_FOUND",
            "The private dataset was not found or its access token is invalid.",
        )


class FakeSession:
    def __init__(self, values):
        self.values = values

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, model, identifier):
        return self.values.get((model, identifier))


@pytest.mark.parametrize("kind", ["json", "cohort_manifest", "source_files"])
def test_legacy_analysis_result_and_download_reauthorize_private_dataset(
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    analysis = SimpleNamespace(id="analysis-private", dataset_id="user-fixture")
    db = FakeSession({(AnalysisJob, analysis.id): analysis})
    monkeypatch.setattr(main, "_ensure_public_result_retained", lambda *_args: None)
    monkeypatch.setattr(main, "authorize_user_dataset", token_guard)
    monkeypatch.setattr(
        main,
        "analysis_out",
        lambda job: {"id": job.id, "authorized": True},
    )

    for token in (None, "wrong-token"):
        with pytest.raises(HTTPException) as result_error:
            main.get_analysis(analysis.id, request_with_token(token), db)
        assert result_error.value.status_code == 404
        assert result_error.value.detail["code"] == "USER_DATASET_NOT_FOUND"

        with pytest.raises(HTTPException) as download_error:
            main.download_analysis(
                analysis.id,
                kind,
                request_with_token(token),
                db,
            )
        assert download_error.value.status_code == 404
        assert download_error.value.detail["code"] == "USER_DATASET_NOT_FOUND"

    assert main.get_analysis(
        analysis.id,
        request_with_token(TOKEN),
        db,
    ) == {"id": analysis.id, "authorized": True}


def test_public_analysis_result_does_not_require_private_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = SimpleNamespace(id="analysis-public", dataset_id="external-study")
    db = FakeSession({(AnalysisJob, analysis.id): analysis})
    monkeypatch.setattr(main, "_ensure_public_result_retained", lambda *_args: None)
    monkeypatch.setattr(
        main,
        "authorize_user_dataset",
        lambda *_args: pytest.fail("Public results must not invoke private authorization."),
    )
    monkeypatch.setattr(main, "analysis_out", lambda job: {"id": job.id})

    assert main.get_analysis(
        analysis.id,
        request_with_token(),
        db,
    ) == {"id": analysis.id}


def test_mcp_job_poll_reauthorizes_private_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = SimpleNamespace(
        id="job-private",
        kind="analysis",
        request_payload={"dataset_id": "user-fixture"},
    )
    monkeypatch.setattr(
        mcp_server,
        "SessionLocal",
        lambda: FakeSession({(ComputeJob, job.id): job}),
    )

    def payload_guard(_db, payload, token):
        assert payload == {"dataset_id": "user-fixture"}
        token_guard(_db, "user-fixture", token)

    monkeypatch.setattr(
        mcp_server,
        "authorize_user_datasets_in_payload",
        payload_guard,
    )
    monkeypatch.setattr(
        mcp_server,
        "compute_job_out",
        lambda *_args: SimpleNamespace(
            model_dump=lambda **_kwargs: {
                "id": job.id,
                "status": "completed",
                "result": {},
            }
        ),
    )

    for token in (None, "wrong-token"):
        context_token = mcp_server._mcp_dataset_token.set(token)
        try:
            result = mcp_server.tcga_get_job(job.id)
        finally:
            mcp_server._mcp_dataset_token.reset(context_token)
        assert result["ok"] is False
        assert result["error"]["code"] == "USER_DATASET_NOT_FOUND"

    context_token = mcp_server._mcp_dataset_token.set(TOKEN)
    try:
        result = mcp_server.tcga_get_job(job.id)
    finally:
        mcp_server._mcp_dataset_token.reset(context_token)
    assert result["ok"] is True
    assert result["job"]["id"] == job.id


def test_mcp_analysis_lookup_reauthorizes_private_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = SimpleNamespace(id="analysis-private", dataset_id="user-fixture")
    monkeypatch.setattr(
        mcp_server,
        "SessionLocal",
        lambda: FakeSession({(AnalysisJob, analysis.id): analysis}),
    )
    monkeypatch.setattr(mcp_server, "authorize_user_dataset", token_guard)
    monkeypatch.setattr(main, "_ensure_public_result_retained", lambda *_args: None)
    monkeypatch.setattr(
        main,
        "analysis_out",
        lambda job: SimpleNamespace(
            model_dump=lambda **_kwargs: {"id": job.id, "status": "completed"}
        ),
    )

    for token in (None, "wrong-token"):
        context_token = mcp_server._mcp_dataset_token.set(token)
        try:
            result = mcp_server.tcga_get_analysis(analysis.id)
        finally:
            mcp_server._mcp_dataset_token.reset(context_token)
        assert result["ok"] is False
        assert result["error"]["code"] == "USER_DATASET_NOT_FOUND"

    context_token = mcp_server._mcp_dataset_token.set(TOKEN)
    try:
        result = mcp_server.tcga_get_analysis(analysis.id)
    finally:
        mcp_server._mcp_dataset_token.reset(context_token)
    assert result["ok"] is True
    assert result["analysis"]["id"] == analysis.id
