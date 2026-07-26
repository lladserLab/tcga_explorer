# Reviewer Access Statement

Status date: 2026-07-24.

Use this statement with the public web instance and repository. Replace the
license and Zenodo archive URL before upload.

## Prepared Reviewer Access Statement

Reviewers can evaluate the running TCGA-TRACE web application at:

```text
https://apps.cienciavida.org/tcga_explorer/
```

The corresponding health endpoint is:

```text
https://apps.cienciavida.org/tcga_explorer/api/v1/health
```

For reproducibility checks beyond the public interface, reviewers can also run
TCGA-TRACE from
`https://github.com/lladserLab/tcga_explorer` using Docker Compose.
The submitted repository includes the application source, Docker configuration,
benchmark scripts, compact benchmark outputs, a data-snapshot manifest and a
reviewer reproduction guide.

The Docker application is started with:

```sh
docker compose up -d --build
```

The local app is then available at:

```text
http://localhost:3000/tcga_explorer/
```

Health and API documentation are available at:

```text
http://localhost:3000/tcga_explorer/api/v1/health
http://localhost:3000/tcga_explorer/api/docs
```

The Docker stack expects public TCGA RNA-seq files to be mounted at `../TCGA`.
TCGA-CDR endpoints are enabled when the official TCGA-CDR file is present at
`clinical/TCGA-CDR-SupplementalTableS1.xlsx`. Full TCGA expression matrices and
patient-level analysis exports are not redistributed in git; the repository
tracks compact benchmark outputs and the data-snapshot manifest used for the
submitted analyses.

## Reviewer File To Cite

Point reviewers to:

```text
manuscript/bioinformatics_app_note/submission/reviewer_reproduction_guide.md
```

That guide gives the exact commands for rebuilding the manuscript PDFs,
benchmark tables, data-snapshot manifest and reproducibility round-trip check.
