from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.importer import ensure_gene_index
from app.gene_symbols import (
    GENE_ALIASES,
    canonical_gene_symbol,
    gene_symbol_resolution,
    normalize_gene_symbol,
)
from app.models import GeneIndex


# Re-export the pure helpers from this historical module so existing public
# imports remain valid while schema code can avoid importing database models.
__all__ = [
    "GENE_ALIASES",
    "canonical_gene_symbol",
    "gene_symbol_resolution",
    "normalize_gene_symbol",
    "resolve_gene_symbol",
    "gene_exists",
]


def resolve_gene_symbol(db: Session, tcga_data_dir, cohort_id: str, symbol: str) -> dict:
    ensure_gene_index(db, tcga_data_dir, cohort_id)
    query = symbol.strip().upper()
    if not query:
        return {"query": symbol, "resolved": None, "status": "empty", "warnings": ["Empty gene symbol."]}

    if gene_exists(db, cohort_id, query):
        return {"query": symbol, "resolved": query, "status": "exact", "warnings": []}

    alias = GENE_ALIASES.get(query)
    if alias and gene_exists(db, cohort_id, alias):
        return {
            "query": symbol,
            "resolved": alias,
            "status": "alias",
            "warnings": [f"{query} was resolved to current symbol {alias}."],
        }

    return {
        "query": symbol,
        "resolved": None,
        "status": "not_found",
        "warnings": [f"{query} was not found in {cohort_id}."],
    }


def gene_exists(db: Session, cohort_id: str, symbol: str) -> bool:
    return bool(
        db.scalar(
            select(GeneIndex.id)
            .where(GeneIndex.cohort == cohort_id)
            .where(GeneIndex.gene_symbol == symbol)
            .limit(1)
        )
    )
