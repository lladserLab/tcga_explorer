# Statistical Calibration

This benchmark evaluates the revised evidence profile; it does not calibrate or reinstate the removed retained/not-retained rule.

## Design

- Alpha: `0.050`.
- Seed: `20260725`.
- Observed-cohort permutations: `2000`.
- Known-truth simulations: `2000` per scenario, `n=300`.
- Grouped family: maxstat, median, upper quartile and outer quartiles, with Holm adjustment within each replicate.
- Maxstat: Lau94 corrected p-value enters multiplicity; the selected group log-rank p-value is retained only to quantify selection bias.
- Rejection intervals: Wilson 95% Monte Carlo intervals.

## Source Cohort

- Analysis: `d7a5cea9a427469885f6534cc03678b2`.
- Patients/events: `365/130`.
- Fixed tau: `1091.00` days.
- Audit reproducibility hash: `21d6130e1dd31fb8d7823ac121f5a42ee6e96f334652d20eb619dc169790e1b7`.
- Continuous records hash: `92699d577a954fcdb1a1d1fee76b1cc0c6885d622b16bc20c0f7c1b470cbbc68`.

## Rejection Proportions

| Scenario | Linear Cox | Spline nonlinear | Marker PH | Grouped Holm | Maxstat naive | Maxstat Lau94 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| LIHC expression permutation | 5.0% (4.1-6.0) | 5.8% (4.9-6.9) | 5.1% (4.2-6.2) | 3.2% (2.5-4.1) | 39.6% (37.5-41.8) | 1.8% (1.3-2.5) |
| Simulated null | 5.7% (4.7-6.7) | 4.5% (3.6-5.4) | 5.3% (4.4-6.4) | 3.5% (2.8-4.5) | 38.2% (36.1-40.4) | 2.4% (1.8-3.2) |
| Linear PH | 99.2% (98.8-99.5) | 5.5% (4.5-6.5) | 5.0% (4.1-6.0) | 96.4% (95.4-97.1) | 99.9% (99.6-99.9) | 94.3% (93.3-95.3) |
| Delayed non-PH | 99.5% (99.0-99.7) | 6.0% (5.1-7.2) | 88.2% (86.8-89.6) | 96.7% (95.8-97.4) | 100.0% (99.7-100.0) | 94.1% (93.0-95.1) |
| U-shaped nonlinear | 15.0% (13.5-16.6) | 100.0% (99.8-100.0) | 20.7% (19.0-22.5) | 97.9% (97.1-98.4) | 100.0% (99.8-100.0) | 99.1% (98.6-99.4) |

Rates are operating characteristics of different estimands. In particular, the PH column measures diagnostic sensitivity rather than biomarker association power.

## Dependence of Grouped Summaries

Under observed-cohort expression permutation with a median split:

- Spearman correlation of -log10 p, log-rank versus Cox: `1.000`.
- Spearman correlation of -log10 p, log-rank versus RMST: `0.664`.
- Spearman correlation of -log10 p, Cox versus RMST: `0.665`.
- All three nominally below alpha: `57/2000 (2.9%, 95% CI 2.2-3.7%)`.

These correlations are why TCGA-TRACE reports log-rank, grouped Cox and RMST side by side rather than treating them as independent barriers. Marker-specific PH modifies interpretation and never removes an RMST or association result.

## Machine-readable Outputs

- `calibration_results.raw.json`: design, source hashes, scenario truth, summaries and software versions.
- `permutation_replicates.csv`: all observed-null replicate metrics.
- `simulation_replicates.csv`: all known-truth replicate metrics.
- `manifest.json`: SHA-256 checksums for the benchmark outputs.
