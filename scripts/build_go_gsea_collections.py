#!/usr/bin/env python3
"""Build frozen human Gene Ontology GMT collections for TRACE Explorer.

The builder intentionally has no third-party dependencies. It consumes the
dated GO Consortium ontology and human annotation products, verifies their
frozen SHA-256 digests, and emits deterministic BP/MF/CC GMT files.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import gzip
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable, TextIO


GO_RELEASE = "2026-06-19"
GO_ONTOLOGY_VERSION = "2026-06-15"
GO_RELEASE_DOI = "10.5281/zenodo.20943148"
GO_LICENSE = "CC BY 4.0"
GO_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
GO_RELEASE_URL = f"https://release.geneontology.org/{GO_RELEASE}/"
GO_OBO_URL = f"{GO_RELEASE_URL}ontology/go-basic.obo"
GO_GAF_URL = (
    f"{GO_RELEASE_URL}annotations/gaf/HUMAN-uniprot.gaf.gz"
)
GO_OBO_SHA256 = (
    "c72fc198a86983d55e43aac585d1ffdbeb6e3601475b3f18b6045acdc0a0734c"
)
GO_GAF_SHA256 = (
    "258f6ea163375c036929478c400f25bf32e6d83df547cc4b864dfb4ec20c1ffb"
)
SAFE_PARENT_RELATIONSHIPS = ("is_a", "part_of")
MIN_RAW_GENES = 5
OUTPUT_NAMES = {
    "biological_process": "go-bp-20260619.gmt",
    "molecular_function": "go-mf-20260619.gmt",
    "cellular_component": "go-cc-20260619.gmt",
}
ASPECT_NAMESPACE = {
    "P": "biological_process",
    "F": "molecular_function",
    "C": "cellular_component",
}


@dataclass(frozen=True)
class GoTerm:
    go_id: str
    name: str
    namespace: str
    parents: tuple[str, ...]
    alt_ids: tuple[str, ...]
    obsolete: bool


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_sha256(path: Path, expected: str, label: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(
            f"{label} SHA-256 mismatch: expected {expected}, observed {actual}."
        )


def _term_from_fields(fields: dict[str, list[str]]) -> GoTerm | None:
    go_id = (fields.get("id") or [""])[0].strip()
    if not go_id.startswith("GO:"):
        return None
    relationships: list[str] = []
    for raw in fields.get("relationship", []):
        relation, _, target = raw.partition(" ")
        target_id = target.split(" ", 1)[0].strip()
        if relation == "part_of" and target_id.startswith("GO:"):
            relationships.append(target_id)
    is_a = [
        raw.split(" ", 1)[0].strip()
        for raw in fields.get("is_a", [])
        if raw.split(" ", 1)[0].strip().startswith("GO:")
    ]
    return GoTerm(
        go_id=go_id,
        name=(fields.get("name") or [go_id])[0].strip(),
        namespace=(fields.get("namespace") or [""])[0].strip(),
        parents=tuple(sorted(set(is_a + relationships))),
        alt_ids=tuple(sorted(set(fields.get("alt_id", [])))),
        obsolete=(fields.get("is_obsolete") or ["false"])[0].strip().lower()
        == "true",
    )


def parse_go_basic_obo(
    path: Path,
) -> tuple[dict[str, GoTerm], dict[str, str], dict[str, str]]:
    """Parse active GO terms and the safe parent edges used for propagation."""

    all_terms: dict[str, GoTerm] = {}
    header: dict[str, str] = {}
    fields: dict[str, list[str]] | None = None

    def finish_term() -> None:
        nonlocal fields
        if fields is None:
            return
        term = _term_from_fields(fields)
        if term is not None:
            if term.go_id in all_terms:
                raise ValueError(f"Duplicate GO term in ontology: {term.go_id}.")
            all_terms[term.go_id] = term
        fields = None

    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\r\n")
            if line == "[Term]":
                finish_term()
                fields = defaultdict(list)
                continue
            if line.startswith("[") and line.endswith("]"):
                finish_term()
                fields = None
                continue
            if not line or line.startswith("!"):
                continue
            key, separator, value = line.partition(": ")
            if not separator:
                continue
            if fields is None:
                header.setdefault(key, value)
            else:
                fields[key].append(value)
    finish_term()

    active_terms = {
        go_id: term for go_id, term in all_terms.items() if not term.obsolete
    }
    alt_to_primary: dict[str, str] = {}
    for term in active_terms.values():
        for alt_id in term.alt_ids:
            if alt_id in alt_to_primary:
                raise ValueError(f"Duplicate active GO alternative ID: {alt_id}.")
            alt_to_primary[alt_id] = term.go_id

    for term in active_terms.values():
        for parent_id in term.parents:
            parent = active_terms.get(parent_id)
            if parent is None:
                continue
            if parent.namespace != term.namespace:
                raise ValueError(
                    "go-basic safe relationship crossed namespaces: "
                    f"{term.go_id} ({term.namespace}) -> "
                    f"{parent_id} ({parent.namespace})."
                )
    return active_terms, alt_to_primary, header


def _ancestor_closure(terms: dict[str, GoTerm]) -> dict[str, frozenset[str]]:
    memo: dict[str, frozenset[str]] = {}

    def visit(go_id: str, stack: frozenset[str]) -> frozenset[str]:
        cached = memo.get(go_id)
        if cached is not None:
            return cached
        if go_id in stack:
            raise ValueError(f"Cycle found in go-basic at {go_id}.")
        term = terms[go_id]
        ancestors = {go_id}
        next_stack = stack | {go_id}
        for parent_id in term.parents:
            if parent_id in terms:
                ancestors.update(visit(parent_id, next_stack))
        result = frozenset(ancestors)
        memo[go_id] = result
        return result

    for term_id in terms:
        visit(term_id, frozenset())
    return memo


def _open_gaf(path: Path) -> TextIO:
    with path.open("rb") as handle:
        compressed = handle.read(2) == b"\x1f\x8b"
    if compressed:
        return gzip.open(path, mode="rt", encoding="utf-8")
    return path.open(encoding="utf-8")


def parse_human_gaf(
    path: Path,
    terms: dict[str, GoTerm],
    alt_to_primary: dict[str, str],
) -> tuple[dict[str, set[str]], dict[str, object]]:
    """Read direct, non-NOT human annotations keyed by active GO term."""

    direct: dict[str, set[str]] = defaultdict(set)
    stats: dict[str, object] = {
        "rows": 0,
        "accepted_rows": 0,
        "excluded_not_rows": 0,
        "excluded_nonhuman_rows": 0,
        "excluded_unknown_or_obsolete_term_rows": 0,
        "gaf_version": None,
        "date_generated": None,
        "go_version": None,
    }
    with _open_gaf(path) as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.rstrip("\r\n")
            if not line:
                continue
            if line.startswith("!"):
                key, separator, value = line[1:].partition(": ")
                if separator and key in {
                    "gaf-version",
                    "date-generated",
                    "go-version",
                }:
                    stats[key.replace("-", "_")] = value.strip()
                continue
            stats["rows"] = int(stats["rows"]) + 1
            fields = line.split("\t")
            if len(fields) != 17:
                raise ValueError(
                    f"Invalid GAF row {line_number}: expected 17 fields, "
                    f"observed {len(fields)}."
                )
            qualifiers = {
                item.strip().upper()
                for item in fields[3].split("|")
                if item.strip()
            }
            if "NOT" in qualifiers:
                stats["excluded_not_rows"] = (
                    int(stats["excluded_not_rows"]) + 1
                )
                continue
            annotated_taxon = fields[12].split("|", 1)[0].strip()
            if annotated_taxon != "taxon:9606":
                stats["excluded_nonhuman_rows"] = (
                    int(stats["excluded_nonhuman_rows"]) + 1
                )
                continue
            go_id = alt_to_primary.get(fields[4].strip(), fields[4].strip())
            term = terms.get(go_id)
            expected_namespace = ASPECT_NAMESPACE.get(fields[8].strip())
            if term is None or term.namespace != expected_namespace:
                stats["excluded_unknown_or_obsolete_term_rows"] = (
                    int(stats["excluded_unknown_or_obsolete_term_rows"]) + 1
                )
                continue
            symbol = fields[2].strip().upper()
            if not symbol:
                continue
            direct[go_id].add(symbol)
            stats["accepted_rows"] = int(stats["accepted_rows"]) + 1

    if stats["gaf_version"] != "2.2":
        raise ValueError(
            f"Expected GAF 2.2, observed {stats['gaf_version']!r}."
        )
    return dict(direct), stats


def propagate_annotations(
    terms: dict[str, GoTerm],
    direct: dict[str, set[str]],
) -> dict[str, set[str]]:
    """Propagate annotations to self and ancestors over is_a and part_of."""

    closure = _ancestor_closure(terms)
    propagated: dict[str, set[str]] = defaultdict(set)
    for term_id in sorted(direct):
        genes = direct[term_id]
        for ancestor_id in closure[term_id]:
            propagated[ancestor_id].update(genes)
    return dict(propagated)


def _gmt_row(term: GoTerm, genes: Iterable[str]) -> str:
    clean_name = " ".join(term.name.replace("\t", " ").split())
    description = (
        "https://purl.obolibrary.org/obo/" + term.go_id.replace(":", "_")
    )
    return "\t".join(
        [f"{term.go_id} {clean_name}", description, *sorted(set(genes))]
    )


def write_collections(
    output_dir: Path,
    terms: dict[str, GoTerm],
    propagated: dict[str, set[str]],
    *,
    min_raw_genes: int = MIN_RAW_GENES,
) -> dict[str, dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, object]] = {}
    for namespace, filename in OUTPUT_NAMES.items():
        path = output_dir / filename
        selected_ids = [
            term_id
            for term_id in sorted(terms)
            if terms[term_id].namespace == namespace
            and len(propagated.get(term_id, set())) >= min_raw_genes
        ]
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(
                "# Gene Ontology Consortium "
                f"{GO_RELEASE}; propagated over is_a and part_of; "
                "NOT and obsolete annotations excluded.\n"
            )
            for term_id in selected_ids:
                handle.write(
                    _gmt_row(terms[term_id], propagated[term_id]) + "\n"
                )
        path.chmod(0o644)
        results[namespace] = {
            "file": filename,
            "sha256": sha256_file(path),
            "gene_set_count": len(selected_ids),
            "unique_gene_count": len(
                {
                    gene
                    for term_id in selected_ids
                    for gene in propagated[term_id]
                }
            ),
        }
    return results


def build_collections(
    obo_path: Path,
    gaf_path: Path,
    output_dir: Path,
    *,
    verify_sources: bool = True,
    min_raw_genes: int = MIN_RAW_GENES,
) -> dict[str, object]:
    if verify_sources:
        _verify_sha256(obo_path, GO_OBO_SHA256, "go-basic.obo")
        _verify_sha256(gaf_path, GO_GAF_SHA256, "HUMAN-uniprot.gaf.gz")

    terms, alt_to_primary, ontology_header = parse_go_basic_obo(obo_path)
    direct, gaf_stats = parse_human_gaf(gaf_path, terms, alt_to_primary)
    propagated = propagate_annotations(terms, direct)
    outputs = write_collections(
        output_dir,
        terms,
        propagated,
        min_raw_genes=min_raw_genes,
    )
    provenance: dict[str, object] = {
        "schema_version": "tcga-trace-go-gsea-provenance-v1",
        "release": GO_RELEASE,
        "release_doi": GO_RELEASE_DOI,
        "release_url": GO_RELEASE_URL,
        "ontology_version": GO_ONTOLOGY_VERSION,
        "license": GO_LICENSE,
        "license_url": GO_LICENSE_URL,
        "creator": "Gene Ontology Consortium",
        "source_artifacts": {
            "ontology": {
                "file": "go-basic.obo",
                "url": GO_OBO_URL,
                "sha256": GO_OBO_SHA256,
                "data_version": ontology_header.get("data-version"),
            },
            "annotations": {
                "file": "HUMAN-uniprot.gaf.gz",
                "url": GO_GAF_URL,
                "sha256": GO_GAF_SHA256,
                "gaf_version": gaf_stats["gaf_version"],
                "date_generated": gaf_stats["date_generated"],
                "go_version": gaf_stats["go_version"],
            },
        },
        "generation": {
            "generator": "scripts/build_go_gsea_collections.py",
            "safe_parent_relationships": list(SAFE_PARENT_RELATIONSHIPS),
            "annotation_policy": (
                "All evidence codes retained; NOT-qualified, non-human, "
                "unknown and obsolete-term rows excluded; direct annotations "
                "propagated to self and active ancestors."
            ),
            "gene_identifier": (
                "Uppercase UniProtKB human GAF DB Object Symbol "
                "(HGNC-compatible gene symbol)"
            ),
            "minimum_raw_genes": min_raw_genes,
            "gaf_stats": gaf_stats,
            "active_ontology_terms": len(terms),
        },
        "outputs": outputs,
    }
    provenance_path = output_dir / "go-20260619.provenance.json"
    provenance_path.write_text(
        json.dumps(
            provenance,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    provenance_path.chmod(0o644)
    return provenance


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build deterministic GO BP/MF/CC GMT collections from the "
            f"official {GO_RELEASE} release."
        )
    )
    parser.add_argument("--obo", type=Path, required=True)
    parser.add_argument("--gaf", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--skip-source-checksums",
        action="store_true",
        help="Intended only for local fixtures; never use for a release build.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    provenance = build_collections(
        args.obo,
        args.gaf,
        args.output_dir,
        verify_sources=not args.skip_source_checksums,
    )
    for namespace, details in provenance["outputs"].items():
        print(
            f"{namespace}: {details['gene_set_count']} sets, "
            f"SHA-256 {details['sha256']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
