# External Concordance Panel

Status: completed.

These three cases were listed in `docs/publication/concordance_validation_plan.md` on 2026-07-23, before this panel was executed. The comparison is a cross-pipeline software check, not independent validation because both resources use TCGA.

| Case | cBioPortal n/events | cBioPortal HR (95% CI) | p | TCGA-TRACE n/events | TCGA-TRACE HR (95% CI) | p / Holm p | Decision |
| --- | ---: | --- | ---: | ---: | --- | --- | --- |
| CA9/KIRC OS | 510/168 | 0.81 (0.60-1.10) | 0.177 | 531/175 | 0.68 (0.51-0.92) | 0.013 / 0.050 | direction concordant nominal support discordant |
| PDCD1/SKCM OS | 426/210 | 0.57 (0.43-0.76) | 8.45e-05 | 453/213 | 0.53 (0.40-0.69) | 4.59e-06 / 9.48e-06 | direction and nominal support concordant |
| CD274/LUAD OS | 501/181 | 1.08 (0.81-1.45) | 0.585 | 505/182 | 0.99 (0.74-1.33) | 0.962 / 1.000 | both unsupported point direction differs |

## Contract and limits

- External source: cBioPortal TCGA PanCancer Atlas.
- Cutoff/model: median; univariable Cox with Efron ties.
- Sample rule: Among cBioPortal samples with the requested expression value and complete OS_MONTHS/OS_STATUS, select one sample per patient using TCGA sample-code priority: primary, recurrent, additional primary, metastatic, other; resolve ties lexicographically by sample ID.
- Expression is not on a common numerical scale: cBioPortal uses its PanCancer Atlas RSEM profile; TCGA-TRACE uses GDC STAR-count log2(TPM + 1).
- Endpoint and patient sets can differ because cBioPortal clinical OS and TCGA-CDR OS are curated separately.
- No result is described as an exact replication or independent validation.

Each case directory contains the gzipped API snapshot, selected patient-level input, external survival output and comparison JSON.
