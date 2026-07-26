# Narrative and Peer-Review Audit

Status date: 2026-07-26.

## Editorial Verdict

The current manuscript has a defensible Application Note narrative, provided
that TCGA-TRACE is presented as an integrated reporting and reconstruction
contract rather than a new survival estimator or a clinically validated
biomarker platform.

The central claim is narrow:

> TCGA-TRACE preserves endpoint definition, eligible participants, selected RNA
> samples, score construction, model diagnostics, multiplicity scope, software,
> executable rerun material and a server-signed receipt as one analysis record.

The manuscript must not claim novelty for Kaplan--Meier analysis, continuous or
grouped Cox models, optimized cutpoints, gene-set scoring, two-predictor
interactions, PH testing, pan-cancer analysis or code-based reproducibility.

## Narrative Thread

1. Transcriptomic survival associations depend on endpoint, eligibility,
   sample selection, expression scale, score, cutpoint and model.
2. Existing portals and packages solve substantial parts of this problem, often
   with greater dataset, assay, pathway, multi-omic, single-cell or programming
   breadth than TCGA-TRACE.
3. The residual problem is not access to another estimator. It is preserving
   the complete path from source data and participant selection to estimands,
   diagnostics and executable reconstruction.
4. TCGA-TRACE implements that reporting contract together with a declared
   multiverse, continuous and grouped sensitivity analyses, PH diagnostics,
   RMST, sparse-data cautions, competing-risk estimands and pan-cancer
   heterogeneity reporting.
5. Technical evaluation tests reconstruction, signed-origin verification,
   operating characteristics and runtime independently of biological examples.
6. Four post hoc case studies illustrate three literature-aligned outcomes and
   one non-confirmatory outcome, while the complete registered panel retains
   all null, nonlinear, sparse-event and PH-discordant results.
7. Future Plans states that retrospective TCGA screening is not independent
   biomarker validation and identifies external-cohort evaluation as the
   highest-value next step.

## Prior-Art Coverage

The source register now covers 20 direct or adjacent resources:

- survival and expression portals: GEPIA2, KM Plotter, UALCAN, OncoLnc,
  PrognoScan, SurvExpress and ESurv;
- interaction, signature and pathway systems: cSurvival, DoSurvive, PESSA,
  GSCA and Survival Genie 2;
- general cancer-genomics and transcriptomic platforms: UCSC Xena, cBioPortal,
  TIMER2.0, CaPSSA and TCGEx;
- programmable or benchmarking baselines: TCGAbiolinks, TCGAplot and SurvBoard.

The comparison is strength-first. It explicitly states where other resources
are stronger and treats residual comparison points as source-based positioning,
not proof that a capability is absent from every current release.

Recurring limitations are described as scope boundaries rather than product
defects:

- optimized grouping requires selection and multiplicity interpretation;
- broad portals prioritize dataset, assay or pathway breadth;
- code-first workflows leave harmonization and report structure to the analyst;
- predictive-model benchmarking is a different task from marker association;
- no retrospective portal provides independent clinical validation by itself.

## Case-Study Evidence Hierarchy

| Case | Role | Defensible interpretation | Prohibited interpretation |
| --- | --- | --- | --- |
| CDC20/LIHC | Positive, literature-aligned | Directional workflow concordance with a study that used TCGA and ICGC | Independent validation or reconstruction of the published two-gene model |
| BUB1B--PINK1/ACC | Positive, orthogonal anchor | Cross-cohort and cross-assay directional corroboration against a Brazilian qRT-PCR study | Replication of the original assay, threshold or patient-level result |
| BIRC5 pan-cancer | Positive but heterogeneous | Within-TCGA agreement with a broad adverse literature pattern | Universal pan-cancer effect or external validation |
| BAP1/PRAME UVM | Sole non-confirmatory case | RNA grouping does not establish the continuous interaction or reproduce IHC | Refutation of the published protein-assay result |

