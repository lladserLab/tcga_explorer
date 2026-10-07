from __future__ import annotations

import json
from pathlib import Path

from app.expression import gdc_expression_gene_provenance


def test_gdc_gene_provenance_uses_the_derived_row_and_versioned_source_id(
    monkeypatch,
    tmp_path: Path,
) -> None:
    tcga_dir = tmp_path / "tcga"
    derived_dir = tmp_path / "derived"
    metadata_path = derived_dir / "matrices" / "TCGA-BRCA" / "metadata.json"
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text(
        json.dumps(
            {
                "status": "ready",
                "gene_to_row": {"TP53": 2627},
            }
        ),
        encoding="utf-8",
    )
    source_path = tmp_path / "sample.rna_seq.augmented_star_gene_counts.tsv"
    source_path.write_text(
        "gene_id\tgene_name\tunstranded\ttpm_unstranded\t"
        "fpkm_unstranded\tfpkm_uq_unstranded\n"
        "ENSG00000141510.18\tTP53\t10\t2\t1\t3\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.expression.load_or_build_cache_file_map",
        lambda *_args, **_kwargs: {"TCGA-XX-0001-01A": str(source_path)},
    )

    provenance = gdc_expression_gene_provenance(
        tcga_dir,
        derived_dir,
        "TCGA-BRCA",
        "tp53",
    )

    assert provenance == {
        "resolved_symbol": "TP53",
        "source_gene_id": "ENSG00000141510.18",
        "source_identifier_type": "versioned_ensembl_gene_id",
        "mapping_source": (
            "GDC augmented STAR-count gene_id + derived matrix metadata"
        ),
        "mapping_status": "verified",
        "row_number": 2627,
    }
