# Third-party notices

TRACE Explorer's MIT license applies to the project's original software and
documentation. The following bundled data assets retain their source terms and
are not relicensed under MIT.

## Self-hosted API documentation

Swagger UI (`swagger-ui-dist` 5.32.15) and ReDoc 2.5.3 are served locally
under their original Apache-2.0 and MIT licenses, respectively. The unmodified
license files and per-file SHA-256 values are bundled in
`backend/app/static/api-docs/`. `scripts/vendor_api_docs.py` verifies each
pinned npm archive's SHA-512 integrity before extracting the allowed assets.
These bundles do not contact a CDN or an external API validator in TRACE.
The sole bundle transformation embeds Redoc's checksum-verified attribution
SVG as a data URL; the visible attribution is retained. Its source, hash and
transformation are recorded in `vendor-manifest.json`.

## Platform and source icons

The Windows, Apple, Linux and GitHub marks are monochrome SVG paths from
[Simple Icons 11.15.0](https://github.com/simple-icons/simple-icons/tree/11.15.0),
distributed under CC0. Marks identify their respective platforms and source
host; use of a mark does not imply endorsement. The interface retains explicit
labels beside these decorative icons.

## Bioconductor signature-scoring engines

The runtime container installs the following pinned Bioconductor 3.20
packages. They remain under their own licenses and are not relicensed under
TRACE Explorer's MIT license:

- [`singscore` 1.26.0](https://bioconductor.org/packages/3.20/bioc/html/singscore.html),
  GPL-3, used for centred within-sample rank scoring.
- [`GSVA` 2.0.7](https://bioconductor.org/packages/3.20/bioc/html/GSVA.html),
  GPL version 2 or later, used only for its ssGSEA algorithm.
  TRACE does not expose GSVA itself as a scoring method.
- [`AUCell` 1.28.0](https://bioconductor.org/packages/3.20/bioc/html/AUCell.html),
  GPL-3, used for the optional top-ranked activity sensitivity.

Package source, documentation and license records are available from the
[Bioconductor 3.20 package archive](https://bioconductor.org/packages/3.20/bioc/).
The exact versions are also pinned in `backend/renv.lock`; scoring parameters
and scientific references are recorded in
`docs/SIGNATURE_SCORING_METHODS.md`.

## ImmPort immune gene lists

- Bundled file: `backend/gene_sets/immport-current-20260730.gmt`
- Source: ImmPort Shared Data, `all_gene_lists.gmt`
- Frozen version: `current-frozen-2026-07-30`
- SHA-256: `f194f9e54d85b5911d3b7407c586b4a631432579144814c68a01b554624b5e68`
- Provider: Immunology Database and Analysis Portal (ImmPort), funded by the
  NIH/NIAID Division of Allergy, Immunology, and Transplantation
- Governing terms: [ImmPort User Agreement](https://docs.immport.org/home/agreement/)
- Source documentation: [ImmPort Gene Lists](https://docs.immport.org/apidocumentation/shareddataapi/genelists/)

ImmPort permits lawful use and distribution subject to its agreement,
including redistribution under commensurate terms, acknowledgement of ImmPort
and the relevant data providers, no attempt to identify individuals, and the
source warranty and clinical-use limitations. Anyone redistributing or using
this file must review and comply with the current ImmPort agreement.

## Gene Ontology collections

- Bundled files: `backend/gene_sets/go-bp-20260619.gmt`,
  `backend/gene_sets/go-mf-20260619.gmt`, and
  `backend/gene_sets/go-cc-20260619.gmt`
- Source release: Gene Ontology Consortium, 2026-06-19
- Release DOI: [10.5281/zenodo.20943148](https://doi.org/10.5281/zenodo.20943148)
- License: [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)
- Attribution: Gene Ontology Consortium, © 1999–2026 Gene Ontology Consortium

The three GMT files are deterministic transformations of the release's
`go-basic.obo` ontology and human UniProt GAF. Exact source and output hashes,
generation rules, exclusions and counts are recorded in
`backend/gene_sets/go-20260619.provenance.json`. The license requires
attribution, a link to the license and an indication that the source data were
transformed. GO data and the derived collections are provided without
warranties; consult the [GO citation policy](https://geneontology.org/docs/go-citation-policy/)
for recommended scientific citations.

## External transcriptomic cohorts

Public cohort source matrices and clinical records are not covered by the MIT
license. TRACE Explorer normally rebuilds these releases from pinned public
sources rather than distributing source data. Each release manifest records
its source URLs, checksums, license evidence and whether redistribution is
allowed. Where source terms do not permit redistribution, download remains
disabled even though in-place analysis may be available. See
`repository_registry/studies/` and
`docs/EXTERNAL_RNASEQ_REPOSITORY.md` for the release-specific boundary.

## TCGA registered reproduction capsules

The compact reviewer package includes three frozen
`clean_container_reproduction/capsules/*/input.json` files. They contain the
exact de-identified patient-level analysis records needed to rerun the
registered single-gene, weighted-signature and two-signature examples; they are
not raw sequencing files, full source matrices or private user uploads.

These capsule inputs derive from the open-access TCGA/GDC and published
clinical resources identified in their audit and snapshot manifests. Use is
subject to the [NCI Genomic Data Commons data-access policies](https://gdc.cancer.gov/access-data/data-access-policies):
users must not attempt to identify participants and must acknowledge the
specific datasets/accessions and the NIH-designated repository. GDC-controlled
data require dbGaP authorization and the applicable data-use agreement; no
controlled-access source file is intentionally included in this archive.

The archive builder names these three files explicitly and rejects arbitrary
clinical/expression matrices, runtime user uploads and private credentials. If
a future capsule is rebuilt from a different access class, its redistribution
status must be reviewed again rather than inherited from this notice.
