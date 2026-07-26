# Third Review Implementation Log

Status date: 2026-07-26.

This ledger records the response to the third external review of the
Bioinformatics Application Note. `Complete` means that implementation,
regenerated evidence and manuscript wording agree. `Deferred` means that the
gap remains visible in Future Plans and is not used to support a current claim.

## Review Ledger

| ID | Status | Review request | Resolution and evidence |
| --- | --- | --- | --- |
| R3-01 | Complete | Compare continuous and grouped power under linear PH | The 2,000-replicate linear-PH simulation now reports continuous Cox (99.2%), Lau94 maxstat (94.3%), median (93.9%), upper quartile (93.5%), outer quartiles (97.8%) and the grouped Holm family (96.4%), with Wilson intervals. |
| R3-02 | Complete | State the default user path | Help, Methods and the supplement state the exact default: one gene, OS, log2(TPM+1), no filters, age adjustment, continuous Cox first, median grouping as sensitivity, and automatic audit/capsule/receipt exports. The 72-cell multiverse remains an explicit action. |
| R3-03 | Complete | Remove ambiguity around median and maxstat amplification | Results distinguish the median-split rule from the median summary statistic and identify UVM/BAP1 as the non-estimable maxstat case because all 21 DSS events fall in one group. |
| R3-04 | Complete | Preserve long-term Ed25519 verification | The public-key fingerprint is printed in the manuscript and frozen evidence, and `docs/ATTESTATION_KEY_POLICY.md` defines active, retired and revoked key behavior. Verification rejects revoked keys. |
| R3-05 | Complete | Interpret Wilson intervals and conservative grouped inference | Calibration reports Wilson intervals for every rejection rate, states whether they include 0.05 and explains that Holm and Lau94 are conservative under the tested dependence structure; absence of grouped support is not treated as evidence of no effect. |
| R3-06 | Complete | Restore missing methodological and comparator citations | The manuscript cites specification curves, multiverse analysis, cBioPortal, Grambsch--Therneau, Harrell, KM Plotter and DoSurvive, alongside GEPIA2, cSurvival and PESSA. |
| R3-07 | Complete | Declare license, API, canonical name and version caveat | The repository and frontend packages use the MIT license; Methods identifies the OpenAPI contract; TCGA-TRACE is the canonical product name while the repository slug and `/tcga_explorer` path are declared compatibility surfaces; Future Plans retains the untested cross-version stability caveat. |
| R3-08 | Complete | Reorder and sharpen the abstract | The two-sentence Summary leads with the continuous-first reporting contract, null calibration (5.0%), naive versus Lau94 maxstat rejection (39.6% versus 1.8%), linear-PH power (99.2%) and six clean-container reruns. |
| R3-09 | Complete by constrained alternative | Add a main-text reporting-contract table | The four-page format and one-figure editorial constraint are preserved by integrating the contract as panel D of Figure 1 rather than adding a second display item. The complete empirical matrices remain in the supplement. |
| R3-10 | Complete | Reconcile spline information requirements and explain CA9 | Restricted cubic splines now require at least 30 events for three spline parameters and report events per parameter. UVM/BAP1 is skipped at 21 events. The CA9/KIRC percentile profile is reported from P5 to P95 and interpreted as nonlinear rather than as a single prognostic HR. |
| R3-11 | Complete | Make the early/late PH summary reproducible and less arbitrary | The primary counting-process contrast retains a fixed, declared two-year split and now reports marker-by-period Wald inference. Prespecified one- and five-year sensitivities are exported beside it, and the manuscript labels the two-period model as a coarse approximation rather than a smooth time-varying effect. |
| R3-12 | Complete | Report competing-risk results for UVM/BAP1 | The case reports 80 patients, 21 DSS events, two competing deaths, Gray p=0.000457, grouped Fine--Gray HR 0.174 (0.059--0.516) and continuous Fine--Gray HR per SD 0.504 (0.375--0.678). |
| R3-13 | Deferred | Extend calibration to n approximately 80 and multiple observed cohorts | Current calibration remains 2,000 replicates at n=300 plus one cohort-preserving permutation design. Small-event and multi-cohort operating characteristics are stated in Future Plans and are not implied by the present calibration claims. |
| R3-14 | Deferred | Publish a 33-cohort covariate-completeness table | The application exposes cohort metadata coverage and every fitted model reports complete-case N, events, parameters and adequacy. A frozen age/stage/grade/gender/race matrix for all 33 cohorts is not yet included in the article package and remains future work. |
| R3-15 | Partially complete; saturation test deferred | Specify deployed queue behavior and test saturation | The runtime benchmark records host and Docker resources, global concurrency two, queue/wall/compute times, batch and multiverse limits. A multi-client saturation, timeout and rate-limit benchmark on the final public deployment remains deferred and is not represented by the two-job overlap probe. |

## Validation Snapshot

- 2,000 observed-cohort permutations and 2,000 simulations for each declared
  mechanism were regenerated.
- All 11 scenarios and four grouped rules were regenerated under analysis
  pipeline `expression-complete-integrity-contract-v6.13`.
- Three frozen capsules passed on native arm64 and Linux/amd64: six of six
  isolated reruns.
- Server attestation accepted the exact report and rejected altered,
  recomputed-unsigned and revoked-key controls.
- The backend, publication and standalone test suites passed in the full
  pre-submission gate; the frontend production image also built successfully.
- Editorial compliance reports one integrated vector figure, no main-text
  tables, eight supplementary tables and a four-page OUP preview.
- The submission artifact gate reports 109 of 109 required artifacts present.

## Remaining Release Decisions

The scientific and software changes above do not resolve author-controlled
submission metadata. Corresponding-author details, submitting author and ORCID,
CRediT roles, AI-use disclosure, independent author review, support ownership,
the two-year service commitment, exact-tag browser verification and the Zenodo
DOI must be supplied before a release archive can be called submission-ready.
