import json
from types import SimpleNamespace

from app.provenance import analysis_data_provenance


def test_analysis_data_provenance_hashes_loaded_matrix_and_records_gdc_ids(tmp_path) -> None:
    derived = tmp_path / "derived"
    matrix_dir = derived / "matrices" / "TCGA-TEST"
    matrix_dir.mkdir(parents=True)
    (matrix_dir / "log2_tpm.float32.bin").write_bytes(b"matrix")
    (matrix_dir / "metadata.json").write_text(
        json.dumps(
            {
                "status": "ready",
                "scales": {
                    "log2_tpm": {
                        "file": "log2_tpm.float32.bin",
                        "source_column": "tpm_unstranded",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    map_dir = derived / "maps"
    map_dir.mkdir()
    (map_dir / "TCGA-TEST.json").write_text(
        json.dumps(
            {
                "cohort": "TCGA-TEST",
                "barcode_to_file": {
                    "S1": (
                        "/data/tcga/gdc_cache/TCGA-TEST/Transcriptome_Profiling/"
                        "Gene_Expression_Quantification/case-file-uuid/"
                        "gdc-file-uuid.rna_seq.augmented_star_gene_counts.tsv"
                    )
                },
            }
        ),
        encoding="utf-8",
    )
    clinical = tmp_path / "cdr.xlsx"
    clinical.write_bytes(b"clinical")
    settings = SimpleNamespace(
        tcga_data_dir=tmp_path / "tcga",
        derived_expression_dir=derived,
        tcga_cdr_path=clinical,
        tcga_sync_state_dir=tmp_path / "sync",
        publication_benchmark_dir=tmp_path / "publication",
    )

    result = analysis_data_provenance(
        settings,
        cohort="TCGA-TEST",
        expression_scale="log2_tpm",
        selected_barcodes={"S1"},
    )

    assert result["selected_gdc_file_count"] == 1
    assert result["selected_gdc_file_identifiers"][0]["gdc_file_uuid"] == "gdc-file-uuid"
    assert result["provenance_completeness"]["exact_expression_artifact_hashed"] is True
    assert all("path" not in item for item in result["expression_files"])
