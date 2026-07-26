# External Concordance Validation Plan

Status date: 2026-07-25. Completed.

This document defines the minimum manual concordance record needed before
submitting TCGA-TRACE as a Bioinformatics Application Note. The goal is not to
prove that every external resource returns identical results; the goal is to
show that TCGA-TRACE reproduces the expected direction and scale of at least one
reviewer-visible survival association when endpoint, cohort, cutoff and sample
definitions are close enough to compare.

## Completed Panel

The prespecified three-case panel is frozen at:

```text
docs/publication/benchmark/external_concordance_panel/
```

It compares median-split OS for the three cases registered below against
cBioPortal TCGA PanCancer Atlas using frozen official-API responses. The panel
contains a supported case, a directionally concordant but nominally discordant
case, and an unsupported case whose null point estimates fall on opposite sides
of one. Source snapshots, patient-level external inputs, R outputs, checksums
and TCGA-TRACE run hashes are retained.

The earlier reviewer-visible KM Plotter record remains available at:

```text
docs/publication/external_concordance_kmplotter_ca9_kirc.md
```

It is a secondary historical record; no new automated KM Plotter queries were
performed because the current service terms prohibit automated access.

## Required Record

For any additional concordance checks, complete the fields below.

| Field | Required entry |
| --- | --- |
| External tool | GEPIA2, KM Plotter, cSurvival or another reviewer-visible comparator |
| Accessed date | Exact date of the manual query |
| Cohort/dataset | Cancer type and source dataset reported by the external tool |
| Marker/signature | Gene symbol or signature definition |
| Endpoint | OS, DSS, DFI, PFI or external-tool label |
| Cutoff | Median, quartile, optimal/maxstat or tool-specific rule |
| Sample count | Total and per-group counts, if exposed |
| Event count | Total and per-group counts, if exposed |
| External result | HR, CI, log-rank p-value and survival plot export, as available |
| TCGA-TRACE result | Analysis ID, endpoint source, cutoff, HR, CI, p-values and run hash |
| Concordance decision | Same direction, comparable magnitude, not comparable or discordant |
| Mismatch explanation | Endpoint, data release, sample rule, expression scale or cutoff difference |

## Candidate Cases

| Priority | Comparator | TCGA-TRACE case | Why this case |
| --- | --- | --- | --- |
| 1 | cBioPortal TCGA PanCancer Atlas | TCGA-SKCM PDCD1 OS, median split | Supported immune-marker case; direction and nominal support agree. |
| 2 | cBioPortal TCGA PanCancer Atlas | TCGA-KIRC CA9 OS, median split | Direction agrees while nominal support differs. |
| 3 | cBioPortal TCGA PanCancer Atlas | TCGA-LUAD CD274 OS, median split | Both estimates are unsupported; point directions differ close to the null. |

## Reporting Rule

Report concordance only when the comparison is defensible. If the external tool
uses a different endpoint, sample source, cutoff search, expression processing
or mixed TCGA/GEO cohort, record the mismatch and do not call the result a
direct replication. A non-comparable record is still useful in the supplement if
it explains why exact cross-tool agreement is not expected.

## Source-Access Decision

Checked on 2026-07-22:

- GEPIA2 remained unreachable from the execution environment.
- KM Plotter remains a cited and reviewer-visible comparator, but its current
  terms prohibit automated access. The pre-existing manually documented CA9
  result is retained without additional scripted queries.
- cBioPortal documents a public REST API for programmatic access to the data
  used by its visualizations. The panel uses that API, freezes every response
  and records the access date as 2026-07-25.
- cBioPortal PanCancer Atlas RSEM and TCGA-TRACE GDC STAR-count TPM are treated
  as different expression pipelines. The comparison evaluates
  directional/reporting concordance and is not an exact replication or
  independent biological validation.
