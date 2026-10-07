from __future__ import annotations

import pytest

from app.gene_aliases import GENE_ALIASES as LEGACY_GENE_ALIASES
from app.gene_aliases import canonical_gene_symbol as legacy_canonical_gene_symbol
from app.gene_symbols import (
    GENE_ALIASES,
    canonical_gene_symbol,
    gene_symbol_resolution,
    normalize_gene_symbol,
)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (" p53 ", "TP53"),
        ("TP53", "TP53"),
        ("her2", "ERBB2"),
        ("ERBB2", "ERBB2"),
        ("unknown-gene", "UNKNOWN-GENE"),
    ],
)
def test_pure_gene_symbol_canonicalization(
    query: str,
    expected: str,
) -> None:
    assert canonical_gene_symbol(query) == expected


def test_gene_resolution_distinguishes_alias_from_exact_query() -> None:
    assert gene_symbol_resolution(" p53 ") == {
        "requested_gene_symbol": "P53",
        "resolved_gene_symbol": "TP53",
        "resolution": "alias",
    }
    assert gene_symbol_resolution(" tp53 ") == {
        "requested_gene_symbol": "TP53",
        "resolved_gene_symbol": "TP53",
        "resolution": "exact",
    }
    assert normalize_gene_symbol(None) == ""


def test_historical_gene_alias_imports_remain_shared() -> None:
    assert LEGACY_GENE_ALIASES is GENE_ALIASES
    assert legacy_canonical_gene_symbol is canonical_gene_symbol
    assert LEGACY_GENE_ALIASES["P53"] == "TP53"
    assert LEGACY_GENE_ALIASES["HER2"] == "ERBB2"
