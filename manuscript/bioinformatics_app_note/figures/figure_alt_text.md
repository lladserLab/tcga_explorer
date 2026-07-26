# Figure 1 Alt Text

Flow diagram from versioned TCGA RNA, TCGA-CDR endpoints and user parameters
through deterministic participant-level cohort construction and three analysis
branches: single gene or signature, crossed markers or signatures, and
pan-cancer primary continuous Cox models with parallel ordinal stage/grade
sensitivity. A reporting-contract panel states that cohort decisions fix the
endpoint and sample rule and report patient flow, model decisions make
continuous effects primary and grouped analyses sensitivities, and family
decisions freeze a grid before execution and report its complete ledger and
multiplicity adjustment. The request can declare an
endpoint-by-scoring-by-cutpoint family, and the branches feed a specification
curve plus explicit cutpoint, RMST, proportional-hazards,
events-per-parameter and Firth-sensitivity diagnostics.
The final run record contains plots, the complete family ledger, selected
participant records, expression components,
source identifiers, methods, versions, structured audit JSON, SHA-256
checksums and a detached Ed25519 server receipt. A provenance rail connects
source-artifact, request, participant, scoring and result hashes to the signed
receipt, with an arrow indicating that scores and statistical outputs can be
reconstructed from the audited record.
