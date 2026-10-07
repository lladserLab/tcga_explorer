"""Dependency-free normalization for the small curated gene-alias contract.

Database-aware resolvers intentionally live elsewhere.  This module is safe to
import from schemas and cache-boundary code, where importing SQLAlchemy models
would otherwise couple request normalization to repository availability.
"""

from __future__ import annotations

from typing import Any


# Keep this as a regular dictionary for backwards compatibility: callers have
# historically imported ``GENE_ALIASES`` and iterated over ``.items()``.
GENE_ALIASES: dict[str, str] = {
    "P53": "TP53",
    "BCC7": "TP53",
    "LFS1": "TP53",
    "HER2": "ERBB2",
    "HER-2": "ERBB2",
    "NEU": "ERBB2",
    "C-ERBB-2": "ERBB2",
    "C-MYC": "MYC",
    "BHLHE39": "MYC",
    "P16": "CDKN2A",
    "INK4A": "CDKN2A",
    "P14ARF": "CDKN2A",
    "MLL": "KMT2A",
    "KIAA1809": "KMT2A",
    "BRAF1": "BRAF",
    "HER1": "EGFR",
    "ERBB": "EGFR",
    "ERBB1": "EGFR",
    "CD340": "ERBB2",
}


def normalize_gene_symbol(value: Any) -> str:
    """Return the stable, case-insensitive representation of a gene query."""

    return str(value or "").strip().upper()


def canonical_gene_symbol(value: Any) -> str:
    """Resolve a curated alias chain without consulting data or a database.

    Alias chains are followed defensively so future catalog additions remain
    deterministic.  A cycle falls back to the last non-repeated symbol instead
    of looping indefinitely.
    """

    symbol = normalize_gene_symbol(value)
    visited: set[str] = set()
    while symbol and symbol not in visited:
        visited.add(symbol)
        candidate = normalize_gene_symbol(GENE_ALIASES.get(symbol, symbol))
        if candidate == symbol:
            break
        symbol = candidate
    return symbol


def gene_symbol_resolution(value: Any) -> dict[str, str]:
    """Describe the pure query-to-current-symbol resolution contract."""

    requested = normalize_gene_symbol(value)
    resolved = canonical_gene_symbol(requested)
    return {
        "requested_gene_symbol": requested,
        "resolved_gene_symbol": resolved,
        "resolution": "exact" if requested == resolved else "alias",
    }
