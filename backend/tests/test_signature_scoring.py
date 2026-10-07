import json
import math
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app import main, signature_scoring
from app.gsea import ExpressionMatrix, MatrixGene
from app.repository.storage import write_float32le_matrix
from app.schemas import (
    AnalysisFilters,
    AnalysisRequest,
    PanCancerSurvivalRequest,
    SignatureGene,
    SignatureSpec,
)
from app.signature_scoring import (
    EXPECTED_PACKAGE_VERSIONS,
    aucell_sample_seed,
    r_binary_endian,
    run_rank_based_signature_score,
    signature_method_label,
    SignatureScoringTimeout,
)


@pytest.mark.parametrize("sample_type,suffix", [
    ("Primary Tumor", "T"), ("Solid Tissue Normal", "N"),
])
def test_external_rank_population_filters_specimens_before_dedup(
    monkeypatch, sample_type, suffix,
):
    rows = [SimpleNamespace(
        barcode=f"P{i}-{kind}", patient_id=f"P{i}", cohort="FU-GBC",
        sample_type=label, sample_type_id=code, is_ffpe=False,
    ) for i in range(12) for kind, label, code in [
        ("T", "Primary Tumor", "01"), ("N", "Solid Tissue Normal", "11"),
    ]]
    monkeypatch.setattr(main, "dataset_samples", lambda *args, **kwargs: rows)
    request = AnalysisRequest(
        cohort="FU-GBC", gene_symbol="TP53", filters=AnalysisFilters(
            sample_types=[sample_type], stages=["Stage IV"], age_min=80,
        ),
    )
    matrix = SimpleNamespace(sample_ids=[row.barcode for row in rows])
    selected, summary, _ = main.canonical_signature_scoring_population(
        None, request, matrix, SimpleNamespace(),
    )
    assert selected == [f"P{i}-{suffix}" for i in range(12)]
    assert summary["declared_sample_types"] == [sample_type]
    assert summary["analysis_filters_applied"] is False


@pytest.mark.parametrize("method", ["singscore", "ssgsea", "aucell"])
def test_rank_timeout_cleans_inputs_and_has_actionable_job_error(tmp_path, monkeypatch, method):
    from app.worker import _failure_payload

    matrix = _rank_matrix(tmp_path, ["S1", "S2", "S3"])
    def timeout(command, **kwargs):
        payload = json.loads(Path(command[2]).read_text())
        Path(payload["output_path"]).write_text("partial output")
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])
    monkeypatch.setattr("app.signature_scoring.subprocess.run", timeout)
    with pytest.raises(SignatureScoringTimeout) as error:
        run_rank_based_signature_score(
            matrix=matrix, canonical_sample_ids=matrix.sample_ids,
            entries=[{"gene_symbol": gene, "resolved_symbol": gene, "weight": 1.0}
                     for gene in ["G0001", "G0002"]],
            method=method, cache_root=tmp_path / "cache",
            dataset_identity={"dataset_id": "test", "release_id": "v1"},
        )
    assert not list((tmp_path / "cache").rglob("*.input.json"))
    assert not list((tmp_path / "cache").rglob("*.output.json"))
    code, message, detail = _failure_payload(error.value)
    assert code == "SIGNATURE_SCORING_TIMEOUT"
    assert "Clinical filters alone" in message
    assert detail == {"timeout_seconds": 900}


def test_r_binary_endian_translates_native_and_rejects_unknown_values() -> None:
    assert r_binary_endian("little") == "little"
    assert r_binary_endian("big") == "big"
    assert r_binary_endian("native") in {"little", "big"}
    with pytest.raises(ValueError, match="Unsupported expression matrix byte order"):
        r_binary_endian("network")


@pytest.mark.parametrize(
    ("method", "label"),
    [
        ("singscore", "singscore"),
        ("ssgsea", "ssGSEA"),
        ("aucell", "AUCell"),
        ("zscore", "Z-score"),
    ],
)
def test_signature_method_labels_preserve_canonical_casing(
    method: str,
    label: str,
) -> None:
    assert signature_method_label(method) == label


