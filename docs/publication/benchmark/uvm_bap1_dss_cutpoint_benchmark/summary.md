# TCGA-UVM BAP1 DSS cutpoint benchmark

- Run started: 2026-07-25T17:49:32Z
- Run finished: 2026-07-25T17:49:43Z
- Completed analyses: 4/4
- Cached analyses in this run: 4/4
- API base URL: `http://192.168.1.31:3000/tcga_explorer`
- Cohort: `TCGA-UVM`
- Gene: `BAP1`
- Endpoint: `DSS`
- Expression scale: `log2_tpm`
- Prespecified complete-case Cox adjustment: age_at_index.
- Grouped-test family: four prespecified two-group cutpoint sensitivities within this marker-endpoint scenario.
- Grouped multiplicity: Holm adjustment within this scenario. The maxstat member contributes its Lau94 selection-adjusted rank-statistic p-value; the other prespecified rules contribute their log-rank p-values.
- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.
- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.
- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.
- Cutpoint-independent continuous reference: n=80, events=21, HR per +1 SD=0.51 (0.35-0.74), linear p=3.73e-04, linear suite BH q=6.84e-04, events/parameter=21.0, nonlinearity p=0.002, nonlinearity suite BH q=0.012.

| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| maxstat | 80 | 21 | 7.65e-05 | 3.06e-04 |  |  |  |  |  |  | 299 @ 1180 | 7.79e-07 | not estimable | Standard adjusted Cox failed; Outcome-optimized cutpoint; grouped estimates are post-selection; Firth adjusted sensitivity HR 0.02 (0.00-0.17), p 8.91e-07 |
| median | 80 | 21 | 3.09e-04 | 6.17e-04 | 0.17 (0.06-0.50) | 0.001 | 0.18 (0.06-0.55) | 0.003 | 0.514 | 0.210 | 224 @ 1180 | 0.004 | grouped 0.17 vs continuous-implied 0.34; absolute log-HR ratio 1.64 | No model-diagnostic caution recorded |
| upper_quartile | 80 | 21 | 0.002 | 0.002 |  |  |  |  |  |  | 245 @ 1180 | 2.90e-06 | not estimable | Standard adjusted Cox failed; Firth adjusted sensitivity HR 0.05 (0.00-0.40), p 6.98e-04 |
| upper_lower_quartile | 40 | 10 | 1.82e-04 | 5.46e-04 |  |  |  |  |  |  | 262 @ 1180 | 0.004 | not estimable | Standard adjusted Cox failed; Middle 50% excluded; Adjusted Cox 5.0 events/parameter (caution); Firth adjusted sensitivity HR 0.03 (0.00-0.22), p 6.13e-05 |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `6d5fa8880eea436b84905005f5463921` | `c71ad2bc04878f064d5a089750b169a14b66820d8ee9897afe52c0e39568181a` | `c5246fadd102795995a5e54cc20fd4bf4cbe8c4454fb9232c83df8457c6d7e55` | `58babc3372d0aa834362fcbfd1f475a1d4297a9681ae713ad0fb36f905c39f87` |
| median | `eeb98524f7d740ae8c504bbf3c8a3341` | `f529defae5459c3296a1ed1c7c1a19916d510a32d11e228f839153ef873fbb49` | `840c13c117d85c5035e3ea6b59fc23057a6cb63a9c0ebe216d7f29a29f57c992` | `58babc3372d0aa834362fcbfd1f475a1d4297a9681ae713ad0fb36f905c39f87` |
| upper_quartile | `f8d3fe280dce4915a76f7aa36317f9bd` | `67ae105c34fafdbf98272222ddffc562c54d1e577f9f1690318b92d745e1f489` | `a79ba96d68f49d171269909bccee2b870a9bb2a52a6c1989784beb0818f5f5a5` | `58babc3372d0aa834362fcbfd1f475a1d4297a9681ae713ad0fb36f905c39f87` |
| upper_lower_quartile | `df79bd0ab5634b138e72b3f3bd75fac9` | `abb25482fe77442d302cf745f52d8fa3dadfb3d83b847b536df574035cfc6bf4` | `8ea6e4a4be41f722a121ff2ee972ec187089b8d0758fc35b3b4cd40d1cdfc6de` | `58babc3372d0aa834362fcbfd1f475a1d4297a9681ae713ad0fb36f905c39f87` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| maxstat | 0.75 | 884.6 | 168 | 4.34e-05 |
| maxstat | 0.90 | 1061.5 | 244 | 3.52e-06 |
| maxstat | 1.00 | 1179.5 | 299 | 7.79e-07 |
| median | 0.75 | 884.6 | 122 | 0.019 |
| median | 0.90 | 1061.5 | 179 | 0.007 |
| median | 1.00 | 1179.5 | 224 | 0.004 |
| upper_quartile | 0.75 | 884.6 | 138 | 8.38e-05 |
| upper_quartile | 0.90 | 1061.5 | 200 | 9.75e-06 |
| upper_quartile | 1.00 | 1179.5 | 245 | 2.90e-06 |
| upper_lower_quartile | 0.75 | 884.6 | 142 | 0.023 |
| upper_lower_quartile | 0.90 | 1061.5 | 209 | 0.009 |
| upper_lower_quartile | 1.00 | 1179.5 | 262 | 0.004 |

## Low-information and Firth Sensitivities

| Method | Model family | Events / parameter | Information status | Firth HR (95% CI) | Firth p | Ties |
| --- | --- | ---: | --- | ---: | ---: | --- |
| maxstat | Grouped adjusted | 10.5 | adequate | 0.02 (0.00-0.17) | 8.91e-07 | breslow |
| upper_quartile | Grouped adjusted | 10.5 | adequate | 0.05 (0.00-0.40) | 6.98e-04 | breslow |
| upper_lower_quartile | Grouped adjusted | 5.0 | caution | 0.03 (0.00-0.22) | 6.13e-05 | breslow |
