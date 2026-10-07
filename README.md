<p align="center">
  <img src="frontend/public/brand/trace-mark.svg" width="88" alt="TRACE Explorer logo">
</p>

# TRACE Explorer

**Transcriptomic Research Across Cohorts and Endpoints**

TRACE connects survival, expression and pathway analyses in TCGA, curated bulk RNA-seq cohorts and your own data. Save patient groups, carry their assignments into molecular analyses and examine a marker in other studies while retaining each study's identity and analysis settings.

**[Open the web app](https://apps.cienciavida.org/tcga_explorer/)** · [API documentation](https://apps.cienciavida.org/tcga_explorer/api/docs) · [User guides](docs/TUTORIALS.md)

## What can I investigate?

- **Survival:** test genes or signatures with Kaplan–Meier curves, continuous and adjusted Cox models, model diagnostics and restricted mean survival time. Compare cutpoints, joint markers or signatures and interactions.
- **Molecular differences:** compare expression and pathways between patient groups, including groups saved from a survival analysis. Saved assignments and the direction of the contrast stay attached to the analysis.
- **Evidence across cohorts:** scan TCGA cancer types or compare a gene across independent studies. Study-level results retain their population, endpoint and expression scale; compatible estimates can be synthesized.
- **Your own data:** load an expression matrix and matched, de-identified clinical data. Available analyses depend on the columns and expression scale you provide.

Mean, Z-score, weighted, singscore, ssGSEA and AUCell signature scoring are available where the cohort meets the method's requirements. [The scoring guide](docs/SIGNATURE_SCORING_METHODS.md) explains the choices.

## Use TRACE on your computer

The desktop app runs the analysis engine locally, with Python, R and their libraries included. **Docker is not required.** Data, projects and results stay on your computer until you delete them. Public cohorts are imported separately, so you can choose the cancers and studies you need.

| System | Download | Supported target |
| --- | --- | --- |
| Windows | [Windows installer](https://apps.cienciavida.org/tcga_explorer/downloads/desktop/0.1.7/TRACE-Explorer-Setup-0.1.7-windows-x64.exe) | x64 |
| macOS | [macOS disk image](https://apps.cienciavida.org/tcga_explorer/downloads/desktop/0.1.7/TRACE-Explorer-0.1.7-macOS-arm64.dmg) | Apple Silicon |
| Linux | [Linux AppImage](https://apps.cienciavida.org/tcga_explorer/downloads/desktop/0.1.7/TRACE-Explorer-0.1.7-Linux-x64.AppImage) | x64, glibc 2.39 or later |

These builds are unsigned on Windows and are not Apple-notarized on macOS; installation may be blocked by operating-system security checks. Signing and notarization are pending. See [desktop installation](docs/DESKTOP.md) for platform details and download checksums.

In **Manage data**, choose **From this computer** to find or import TRACE `.tar.gz` packages. Use **Download** to connect a hosted package catalog, then choose TCGA or external studies by cancer. A public data catalog is not configured by default. Own expression and clinical files use **Use your own data** in the main app. [Data management](docs/DESKTOP.md#manage-data) explains both paths.

On the public web service, uploaded datasets and their results are temporary, with a default retention of 24 hours. Export anything you need to keep.

## Recover an analysis

Download results together with their source information, settings, inclusion and exclusion counts, patient/group assignments and software identity. Survival exports include an audit record and a reproduction capsule for supported models. The export's own record identifies the inputs and procedures used; available source metadata varies by dataset.

See [the API guide](docs/API.md) for exported fields and [the bundle verifier](scripts/publication/verify_reproducibility_bundle.py) to check a downloaded survival bundle or rerun its included R script.

## Automate a workflow

TRACE is available through the web interface, REST API, remote MCP and a standalone CLI. They use the same analysis engine.

- REST documentation: [English](docs/API.md) · [Español](docs/API_ES.md)
- MCP endpoint: `https://apps.cienciavida.org/tcga_explorer/mcp`
- CLI: [English](docs/CLI.md) · [Español](docs/CLI_ES.md)

MCP exposes structured tools for selecting datasets, resolving genes, running analyses and retrieving results. Client setup is documented in the [API guide](docs/API.md).

## Develop or self-host

The web stack uses React/Vite, FastAPI, PostgreSQL, an R analysis engine and Nginx. Native apps use Electron and a local SQLite database. Desktop source for all three systems lives under [desktop/](desktop/README.md).

Start with [development and self-hosting](docs/DEVELOPMENT.md). Source data, database contents and generated runtime bundles are separate from this repository. Dependency locks, tests, study import specifications and the scientific scripts are included.

Tutorial videos are downloaded separately with checksum verification:

```sh
cd frontend
npm ci
npm run videos:fetch
```

## Documentation

| Topic | Guide |
| --- | --- |
| Modules and practical examples | [Tutorials](docs/TUTORIALS.md) |
| Signatures and scoring requirements | [Signature scoring](docs/SIGNATURE_SCORING_METHODS.md) |
| Expression scales | [RNA transformations](docs/RNA_BULK_TRANSFORMATIONS.md) |
| Cohort sources and import contracts | [External repository](docs/EXTERNAL_RNASEQ_REPOSITORY.md) |
| Desktop installation and data | [Desktop guide](docs/DESKTOP.md) |
| Development, testing and self-hosting | [Development guide](docs/DEVELOPMENT.md) |
| API, exports and MCP | [API guide](docs/API.md) |
| Public-service operations | [Operations](docs/PUBLIC_SERVICE_OPERATIONS.md) |

## License and contact

TRACE source is licensed under [MIT](LICENSE). Bundled libraries, gene-set collections and source datasets have their own terms; see [third-party notices](THIRD_PARTY_NOTICES.md). Dataset licensing remains attached to its source and release.

Report software issues through [GitHub Issues](https://github.com/lladserLab/tcga_explorer/issues). For project inquiries, contact Sergio Hernández-Galaz at [shernandez@cienciavida.org](mailto:shernandez@cienciavida.org).
TRACE is intended for research, not clinical decision-making.
