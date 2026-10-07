from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app import main


def test_public_preflight_rejects_unavailable_dataset_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = SimpleNamespace()
    monkeypatch.setattr(
        main,
        "resolve_repository_context",
        lambda *_args, **_kwargs: context,
    )
    monkeypatch.setattr(
        main,
        "require_repository_capability",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("survival is unavailable")
        ),
    )
    monkeypatch.setattr(
        main,
        "repository_capabilities",
        lambda _context, **_kwargs: {
            "expression": {"available": True},
            "expression_comparison": {"available": True},
            "gsea": {"available": True},
            "survival": {
                "available": False,
                "reason": "No eligible time-to-event endpoint is available.",
            },
        },
    )

    with pytest.raises(HTTPException) as captured:
        main._preflight_repository_capabilities(
            object(),
            kind="analysis",
            payload={
                "dataset_id": "expression-only",
                "dataset_release_id": "expression-only-r1",
            },
        )

    assert captured.value.status_code == 422
    assert captured.value.detail["code"] == "DATASET_CAPABILITY_UNAVAILABLE"
    assert captured.value.detail["details"]["requested_analysis"] == "survival"
    assert "gsea" in captured.value.detail["details"]["available_analyses"]


def test_public_preflight_explains_candidate_not_promoted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main,
        "resolve_repository_context",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("not found")
        ),
    )
    monkeypatch.setattr(
        main,
        "_candidate_record",
        lambda dataset_id: {
            "id": dataset_id,
            "status": "under_review",
            "blockers": [
                {"code": "endpoint_pending", "detail": "Time origin unresolved."}
            ],
        },
    )

    with pytest.raises(HTTPException) as captured:
        main._preflight_repository_capabilities(
            object(),
            kind="gsea",
            payload={"dataset_id": "candidate-study"},
        )

    assert captured.value.status_code == 422
    assert captured.value.detail["code"] == "DATASET_NOT_PROMOTED"
    assert captured.value.detail["details"]["status"] == "under_review"


def test_batch_preflight_checks_every_survival_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, str]] = []
    context = SimpleNamespace()
    monkeypatch.setattr(
        main,
        "resolve_repository_context",
        lambda _db, dataset_id, *_args, **_kwargs: (
            seen.append(("resolve", dataset_id)) or context
        ),
    )
    monkeypatch.setattr(
        main,
        "require_repository_capability",
        lambda _context, analysis_type, **_kwargs: seen.append(
            ("capability", analysis_type)
        ),
    )

    main._preflight_repository_capabilities(
        object(),
        kind="batch",
        payload={
            "analyses": [
                {"dataset_id": "study-a"},
                {"dataset_id": "study-b"},
            ]
        },
    )

    assert seen == [
        ("resolve", "study-a"),
        ("capability", "survival"),
        ("resolve", "study-b"),
        ("capability", "survival"),
    ]


def test_public_preflight_checks_rank_scoring_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = SimpleNamespace()
    seen: list[str] = []
    monkeypatch.setattr(
        main,
        "resolve_repository_context",
        lambda *_args, **_kwargs: context,
    )

    def require(_context, analysis_type, **_kwargs):
        seen.append(analysis_type)
        if analysis_type == "rank_based_signature_scoring":
            raise ValueError("broad expression layer required")
        return {"available": True}

    monkeypatch.setattr(main, "require_repository_capability", require)
    monkeypatch.setattr(
        main,
        "repository_capabilities",
        lambda _context, **_kwargs: {
            "survival": {"available": True},
            "rank_based_signature_scoring": {
                "available": False,
                "reason": "A broad expression layer is required.",
            },
        },
    )
    monkeypatch.setattr(main, "available_repository_modules", lambda _: ["analysis"])

    with pytest.raises(HTTPException) as captured:
        main._preflight_repository_capabilities(
            object(),
            kind="analysis",
            payload={
                "dataset_id": "targeted-upload",
                "signature_method": "singscore",
                "gene_symbol": "IFNG,GZMB",
            },
        )

    assert seen == ["survival", "rank_based_signature_scoring"]
    assert captured.value.status_code == 422
    assert (
        captured.value.detail["details"]["requested_analysis"]
        == "rank_based_signature_scoring"
    )


def test_public_preflight_uses_selected_layer_for_rank_scoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = SimpleNamespace(dataset=SimpleNamespace(visibility="public"), release=SimpleNamespace(id="release"))
    coverage = {"patient_count": 20, "endpoints": {}}
    monkeypatch.setattr(main, "resolve_expression_layer", lambda *_args: "targeted")
    monkeypatch.setattr(main, "repository_expression_layer_coverage", lambda *_args: coverage)
    seen: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        main,
        "resolve_repository_context",
        lambda *_args, **_kwargs: context,
    )

    def require(_context, analysis_type, *, expression_layer_id=None, layer_coverage=None):
        assert layer_coverage is coverage
        seen.append((analysis_type, expression_layer_id))
        if (
            analysis_type == "rank_based_signature_scoring"
            and expression_layer_id == "targeted"
        ):
            raise ValueError("The selected layer contains only 420 genes.")
        return {"available": True}

    monkeypatch.setattr(main, "require_repository_capability", require)
    monkeypatch.setattr(
        main,
        "repository_capabilities",
        lambda _context, **_kwargs: {
            "survival": {"available": True},
            "rank_based_signature_scoring": {
                "available": False,
                "reason": "The selected layer contains only 420 genes.",
                "gene_count": 420,
                "sample_count": 20,
                "matrix_entry_count": 8_400,
                "maximum_matrix_entries": 75_000_000,
                "missing_value_count": 0,
                "complete_matrix_verified": True,
            },
        },
    )
    monkeypatch.setattr(main, "available_repository_modules", lambda _: ["analysis"])

    with pytest.raises(HTTPException) as captured:
        main._preflight_repository_capabilities(
            object(),
            kind="analysis",
            payload={
                "dataset_id": "multi-layer-study",
                "expression_layer_id": "targeted",
                "signature_method": "singscore",
                "gene_symbol": "IFNG,GZMB",
            },
        )

    assert seen == [
        ("survival", "targeted"),
        ("rank_based_signature_scoring", "targeted"),
    ]
    assert captured.value.detail["message"] == (
        "The selected layer contains only 420 genes."
    )
    assert captured.value.detail["details"] == {
        "dataset_id": "multi-layer-study",
        "expression_layer_id": "targeted",
        "requested_analysis": "rank_based_signature_scoring",
        "available_analyses": ["analysis"],
        "gene_count": 420,
        "sample_count": 20,
        "matrix_entry_count": 8_400,
        "maximum_matrix_entries": 75_000_000,
        "missing_value_count": 0,
        "complete_matrix_verified": True,
    }
