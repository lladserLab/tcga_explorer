from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.importer import ensure_gene_index
from app.models import GeneIndex


GENE_ALIASES = {
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
