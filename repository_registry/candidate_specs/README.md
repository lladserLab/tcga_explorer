# Candidate study specifications

This directory contains build-ready study contracts that have not been
downloaded, validated as immutable bundles, or promoted to the public TRACE
Explorer repository.

Files here may be passed explicitly to `repository build-study --spec`. They
must not be discovered by catalog synchronization or the pan-cancer study
universe registry. Promotion requires a successful source snapshot, bundle QC,
scientific review, and an explicit registry decision.

The 2026-08-20 batch pins source-side population counts so that a later build
fails closed if GDC or cBioPortal metadata drift before curation is completed.
