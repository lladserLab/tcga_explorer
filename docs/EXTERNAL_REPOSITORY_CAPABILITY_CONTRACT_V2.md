# External repository capability contract v2

The v2 contract lets a curated release support molecular analyses even when
survival is unavailable or documented for only part of the molecular cohort.
The v1 contract remains supported without semantic changes.

## Versions

- Study specification: `tcga-trace-study-spec-v2`
- Bundle: `tcga-trace-external-rnaseq-bundle-v2`
- Existing v1 specifications and bundles remain accepted.
- A v1 bundle still requires at least one endpoint with 10 patients, 5 events
  and 5 censored observations.

In v2, `endpoints` may be absent or an empty array. If an endpoint is present,
its value table may contain a subset of the patients in `patients.tsv`. Missing
endpoint rows do not remove patients or samples from the molecular population.

The v2 default expression layer must contain every sample declared in
`samples.tsv` exactly once, and every patient must have a sample in that layer.
Every sample row must declare a non-negative integer `selection_rank` so that
patient-level selection remains deterministic.

## Derived capabilities

Validation writes a normalized capability object into release QC. Manual
configuration cannot enable a capability that fails QC.

```json
{
  "capabilities": {
    "expression": {"available": true, "reason": null},
    "expression_comparison": {"available": true, "reason": null},
    "gsea": {"available": true, "reason": null},
    "survival": {
      "available": false,
      "reason": "No endpoint currently reaches the repository survival QC thresholds.",
      "endpoint_ids": []
    }
  },
  "available_modules": ["expression", "gsea"]
}
```

The stable workspace module identifiers are:

- `analysis`, `compare` and `multiverse`: require `survival`.
- `expression`: requires `expression_comparison`.
- `gsea`: requires `gsea`.

The dataset service accepts the module identifiers above and the aliases
`survival`, `robustness`, `expression_comparison` and
`expression-comparison` through `analysis_type`.

The stable Python interfaces are:

```python
repository_capabilities(source)
require_repository_capability(source, analysis_type)
list_repository_datasets(db, analysis_type="gsea")
```

`source` may be a `RepositoryContext`, `RepositoryRelease`, QC mapping or
`None`. `require_repository_capability` returns the selected capability detail
or raises `ValueError` with a human-readable QC reason.

For private uploads, a `RepositoryContext` uses the module-specific decisions
attested by upload QC. A targeted private matrix can therefore support survival
or expression comparison without meeting the 10,000-gene external-repository
threshold; GSEA retains its separate upload threshold.

## Prohibiting an analysis

A v2 specification may prohibit a derived capability, but must provide a
reason. This is intended for design-based restrictions such as
outcome-conditioned ascertainment.

```json
{
  "capability_policy": {
    "prohibited": {
      "survival": "Participants were selected using the observed outcome."
    }
  }
}
```

Prohibition is one-way: it cannot make an unavailable analysis available.
Prohibiting `expression` also disables every dependent molecular module.

## GDC and TARGET

TCGA and PCAWG projects remain prohibited in the independent external
repository. TARGET requires an exact, specification-level opt-in and an
explicit sample-type allowlist:

```json
{
  "schema_version": "tcga-trace-study-spec-v2",
  "source": {
    "provider": "gdc_api",
    "project_id": "TARGET-AML",
    "target_project_opt_in": "TARGET-AML",
    "sample_type_priority": [
      "Primary Blood Derived Cancer - Peripheral Blood",
      "Primary Blood Derived Cancer - Bone Marrow"
    ]
  }
}
```

The opt-in must equal the exact `project_id`. `sample_type_priority` is both an
allowlist and a deterministic priority order; the adapter does not fall back to
unlisted tissue roles. In v2, expression-file selection is independent of
endpoint completeness.

## Promotion integrity

Promotion now resolves the cancer code, dataset identity, release identity and
immutable destination before copying. A new release is copied through a unique
temporary directory and atomically renamed. If database import or commit fails,
the transaction is rolled back and only the destination installed by that
promotion call is removed. Existing immutable destinations are never removed
by rollback cleanup.
