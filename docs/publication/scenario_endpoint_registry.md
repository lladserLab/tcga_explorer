# Publication Scenario and Endpoint Registry

Registry version: `1.0.0`
Frozen: `2026-07-25`
Machine-readable source:
`docs/publication/benchmark/scenario_registry_v1.json`

## What This Registry Does

This file freezes the 11 marker-endpoint scenarios used by the Application Note
before any further benchmark regeneration. The benchmark generator validates
its case definitions against the machine-readable registry and stops if a
scenario ID, cohort, marker, endpoint or primary/sensitivity relationship has
changed.

The panel was assembled after exploratory TCGA-TRACE triage on 2026-07-23.
Therefore, this registry does **not** make the initial marker selection
prospective. It prevents subsequent result-driven additions, removals or
endpoint substitutions and preserves the panel as a heterogeneous software
stress test. It is not a biomarker-discovery sample.

## Endpoint Rule

- OS is the default primary endpoint when it passes TCGA-CDR operational QC.
- UVM BAP1 uses DSS as the sole prespecified exception because its literature
  anchor concerns disease-specific metastatic prognosis. Other-cause death is
  currently treated as non-informative censoring.
- BRCA MKI67 PFI and LUAD CD274 PFI are endpoint sensitivities paired with their
  OS primary scenarios.
- A sensitivity endpoint cannot replace a primary endpoint because it produces
  a stronger effect or smaller p-value.
- A registered endpoint that fails QC remains visible as non-evaluable; the
  suite does not silently substitute another endpoint.

All 11 registered marker-endpoint rows remain in the reported continuous BH
families. The primary biological interpretation for MKI67/BRCA and CD274/LUAD,
however, remains attached to OS; PFI describes endpoint sensitivity rather than
independent confirmation.

## Registered Scenarios

| ID | Cohort | Marker | Endpoint | Role | Parent | Literature anchor |
| --- | --- | --- | --- | --- | --- | --- |
| `lihc_cdc20_os_cutpoints` | TCGA-LIHC | CDC20 | OS | Primary, agreement stress test | - | 10.1155/2022/9117205 |
| `luad_birc5_os_cutpoints` | TCGA-LUAD | BIRC5 | OS | Primary, cutpoint-dependence stress test | - | 10.1155/2019/5451290 |
| `uvm_bap1_dss_cutpoints` | TCGA-UVM | BAP1 | DSS | Primary, low-event diagnostic | - | 10.1136/bjophthalmol-2014-305047 |
| `lgg_emp3_os_cutpoints` | TCGA-LGG | EMP3 | OS | Primary, marker-PH diagnostic | - | 10.7150/jca.41123 |
| `kirc_ca9_cutpoints` | TCGA-KIRC | CA9 | OS | Primary, nonlinearity/concordance diagnostic | - | 10.1016/j.ejca.2010.07.020 |
| `brca_mki67_os_cutpoints` | TCGA-BRCA | MKI67 | OS | Primary endpoint reference | - | 10.1007/s10549-015-3559-0 |
| `brca_mki67_pfi_cutpoints` | TCGA-BRCA | MKI67 | PFI | Endpoint sensitivity | `brca_mki67_os_cutpoints` | 10.1007/s10549-015-3559-0 |
| `skcm_pdcd1_os_cutpoints` | TCGA-SKCM | PDCD1 | OS | Primary, immune/sample diagnostic | - | 10.1016/j.intimp.2020.107080 |
| `skcm_tmem176b_os_cutpoints` | TCGA-SKCM | TMEM176B | OS | Primary exploratory immune case | - | 10.3389/fcell.2022.859958 |
| `luad_cd274_os_cutpoints` | TCGA-LUAD | CD274 | OS | Primary, unsupported-signal diagnostic | - | 10.1093/ejcts/ezaa172 |
| `luad_cd274_pfi_cutpoints` | TCGA-LUAD | CD274 | PFI | Endpoint sensitivity | `luad_cd274_os_cutpoints` | 10.1093/ejcts/ezaa172 |

## Change Control

The v1 file is immutable once cited by regenerated artifacts. A future change
requires:

1. A new registry filename and version.
2. A written rationale that does not use the newly observed effect or p-value
   as an inclusion/exclusion criterion.
3. Recalculation of the declared multiplicity families.
4. Regeneration of all scenario metadata, aggregate tables and manuscript
   statements.

The SHA-256 of the exact registry file is copied into every per-scenario
`benchmark_metadata.json` and the aggregate overview CSV.
