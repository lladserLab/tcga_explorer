from pathlib import Path

from app.gsea import load_gene_set_catalog, public_gene_set_catalog, read_gmt


GENE_SET_DIR = Path(__file__).resolve().parents[1] / "gene_sets"
EXPECTED_GO_COLLECTIONS = {
    "go_bp": {
        "count": 8195,
        "sha256": "004ae0ebcbe4d7f3c76744aaf3c53ebc8e4a35006070c452dae72f145d5c74b6",
    },
    "go_mf": {
        "count": 2202,
        "sha256": "62d80137dd55172dfe5033eb5140d793791b47740f9e34fb12e1e62d5a26a88a",
    },
    "go_cc": {
        "count": 1287,
        "sha256": "aced394e253f5ad56f8a8ad02a421943b0dadebdc0e6b01323e701f2c443d01c",
    },
}


def test_bundled_go_catalog_is_frozen_available_and_attributed() -> None:
    catalog = {
        item["id"]: item for item in load_gene_set_catalog(GENE_SET_DIR)
    }
    public = {
        item["id"]: item for item in public_gene_set_catalog(GENE_SET_DIR)
    }

    for collection_id, expected in EXPECTED_GO_COLLECTIONS.items():
        entry = catalog[collection_id]
        assert entry["available"] is True
        assert entry["version"] == "2026-06-19"
        assert entry["gene_set_count"] == expected["count"]
        assert entry["sha256"] == expected["sha256"]
        assert entry["license"] == "CC BY 4.0"
        assert entry["release_doi"] == "10.5281/zenodo.20943148"
        assert entry["generation"]["relationships"] == ["is_a", "part_of"]
        assert len(entry["source_artifacts"]) == 2
        assert "file" not in public[collection_id]


def test_bundled_go_gmts_parse_with_unique_persistent_term_names() -> None:
    for collection_id in EXPECTED_GO_COLLECTIONS:
        entry = next(
            item
            for item in load_gene_set_catalog(GENE_SET_DIR)
            if item["id"] == collection_id
        )
        pathways = read_gmt(entry["file"])

        assert len(pathways) == EXPECTED_GO_COLLECTIONS[collection_id]["count"]
        assert all(pathway["name"].startswith("GO:") for pathway in pathways)
        assert all(
            pathway["description"].startswith(
                "https://purl.obolibrary.org/obo/GO_"
            )
            for pathway in pathways
        )
        assert len({pathway["name"] for pathway in pathways}) == len(pathways)
        assert all(len(pathway["genes"]) >= 5 for pathway in pathways)
