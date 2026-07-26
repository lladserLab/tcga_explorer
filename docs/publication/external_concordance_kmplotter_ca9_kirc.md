# External Concordance Record: KM Plotter CA9/KIRC OS

Status date: 2026-07-25. External query retained from 2026-07-22; TCGA-TRACE
comparator refreshed from the frozen publication benchmark.

This record documents a reviewer-visible external comparison between
TCGA-TRACE and KM Plotter. It is a concordance check, not an exact replication:
the two resources use different data processing, endpoint handling and cutoff
scales.

## External Tool

- Tool: KM Plotter pan-cancer RNA-seq
- URL: `https://kmplot.com/analysis/index.php?p=service&cancer=pancancer_rnaseq`
- Accessed: 2026-07-22 from the local development environment
- Internal gene/probe resolution endpoint:
  `https://kmplot.com/analysis/getAffyidInJSONWithAjax.php?cancer=pancancer_rnaseq&id=CA9`
- Resolution response: `{"id":"CA9","genesymbol":"-","all_genesymbols":["-"],"msg":"success"}`

## Query

| Field | Value |
| --- | --- |
| Gene | `CA9` |
| Dataset | Pan-cancer RNA-seq, restricted to Kidney renal clear cell carcinoma |
| KM Plotter tumor type | `kidney_renal_clear_cell_carcinoma` |
| KM Plotter displayed cohort size | `n=530` in the form option |
| Survival endpoint | OS |
| Cutoff | Median |
| Cutoff value reported by KM Plotter | 5327 |

## KM Plotter Result

| Field | Value |
| --- | --- |
| P value | 0.1763 |
| Median survival, low expression | 91.73 months |
| Median survival, high expression | 118.47 months |
| Result image endpoint | `https://kmplot.com/kmplot_commons/php/src/service/results/index.php?result=km_260723_020101_458400_6a6175dd6feeb_CA9&version=academic&type=png` |

## TCGA-TRACE Comparator Run

| Field | Value |
| --- | --- |
| Analysis ID | `9281f0877ce24ce79d683a0c0a19f07c` |
| Cohort | TCGA-KIRC |
| Gene | CA9 |
| Endpoint | OS from TCGA-CDR |
| Cutoff | Median |
| Patients/events | 531 / 175 |
| Log-rank p-value | 0.012593721055601859 |
| Univariable HR | 0.683428468979249 |
| Univariable 95% CI | 0.5059102095035746-0.9232359091342277 |
| Within-scenario Holm p-value | 0.05037488422240736 |
| Age-adjusted HR | 0.7042823344646859 |
| Age-adjusted 95% CI | 0.5210212340515176-0.9520026713344716 |
| Age-adjusted Cox p-value | 0.022617445857293327 |
| Fixed-horizon RMST difference | 107.18139914886069 days at tau=1826.25 days |
| Fixed-horizon RMST p-value | 0.04372387294946699 |
| Median survival | High not reached; Low 2299 days |
| Reproducibility hash | `7d3ca49db684f5331b52b132c5bcf064a3240e877dc05094e041a236e4c83585` |

## Concordance Decision

Direction is concordant. Both tools place the higher-CA9 group on the longer
survival side: KM Plotter reports longer median OS for high expression, and
TCGA-TRACE estimates HR < 1 with high-expression median OS not reached.

Statistical significance is not concordant. KM Plotter reports p=0.1763,
whereas TCGA-TRACE reports nominal log-rank p=0.0126 and univariable Cox
p=0.0131. The four-cutpoint within-scenario Holm value is 0.0504, showing that
the nominal grouped result sits immediately beyond the declared family-wise
threshold even though the age-adjusted median-split HR is 0.704
(p=0.0226). This is a directional sanity check and an example of why
TCGA-TRACE keeps multiplicity, continuous modelling and adjusted analyses
beside a Kaplan--Meier p-value.

Do not describe this as an exact replication. Differences can arise from the
KM Plotter RNA-seq preprocessing, integer cutoff scale, internal patient
inclusion rules, endpoint implementation and unavailable event-count export.