Only ACC uses a literature cohort and assay independent of the TCGA-TRACE
analysis. Even this is orthogonal directional corroboration, not an external
dataset rerun, because the Brazilian patient-level data were not reanalyzed in
TCGA-TRACE.

The four cases were selected after frozen outputs were available. This is
acceptable for exposition only because the full 11-scenario panel and all 17
Paper Examples remain reported and the selected cases do not define a
multiplicity family.

## Improvements Now Reflected

- endpoint-specific TCGA-CDR handling and numeric QC;
- expression-complete one-sample-per-participant construction;
- age and exact user-selected clinical adjustment;
- continuous Cox and restricted cubic splines before grouped sensitivities;
- marker-term and global PH diagnostics without binary exclusion;
- fixed, group-independent RMST horizon with support checks;
- sparse-data information warnings and Firth sensitivities;
- within-scenario Holm correction for grouped rules and separate continuous
  and nonlinearity families;
- quantified maxstat amplification and post-selection cautions;
- competing-risk CIF, Gray and Fine--Gray outputs;
- common-scale REML/HKSJ pan-cancer synthesis with prediction intervals;
- prespecified multiverse and explicit post hoc session-history boundaries;
- exact participant, expression-component and source provenance;
- standalone R capsules, quantity-aware rerun tolerances and mutation tests;
- detached Ed25519 receipts with a bounded threat model;
- runtime, concurrency and browser evidence;
- one four-page main figure and complete evidence in eight supplementary tables;
- strength-first prior-art positioning and calibrated biological case language.

## Remaining Scientific Risks

1. There is no independent cohort analyzed end to end by TCGA-TRACE. ACC is the
   best orthogonal anchor, but it is a directional comparison to published
   qRT-PCR results rather than a patient-level external replication.
2. The biological cases are post hoc explanatory selections. The complete
   panel limits selective presentation but does not make the case set
   prospective.
3. cBioPortal comparisons share TCGA data and test pipeline concordance, not
   biological independence.
4. The 20-resource landscape is source-based. No independent, versioned UI
   feature audit was performed, so product-wide absence claims remain
   prohibited.
5. Retrospective bulk RNA associations remain vulnerable to subtype, purity,
   treatment and unmeasured confounding despite age and clinical adjustment.
6. Maxstat grouped effects and RMST remain post-selection even when the
   rank-test p-value is adjusted.
7. The current supplement is complete but long at 20 pages. This is not an
   editorial blocker, but further compression should remove repetition rather
   than evidence.
8. Owner metadata, license, immutable archive DOI and exact tagged deployment
   remain release blockers and are not scientific results.

## Highest-Value Next Actions

1. Have all authors independently verify and rewrite scientific claims,
   especially the case-study interpretations and comparator descriptions.
2. Add one genuinely external patient-level cohort that can be analyzed end to
   end under a frozen request, preferably reproducing the ACC score or another
   prespecified marker/signature.
3. If no external cohort can be added before submission, retain the current
   wording and make the absence explicit in the cover letter.
4. Run a dated, reproducible interface audit only if the paper needs
   product-level feature comparisons; otherwise keep the current source-based
   positioning.
5. Complete the owner-controlled release handoff: correspondence, CRediT, AI
   disclosure, OSI license, support commitment, exact tag/deployment and Zenodo
   DOI.

## Verification Snapshot

- Publication tests: 135 passed.
- Editorial compliance: one main vector figure, no main tables, eight
  supplementary tables and a 4/4-page OUP preview.
- Supplement: 20 pages, no figures.
- Submission artifact gate: 109/109 available.
- Open release decisions: 10 owner decisions across 30 synchronized
  occurrences.
- Remote CI caveat: run `30188451618` failed only the clean-capsule job at
  documentation-only commit `593c6d6`; the exact command passed locally from
  an isolated worktree of that commit. The failure is not considered closed
  until a subsequent hosted run passes.