def test_compact_pancancer_scoring_contract_is_cohort_specific_and_value_free() -> None:
    contract = main.compact_cohort_signature_scoring(
        cohort="TCGA-KIRC",
        signature={
            "method": "ssgsea",
            "label": "ssGSEA(CA9+VEGFA)",
            "genes": [
                {"query": "CA9", "resolved_symbol": "CA9"},
                {"query": "VEGFA", "resolved_symbol": "VEGFA"},
            ],
        },
        provenance={
            "schema_version": "trace-signature-scoring-v2",
            "contract_version": "contract-v1",
            "parameters": {"alpha": 0.25},
            "gene_universe": {"gene_count": 18000, "sha256": "universe"},
            "engine": {"package": "GSVA", "version": "2.0.7"},
            "coverage": {"requested_n": 2, "unique_resolved_n": 2},
            "scoring_population": {
                "timing": "before endpoint and clinical filters",
                "canonical_barcode_count": 531,
                "canonical_barcodes_sha256": "population",
                "canonical_selection": {"patient_ids": ["must-not-leak"]},
            },
            "cache": {"key_sha256": "cache"},
            "canonical_score_values_sha256": "canonical-scores",
            "score_values_sha256": "returned-scores",
            "score_values": [{"sample_barcode": "must-not-leak", "score": 1.0}],
        },
    )

    assert contract["cohort"] == "TCGA-KIRC"
    assert contract["label"] == "ssGSEA(CA9+VEGFA)"
    assert contract["hashes"]["canonical_scores_sha256"] == "canonical-scores"
    assert "canonical_selection" not in contract["scoring_population"]
    assert "score_values" not in contract


def test_compact_pancancer_zscore_contract_keeps_cohort_standardization() -> None:
    contract = main.compact_cohort_signature_scoring(
        cohort="TCGA-BRCA",
        signature={
            "method": "zscore",
            "label": "Z-score(ESR1+PGR)",
            "genes": [{"query": "ESR1"}, {"query": "PGR"}],
            "standardization": [
                {"resolved_symbol": "ESR1", "center": 4.2, "sample_standard_deviation": 1.1},
                {"resolved_symbol": "PGR", "center": 3.1, "sample_standard_deviation": 1.4},
            ],
            "scoring_population": {
                "eligible_barcode_count": 500,
                "complete_case_barcode_count": 492,
                "score_values_sha256": "scores-brca",
            },
        },
        provenance={
            "schema_version": "tcga-trace-scoring-provenance-v2",
            "method": "zscore",
            "weight_denominator": 2.0,
            "coverage": {"requested_n": 2, "unique_resolved_n": 2},
            "components": [
                {
                    "query": "ESR1",
                    "resolved_symbol": "ESR1",
                    "selected_value_count": 492,
                    "selected_values_sha256": "esr1-values",
                }
            ],
            "score_values_sha256": "scores-brca",
            "score_values": [{"sample_barcode": "must-not-leak", "score": 0.1}],
        },
    )

    assert contract["scoring_population"]["complete_case_barcode_count"] == 492
    assert contract["scoring_parameters"]["weight_denominator"] == 2.0
    assert contract["scoring_parameters"]["gene_standardization"][0]["center"] == 4.2
    assert contract["component_contracts"][0]["selected_values_sha256"] == "esr1-values"
    assert "score_values" not in contract


