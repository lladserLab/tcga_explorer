from pathlib import Path

from app.data_sync.sync import (
    diff_manifests,
    stable_manifest_hash,
    update_count_matrix_columns,
    validate_star_count_file,
)


def test_manifest_hash_is_stable_for_sorted_files() -> None:
    files = [
        {"file_id": "b", "file_name": "b.tsv", "md5sum": "2", "file_size": 2, "cohort": "TCGA-B"},
        {"file_id": "a", "file_name": "a.tsv", "md5sum": "1", "file_size": 1, "cohort": "TCGA-A"},
    ]

    assert stable_manifest_hash(files) == stable_manifest_hash(list(reversed(files)))


def test_manifest_diff_reports_added_changed_and_stale() -> None:
    remote = [
        {"file_id": "a", "file_name": "a.tsv", "md5sum": "new", "file_size": 10},
        {"file_id": "b", "file_name": "b.tsv", "md5sum": "same", "file_size": 20},
    ]
    local = [
        {"file_id": "a", "file_name": "a.tsv", "md5sum": "old", "file_size": 10},
        {"file_id": "c", "file_name": "c.tsv", "md5sum": "same", "file_size": 30},
    ]

    diff = diff_manifests(remote, local)

    assert [item["file_id"] for item in diff["added"]] == ["b"]
    assert [item["remote"]["file_id"] for item in diff["changed"]] == ["a"]
    assert [item["file_id"] for item in diff["stale"]] == ["c"]


def test_update_count_matrix_columns_replaces_and_appends(tmp_path: Path) -> None:
    matrix = tmp_path / "count_matrix.tsv"
    matrix.write_text("\tS1\nTP53\t1\nKRAS\t2\n", encoding="utf-8")

    update_count_matrix_columns(matrix, {"S1": {"TP53": "10"}, "S2": {"TP53": "5", "KRAS": "7"}})

    assert matrix.read_text(encoding="utf-8") == "\tS1\tS2\nTP53\t10\t5\nKRAS\t2\t7\n"


def test_validate_star_count_file_accepts_required_columns(tmp_path: Path) -> None:
    path = tmp_path / "file.rna_seq.augmented_star_gene_counts.tsv"
    path.write_text(
        "# comment\n"
        "gene_id\tgene_name\tgene_type\tunstranded\tstranded_first\tstranded_second\t"
        "tpm_unstranded\tfpkm_unstranded\tfpkm_uq_unstranded\n"
        "ENSG1\tTP53\tprotein_coding\t1\t1\t1\t2\t3\t4\n",
        encoding="utf-8",
    )

    validate_star_count_file(path)

