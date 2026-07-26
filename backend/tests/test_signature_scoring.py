import pytest

from app import main
from app.schemas import AnalysisRequest, SignatureGene


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