@pytest.mark.parametrize(
    "method",
    ["mean", "zscore", "weighted", "singscore", "ssgsea", "aucell"],
)
def test_pancancer_signature_summary_is_request_level_not_first_cohort(
    method: str,
) -> None:
    if method in {"singscore", "ssgsea", "aucell"}:
        genes = [
            SignatureGene(gene_symbol="IFNG", direction="up"),
            SignatureGene(gene_symbol="GZMB", direction="up"),
            SignatureGene(gene_symbol="IL10", direction="down"),
            SignatureGene(gene_symbol="TGFB1", direction="down"),
        ]
    elif method == "mean":
        genes = [
            SignatureGene(gene_symbol="IFNG"),
            SignatureGene(gene_symbol="GZMB"),
            SignatureGene(gene_symbol="IL10"),
            SignatureGene(gene_symbol="TGFB1"),
        ]
    else:
        genes = [
            SignatureGene(gene_symbol="IFNG", weight=1),
            SignatureGene(gene_symbol="GZMB", weight=1),
            SignatureGene(gene_symbol="IL10", weight=-1),
            SignatureGene(gene_symbol="TGFB1", weight=-1),
        ]
    request = PanCancerSurvivalRequest(
        gene_symbol="IFNG, GZMB, IL10, TGFB1",
        signature_method=method,
        signature_genes=genes,
    )

    summary = main.pancancer_signature_request_definition(request)

    assert summary["scope"] == "request_definition"
    assert summary["label"].startswith(
        {
            "mean": "Mean(",
            "zscore": "Z-score(",
            "weighted": "Weighted(",
            "singscore": "singscore(",
            "ssgsea": "ssGSEA(",
            "aucell": "AUCell(",
        }[method]
    )
    assert summary["cohort_specific_scoring"] is True
    assert "engine" not in summary
    assert "gene_universe" not in summary


