# Bundled GSEA gene-set collections

TRACE Explorer loads the files in this directory through
`collections.json`. Every collection file is frozen and SHA-256 checked before
it can be selected for an analysis.

## ImmPort immune gene lists

`immport-current-20260730.gmt` is a frozen copy of ImmPort's public
`all_gene_lists.gmt` resource. It contains the immunologically relevant gene
lists curated by ImmPort from Gene Ontology and Reactome. The exact source URL,
freeze label and SHA-256 are recorded in `collections.json`.

Use and redistribution remain subject to the
[ImmPort User Agreement](https://docs.immport.org/home/agreement/), including
its acknowledgement, commensurate-redistribution, no-reidentification,
warranty and clinical-use provisions. The file is not relicensed under TRACE
Explorer's MIT license. See the repository-level
[`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md).

## Gene Ontology 2026-06-19

The three GO collections are derived from the official Gene Ontology
Consortium release dated **2026-06-19**:

- Biological Process (`go_bp`): 8,195 sets
- Molecular Function (`go_mf`): 2,202 sets
- Cellular Component (`go_cc`): 1,287 sets

Release DOI: [10.5281/zenodo.20943148](https://doi.org/10.5281/zenodo.20943148)

Frozen official inputs:

| Input | Official URL | SHA-256 |
| --- | --- | --- |
| `go-basic.obo` | <https://release.geneontology.org/2026-06-19/ontology/go-basic.obo> | `c72fc198a86983d55e43aac585d1ffdbeb6e3601475b3f18b6045acdc0a0734c` |
| `HUMAN-uniprot.gaf.gz` | <https://release.geneontology.org/2026-06-19/annotations/gaf/HUMAN-uniprot.gaf.gz> | `258f6ea163375c036929478c400f25bf32e6d83df547cc4b864dfb4ec20c1ffb` |

Generation is deterministic:

```bash
python3 scripts/build_go_gsea_collections.py \
  --obo /path/to/go-basic.obo \
  --gaf /path/to/HUMAN-uniprot.gaf.gz \
  --output-dir backend/gene_sets
```

The builder verifies both source checksums. It retains all GAF evidence codes,
excludes `NOT`-qualified annotations, non-human records, unknown or obsolete
terms, maps alternative IDs to their active term, and propagates each direct
annotation to active ancestors using exactly the safe `is_a` and `part_of`
edges from `go-basic`. BP, MF and CC remain separate. Sets with fewer than five
source genes are omitted because the public GSEA contract never permits a
minimum set size below five. Rows and genes are sorted, so identical inputs
produce byte-identical GMT files.

Machine-readable source metadata, generation counts and output checksums are
in `go-20260619.provenance.json`.

### License and attribution

Gene Ontology Consortium data from the 2026-06-19 release
(DOI:10.5281/zenodo.20943148) are made available under the
[Creative Commons Attribution 4.0 license](https://creativecommons.org/licenses/by/4.0/).
The bundled GMTs are deterministic transformations of those data. Creator:
Gene Ontology Consortium, © 1999–2026 Gene Ontology Consortium. The source
files, license notice and release-specific provenance are linked above.

GO data and these derived files are provided as-is, without warranties. See
the Gene Ontology Consortium's
[citation, attribution and website disclaimer](https://geneontology.org/docs/go-citation-policy/).

Recommended citations are listed in the official
[GO citation policy](https://geneontology.org/docs/go-citation-policy/).
