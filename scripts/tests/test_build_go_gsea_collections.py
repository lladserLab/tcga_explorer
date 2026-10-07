from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from scripts.build_go_gsea_collections import (
    build_collections,
    parse_go_basic_obo,
    parse_human_gaf,
    propagate_annotations,
    sha256_file,
    write_collections,
)


OBO_FIXTURE = """\
format-version: 1.2
data-version: releases/fixture

[Term]
id: GO:0000001
name: bp root
namespace: biological_process

[Term]
id: GO:0000002
name: bp is-a child
namespace: biological_process
is_a: GO:0000001 ! bp root

[Term]
id: GO:0000003
name: bp part-of child
namespace: biological_process
alt_id: GO:9999999
relationship: part_of GO:0000002 ! bp is-a child

[Term]
id: GO:0000004
name: obsolete bp term
namespace: biological_process
is_obsolete: true

[Term]
id: GO:0000010
name: mf root
namespace: molecular_function

[Term]
id: GO:0000020
name: cc root
namespace: cellular_component
"""


def _gaf_row(
    symbol: str,
    go_id: str,
    aspect: str,
    *,
    relation: str = "involved_in",
    taxon: str = "taxon:9606",
) -> str:
    return "\t".join(
        [
            "UniProtKB",
            f"FIXTURE-{symbol}",
            symbol,
            relation,
            go_id,
            "GO_REF:0000001",
            "IEA",
            "",
            aspect,
            f"{symbol} fixture product",
            symbol,
            "protein",
            taxon,
            "20260618",
            "UniProt",
            "",
            f"UniProtKB:FIXTURE-{symbol}",
        ]
    )


def _write_fixture_sources(tmp_path: Path) -> tuple[Path, Path]:
    obo_path = tmp_path / "go-basic.obo"
    obo_path.write_text(OBO_FIXTURE, encoding="utf-8")
    gaf_path = tmp_path / "HUMAN-uniprot.gaf.gz"
    rows = [
        "!gaf-version: 2.2",
        "!generated-by: fixture",
        "!date-generated: 2026-06-18 08:16",
        "!go-version: fixture",
        _gaf_row("GeneB", "GO:9999999", "P"),
        _gaf_row("GeneA", "GO:0000003", "P"),
        _gaf_row("GeneNot", "GO:0000001", "P", relation="NOT|involved_in"),
        _gaf_row("GeneOld", "GO:0000004", "P"),
        _gaf_row("GeneMouse", "GO:0000003", "P", taxon="taxon:10090"),
        _gaf_row("GeneMF", "GO:0000010", "F", relation="enables"),
        _gaf_row("GeneCC", "GO:0000020", "C", relation="located_in"),
    ]
    with gzip.open(gaf_path, "wt", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(rows) + "\n")
    return obo_path, gaf_path


def test_go_builder_propagates_safe_edges_and_separates_namespaces(
    tmp_path: Path,
) -> None:
    obo_path, gaf_path = _write_fixture_sources(tmp_path)
    terms, alt_to_primary, header = parse_go_basic_obo(obo_path)
    direct, stats = parse_human_gaf(gaf_path, terms, alt_to_primary)
    propagated = propagate_annotations(terms, direct)

    assert header["data-version"] == "releases/fixture"
    assert "GO:0000004" not in terms
    assert alt_to_primary == {"GO:9999999": "GO:0000003"}
    assert direct["GO:0000003"] == {"GENEA", "GENEB"}
    assert propagated["GO:0000001"] == {"GENEA", "GENEB"}
    assert propagated["GO:0000002"] == {"GENEA", "GENEB"}
    assert propagated["GO:0000003"] == {"GENEA", "GENEB"}
    assert propagated["GO:0000010"] == {"GENEMF"}
    assert propagated["GO:0000020"] == {"GENECC"}
    assert stats["accepted_rows"] == 4
    assert stats["excluded_not_rows"] == 1
    assert stats["excluded_nonhuman_rows"] == 1
    assert stats["excluded_unknown_or_obsolete_term_rows"] == 1

    first_output = tmp_path / "first"
    second_output = tmp_path / "second"
    first = write_collections(
        first_output,
        terms,
        propagated,
        min_raw_genes=1,
    )
    second = write_collections(
        second_output,
        terms,
        propagated,
        min_raw_genes=1,
    )

    assert first == second
    for details in first.values():
        filename = str(details["file"])
        assert sha256_file(first_output / filename) == sha256_file(
            second_output / filename
        )
        assert (first_output / filename).stat().st_mode & 0o777 == 0o644
    assert (first_output / "go-bp-20260619.gmt").read_text(
        encoding="utf-8"
    ).splitlines()[1:] == [
        "GO:0000001 bp root\thttps://purl.obolibrary.org/obo/GO_0000001"
        "\tGENEA\tGENEB",
        "GO:0000002 bp is-a child\thttps://purl.obolibrary.org/obo/GO_0000002"
        "\tGENEA\tGENEB",
        "GO:0000003 bp part-of child\thttps://purl.obolibrary.org/obo/GO_0000003"
        "\tGENEA\tGENEB",
    ]


def test_release_builder_rejects_sources_outside_frozen_checksums(
    tmp_path: Path,
) -> None:
    obo_path, gaf_path = _write_fixture_sources(tmp_path)

    with pytest.raises(ValueError, match="go-basic.obo SHA-256 mismatch"):
        build_collections(obo_path, gaf_path, tmp_path / "output")