@pytest.mark.parametrize(
    "method",
    ["mean", "zscore", "weighted", "singscore", "ssgsea", "aucell"],
)
def test_pancancer_multigene_scan_never_promotes_first_cohort_contract(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
) -> None:
    cohorts = [
        SimpleNamespace(id="TCGA-A", disease_type="A", primary_site="A"),
        SimpleNamespace(id="TCGA-B", disease_type="B", primary_site="B"),
    ]
    sample = SimpleNamespace(barcode="S1")

    class FakeScalars:
        def all(self):
            return [sample]

    class FakeDb:
        def scalars(self, _query):
            return FakeScalars()

    def fake_expression(_db, analysis_request, **_kwargs):
        cohort = analysis_request.cohort
        signature = {
            "method": method,
            "label": f"{cohort}-contract",
            "genes": [{"gene_symbol": "IFNG"}, {"gene_symbol": "GZMB"}],
        }
        provenance = {
            "method": method,
            "coverage": {"requested_n": 2, "unique_resolved_n": 2},
            "engine": {"package": cohort, "version": "test"},
            "gene_universe": {"gene_count": 1000, "sha256": cohort},
            "scoring_population": {"canonical_barcode_count": 1},
        }
        return {"S1": 1.0}, signature, [], provenance

    monkeypatch.setattr(main, "pancancer_cohorts", lambda *_args: cohorts)
    monkeypatch.setattr(
        main,
        "choose_pancancer_endpoint",
        lambda *_args: {"value": "OS", "label": "Overall survival", "source": "test"},
    )
    monkeypatch.setattr(
        main,
        "selected_endpoint_outcomes",
        lambda *_args: (
            {},
            {"value": "OS", "label": "Overall survival", "source": "test"},
        ),
    )
    monkeypatch.setattr(main, "filter_sample_candidates", lambda samples, *_args, **_kwargs: (samples, [], {}))
    monkeypatch.setattr(main, "select_expression_complete_samples", lambda samples, *_args, **_kwargs: (samples, [], {}))
    monkeypatch.setattr(main, "expression_for_request", fake_expression)
    monkeypatch.setattr(main, "pancancer_continuous_records", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main,
        "run_r_pancancer_cox",
        lambda **kwargs: {
            "results": [
                {"cohort": item["cohort"], "status": "completed", "warnings": []}
                for item in kwargs["cohorts"]
            ]
        },
    )
    monkeypatch.setattr(main, "apply_pancancer_postprocessing", lambda rows, _request: rows)
    monkeypatch.setattr(main, "pancancer_effect_scale_policy", lambda _request: ({}, False, "test"))
    monkeypatch.setattr(main, "attach_effect_scale_metadata", lambda rows, *_args: rows)
    monkeypatch.setattr(main, "add_clinical_sensitivity", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(main, "add_concordance_labels", lambda *_args: None)
    monkeypatch.setattr(main, "summarize_pancancer_results", lambda *_args: {})
    monkeypatch.setattr(main, "write_pancancer_artifacts", lambda **_kwargs: {})

    signature_genes = (
        [
            SignatureGene(gene_symbol="IFNG", direction="up"),
            SignatureGene(gene_symbol="GZMB", direction="up"),
        ]
        if method in {"singscore", "ssgsea", "aucell"}
        else [
            SignatureGene(gene_symbol="IFNG", weight=1),
            SignatureGene(gene_symbol="GZMB", weight=1),
        ]
    )
    request = PanCancerSurvivalRequest(
        gene_symbol="IFNG, GZMB",
        signature_method=method,
        signature_genes=signature_genes,
    )
    result = main.run_pancancer_survival_scan(
        request,
        FakeDb(),
        "pc-test",
        request.model_dump(mode="json"),
    )

    assert result["signature"]["scope"] == "request_definition"
    assert "engine" not in result["signature"]
    assert result["signature_scoring_scope"]["cohort_contracts"] == 2
    assert [row["signature_scoring"]["engine"]["package"] for row in result["results"]] == [
        "TCGA-A",
        "TCGA-B",
    ]


def _rank_matrix(tmp_path: Path, sample_ids: list[str]) -> ExpressionMatrix:
    genes = [MatrixGene(symbol=f"G{index:04d}", row_number=index) for index in range(1000)]
    matrix_path = tmp_path / "expression.float32le.bin"
    write_float32le_matrix(
        matrix_path,
        [
            [
                float(((gene_index + 3) * 17 + (sample_index + 5) * 31) % 997)
                + sample_index / 10_000
                for sample_index, _ in enumerate(sample_ids)
            ]
            for gene_index in range(1000)
        ],
    )
    return ExpressionMatrix(
        path=matrix_path,
        sample_ids=sample_ids,
        genes=genes,
        dtype="float32",
        byte_order="little",
        expression_scale="normalized_continuous",
        expression_scale_label="Normalized expression",
        source_sha256=None,
    )


@pytest.mark.parametrize("method", ["singscore", "ssgsea", "aucell"])
@pytest.mark.parametrize("invalid", ["missing", "duplicate", "nonnumeric", "shape"])
def test_invalid_engine_result_is_never_cached_and_retry_recovers(tmp_path, monkeypatch, method, invalid):
    matrix = _rank_matrix(tmp_path, ["S1", "S2", "S3"])
    calls = []

    def fake_run(command, **kwargs):
        calls.append(True)
        source = json.loads(Path(command[2]).read_text())
        payload = {
            "schema_version": signature_scoring.SIGNATURE_SCORING_ENGINE_SCHEMA,
            "method": method, "package": signature_scoring.ENGINE_PACKAGES[method],
            "package_version": EXPECTED_PACKAGE_VERSIONS[method], "r_version": "4.4.2",
            "constant_signature_genes": [],
            "scores": [{"sample_id": sid, "score": 0.1, "up_score": 0.1, "down_score": 0.0}
                       for sid in source["sample_ids"]],
        }
        if len(calls) == 1:
            if invalid == "missing":
                payload["scores"].pop()
            elif invalid == "duplicate":
                payload["scores"].append(payload["scores"][0])
            elif invalid == "nonnumeric":
                payload["scores"][0]["score"] = None
            else:
                payload = []
        Path(source["output_path"]).write_text(json.dumps(payload))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(signature_scoring.subprocess, "run", fake_run)
    args = dict(matrix=matrix, canonical_sample_ids=matrix.sample_ids,
        entries=[{"gene_symbol": g, "resolved_symbol": g, "weight": 1.0} for g in ["G0001", "G0002"]],
        method=method, cache_root=tmp_path / "cache", dataset_identity={"dataset_id": "fixture"})
    with pytest.raises(RuntimeError):
        run_rank_based_signature_score(**args)
    assert not list((tmp_path / "cache").rglob("*.json"))
    assert not list((tmp_path / "cache").rglob("*.tmp"))
    scores, provenance, _ = run_rank_based_signature_score(**args)
    assert set(scores) == set(matrix.sample_ids)
    assert len(calls) == 2

    # Existing corrupt caches are also discarded, not returned or retried forever.
    [cached] = list((tmp_path / "cache").rglob("*.json"))
    payload = json.loads(cached.read_text())
    payload["scores"].pop()
    cached.write_text(json.dumps(payload))
    recovered, recovered_provenance, _ = run_rank_based_signature_score(**args)
    assert len(calls) == 3
    assert recovered == scores
    assert recovered_provenance == provenance


def _planted_rank_matrix(
    tmp_path: Path,
    sample_ids: list[str],
    *,
    exact_tie_sample: str | None = None,
) -> ExpressionMatrix:
    genes = [
        MatrixGene(symbol=f"G{index:04d}", row_number=index)
        for index in range(1000)
    ]
    matrix_path = tmp_path / "expression.float32le.bin"

    def value(gene_index: int, sample_id: str) -> float:
        if sample_id == exact_tie_sample:
            return 0.0
        baseline = float(100 + gene_index)
        if sample_id == "HIGH":
            if gene_index in {1, 2}:
                return 5000.0
            if gene_index in {3, 4}:
                return -5000.0
        if sample_id == "LOW":
            if gene_index in {1, 2}:
                return -5000.0
            if gene_index in {3, 4}:
                return 5000.0
        return baseline

    write_float32le_matrix(
        matrix_path,
        [
            [value(gene_index, sample_id) for sample_id in sample_ids]
            for gene_index in range(1000)
        ],
    )
    return ExpressionMatrix(
        path=matrix_path,
        sample_ids=sample_ids,
        genes=genes,
        dtype="float32",
        byte_order="little",
        expression_scale="normalized_continuous",
        expression_scale_label="Normalized expression",
        source_sha256=None,
    )


def _exact_bioc_packages_available() -> bool:
    if shutil.which("Rscript") is None:
        return False
    expression = ";".join(
        f"stopifnot(requireNamespace('{package}', quietly=TRUE), "
        f"as.character(packageVersion('{package}')) == '{version}')"
        for method, version in EXPECTED_PACKAGE_VERSIONS.items()
        for package in [
            {"singscore": "singscore", "ssgsea": "GSVA", "aucell": "AUCell"}[method]
        ]
    )
    return subprocess.run(
        ["Rscript", "-e", expression],
        check=False,
        capture_output=True,
        text=True,
    ).returncode == 0


def test_zscore_uses_only_eligible_complete_case_barcodes(monkeypatch) -> None:
    eligible = {f"S{index}" for index in range(1, 11)}
    values = {
        "GENEA": {
            **{f"S{index}": float(index) for index in range(1, 11)},
            "EXCLUDED": 1000.0,
        },
        "GENEB": {
            **{f"S{index}": float(index + 3) for index in range(1, 11)},
            "EXCLUDED": -1000.0,
        },
    }

    monkeypatch.setattr(
        main,
        "resolve_gene_symbol",
        lambda _db, _data_dir, _cohort, symbol: {
            "resolved": symbol,
            "status": "exact",
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        main,
        "get_expression_for_gene",
        lambda _db, _data_dir, _derived_dir, _cohort, symbol, _scale: values[symbol],
    )
    request = AnalysisRequest(
        cohort="TCGA-TEST",
        gene_symbol="GENEA,GENEB",
        signature_method="zscore",
        signature_genes=[
            SignatureGene(gene_symbol="GENEA", weight=1.0),
            SignatureGene(gene_symbol="GENEB", weight=1.0),
        ],
    )

    expression, signature, warnings, provenance = main.expression_for_request(
        object(),
        request,
        eligible_barcodes=eligible,
    )

    assert warnings == []
    assert set(expression) == eligible
    assert sum(expression.values()) == pytest.approx(0.0)
    assert signature["scoring_population"]["eligible_barcode_count"] == 10
    assert signature["scoring_population"]["complete_case_barcode_count"] == 10
    assert [item["center"] for item in signature["standardization"]] == [5.5, 8.5]
    assert all(item["n"] == 10 for item in signature["standardization"])
    assert all(
        component["selected_value_count"] == 10
        for component in provenance["components"]
    )


def test_zscore_is_cohort_dependent(monkeypatch) -> None:
    values = {
        "GENEA": {**{f"S{index}": float(index) for index in range(1, 11)}, "OUT": 1000.0},
        "GENEB": {**{f"S{index}": float(index * 2) for index in range(1, 11)}, "OUT": -500.0},
    }
    monkeypatch.setattr(
        main,
        "resolve_gene_symbol",
        lambda _db, _data_dir, _cohort, symbol: {
            "resolved": symbol,
            "status": "exact",
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        main,
        "get_expression_for_gene",
        lambda _db, _data_dir, _derived_dir, _cohort, symbol, _scale: values[symbol],
    )
    request = AnalysisRequest(
        cohort="TCGA-TEST",
        gene_symbol="GENEA,GENEB",
        signature_method="zscore",
        signature_genes=[
            SignatureGene(gene_symbol="GENEA"),
            SignatureGene(gene_symbol="GENEB"),
        ],
    )
    base, *_ = main.expression_for_request(
        object(), request, eligible_barcodes={f"S{index}" for index in range(1, 11)}
    )
    expanded, *_ = main.expression_for_request(
        object(),
        request,
        eligible_barcodes={f"S{index}" for index in range(1, 11)} | {"OUT"},
    )
    assert expanded["S1"] != pytest.approx(base["S1"])


def test_zscore_reports_constant_components(monkeypatch) -> None:
    eligible = {f"S{index}" for index in range(1, 11)}
    values = {
        "CONSTANT": {sample_id: 7.0 for sample_id in eligible},
        "VARIABLE": {
            f"S{index}": float(index) for index in range(1, 11)
        },
    }
    monkeypatch.setattr(
        main,
        "resolve_gene_symbol",
        lambda _db, _data_dir, _cohort, symbol: {
            "resolved": symbol,
            "status": "exact",
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        main,
        "get_expression_for_gene",
        lambda _db, _data_dir, _derived_dir, _cohort, symbol, _scale: values[symbol],
    )
    request = AnalysisRequest(
        cohort="TCGA-TEST",
        gene_symbol="CONSTANT,VARIABLE",
        signature_method="zscore",
    )
    expression, signature, warnings, _ = main.expression_for_request(
        object(), request, eligible_barcodes=eligible
    )
    constant = signature["standardization"][0]
    assert constant["sample_standard_deviation"] == 0.0
    assert constant["scaling_standard_deviation"] == 1.0
    assert constant["constant"] is True
    assert sum(expression.values()) == pytest.approx(0.0)
    assert any("contributes zero variation" in warning for warning in warnings)


def test_signature_schema_accepts_directions_and_rejects_ambiguous_weights() -> None:
    signature = SignatureSpec(
        name="Immune state",
        gene_symbol="IFNG:1,IL10:-1",
        signature_method="singscore",
    )
    request = AnalysisRequest(
        cohort="TCGA-TEST",
        gene_symbol=signature.gene_symbol,
        signature_method=signature.signature_method,
    )
    assert [row["direction"] for row in main.signature_entries(request)] == [
        "up",
        "down",
    ]

    with pytest.raises(ValidationError, match="cannot be zero"):
        SignatureGene(gene_symbol="IFNG", weight=0)
    with pytest.raises(ValidationError, match="signed gene membership"):
        SignatureSpec(
            gene_symbol="IFNG,GZMB",
            signature_method="aucell",
            signature_genes=[
                SignatureGene(gene_symbol="IFNG", weight=2),
                SignatureGene(gene_symbol="GZMB"),
            ],
        )
    with pytest.raises(ValidationError, match="undersized component"):
        SignatureSpec(
            gene_symbol="IFNG:1,GZMB:1,IL10:-1",
            signature_method="ssgsea",
        )
    with pytest.raises(ValidationError, match="does not use gene weights"):
        PanCancerSurvivalRequest(
            gene_symbol="IFNG, GZMB",
            signature_method="mean",
            signature_genes=[
                SignatureGene(gene_symbol="IFNG", weight=2),
                SignatureGene(gene_symbol="GZMB"),
            ],
        )


def test_aucell_sample_seed_is_stable_and_sample_specific() -> None:
    first = aucell_sample_seed("SAMPLE-A")
    assert first == aucell_sample_seed("SAMPLE-A")
    assert first != aucell_sample_seed("SAMPLE-B")
    assert 1 <= first <= 2_147_483_646


def test_rank_scoring_matrix_entry_limit_fails_before_r(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matrix = _rank_matrix(tmp_path, ["S1", "S2", "S3", "S4"])
    monkeypatch.setattr(signature_scoring, "MAX_MATRIX_ENTRIES", 3_999)
    with pytest.raises(ValueError, match="exceeds the 3,999-entry limit"):
        run_rank_based_signature_score(
            matrix=matrix,
            canonical_sample_ids=matrix.sample_ids,
            entries=[
                {
                    "gene_symbol": "G0001",
                    "resolved_symbol": "G0001",
                    "weight": 1.0,
                },
                {
                    "gene_symbol": "G0002",
                    "resolved_symbol": "G0002",
                    "weight": 1.0,
                },
            ],
            method="singscore",
            cache_root=tmp_path / "cache",
            dataset_identity={"dataset_id": "fixture", "release_id": "v1"},
        )


def test_rank_scoring_repeat_is_identical_and_cache_state_is_not_scientific(
    tmp_path: Path,
    monkeypatch,
) -> None:
    matrix = _rank_matrix(tmp_path, ["S1", "S2", "S3"])
    calls = 0

    def fake_run(command, **_kwargs):
        nonlocal calls
        calls += 1
        input_payload = json.loads(Path(command[2]).read_text(encoding="utf-8"))
        output = {
            "schema_version": "trace-bioconductor-signature-engine-v1",
            "method": input_payload["method"],
            "package": {
                "singscore": "singscore",
                "ssgsea": "GSVA",
                "aucell": "AUCell",
            }[input_payload["method"]],
            "package_version": EXPECTED_PACKAGE_VERSIONS[input_payload["method"]],
            "r_version": "4.4.2",
            "constant_signature_genes": [],
            "scores": [
                {
                    "sample_id": sample_id,
                    "score": float(index),
                    "up_score": float(index),
                    "down_score": 0.0,
                }
                for index, sample_id in enumerate(input_payload["sample_ids"], start=1)
            ],
        }
        Path(input_payload["output_path"]).write_text(
            json.dumps(output), encoding="utf-8"
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.signature_scoring.subprocess.run", fake_run)
    arguments = {
        "matrix": matrix,
        "canonical_sample_ids": ["S3", "S1", "S2"],
        "entries": [
            {"gene_symbol": "G0001", "resolved_symbol": "G0001", "weight": 1.0},
            {"gene_symbol": "G0002", "resolved_symbol": "G0002", "weight": 1.0},
        ],
        "method": "singscore",
        "cache_root": tmp_path / "cache",
        "dataset_identity": {"dataset_id": "fixture", "release_id": "v1"},
    }
    first_scores, first_provenance, _ = run_rank_based_signature_score(**arguments)
    second_scores, second_provenance, _ = run_rank_based_signature_score(**arguments)
    assert calls == 1
    assert first_scores == second_scores
    assert first_provenance == second_provenance
    assert "hit" not in first_provenance["cache"]
    assert first_provenance["cache"]["key_sha256"]

    # A cache artifact whose engine identity no longer matches the request is
    # not trusted, even when its filename and cache key still match.
    [cached_result] = list((tmp_path / "cache").rglob("*.json"))
    cached_payload = json.loads(cached_result.read_text(encoding="utf-8"))
    cached_payload["method"] = "aucell"
    cached_result.write_text(json.dumps(cached_payload), encoding="utf-8")
    third_scores, third_provenance, _ = run_rank_based_signature_score(**arguments)
    assert calls == 2
    assert third_scores == first_scores
    assert third_provenance == first_provenance


@pytest.mark.skipif(
    not _exact_bioc_packages_available(),
    reason="Pinned Bioconductor signature packages are unavailable.",
)
@pytest.mark.parametrize("method", ["singscore", "ssgsea", "aucell"])
def test_rank_based_scores_are_invariant_to_sample_subsetting(
    tmp_path: Path,
    method: str,
) -> None:
    matrix = _rank_matrix(tmp_path, ["S1", "S2", "S3", "S4"])
    entries = [
        {"gene_symbol": "G0001", "resolved_symbol": "G0001", "weight": 1.0},
        {"gene_symbol": "G0002", "resolved_symbol": "G0002", "weight": 1.0},
    ]
    all_scores, _, _ = run_rank_based_signature_score(
        matrix=matrix,
        canonical_sample_ids=["S1", "S2", "S3", "S4"],
        entries=entries,
        method=method,
        cache_root=tmp_path / "all-cache",
        dataset_identity={"dataset_id": "fixture", "release_id": "v1"},
    )
    subset_scores, _, _ = run_rank_based_signature_score(
        matrix=matrix,
        canonical_sample_ids=["S1", "S3"],
        entries=entries,
        method=method,
        cache_root=tmp_path / "subset-cache",
        dataset_identity={"dataset_id": "fixture", "release_id": "v1"},
    )
    assert subset_scores["S1"] == pytest.approx(all_scores["S1"])
    assert subset_scores["S3"] == pytest.approx(all_scores["S3"])


@pytest.mark.skipif(
    not _exact_bioc_packages_available(),
    reason="Pinned Bioconductor signature packages are unavailable.",
)
@pytest.mark.parametrize("method", ["singscore", "ssgsea", "aucell"])
def test_rank_based_scores_follow_planted_up_down_direction(
    tmp_path: Path,
    method: str,
) -> None:
    matrix = _planted_rank_matrix(tmp_path, ["HIGH", "MID", "LOW"])
    entries = [
        {"gene_symbol": "G0001", "resolved_symbol": "G0001", "weight": 1.0, "direction": "up"},
        {"gene_symbol": "G0002", "resolved_symbol": "G0002", "weight": 1.0, "direction": "up"},
        {"gene_symbol": "G0003", "resolved_symbol": "G0003", "weight": -1.0, "direction": "down"},
        {"gene_symbol": "G0004", "resolved_symbol": "G0004", "weight": -1.0, "direction": "down"},
    ]
    scores, provenance, _ = run_rank_based_signature_score(
        matrix=matrix,
        canonical_sample_ids=matrix.sample_ids,
        entries=entries,
        method=method,
        cache_root=tmp_path / f"{method}-cache",
        dataset_identity={"dataset_id": "planted", "release_id": "v1"},
    )
    assert all(math.isfinite(value) for value in scores.values())
    assert len(set(scores.values())) > 1
    assert scores["HIGH"] > scores["LOW"]
    assert provenance["direction"]["up_genes"] == ["G0001", "G0002"]
    assert provenance["direction"]["down_genes"] == ["G0003", "G0004"]


@pytest.mark.skipif(
    not _exact_bioc_packages_available(),
    reason="Pinned Bioconductor signature packages are unavailable.",
)
def test_aucell_exact_ties_are_invariant_to_matrix_sample_order(
    tmp_path: Path,
) -> None:
    first_matrix = _planted_rank_matrix(
        tmp_path / "first",
        ["TIE", "HIGH"],
        exact_tie_sample="TIE",
    )
    second_matrix = _planted_rank_matrix(
        tmp_path / "second",
        ["HIGH", "TIE"],
        exact_tie_sample="TIE",
    )
    entries = [
        {"gene_symbol": "G0001", "resolved_symbol": "G0001", "weight": 1.0, "direction": "up"},
        {"gene_symbol": "G0002", "resolved_symbol": "G0002", "weight": 1.0, "direction": "up"},
        {"gene_symbol": "G0003", "resolved_symbol": "G0003", "weight": -1.0, "direction": "down"},
        {"gene_symbol": "G0004", "resolved_symbol": "G0004", "weight": -1.0, "direction": "down"},
    ]

    def score(matrix: ExpressionMatrix, cache_name: str) -> dict[str, float]:
        values, _, _ = run_rank_based_signature_score(
            matrix=matrix,
            canonical_sample_ids=matrix.sample_ids,
            entries=entries,
            method="aucell",
            cache_root=tmp_path / cache_name,
            dataset_identity={"dataset_id": cache_name, "release_id": "v1"},
        )
        return values

    first = score(first_matrix, "first-cache")
    second = score(second_matrix, "second-cache")
    assert second["TIE"] == pytest.approx(first["TIE"])
    assert second["HIGH"] == pytest.approx(first["HIGH"])
