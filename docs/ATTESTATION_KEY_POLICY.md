# TCGA-TRACE Attestation Key Policy

TCGA-TRACE signs each generated audit report with an Ed25519 key. A receipt is
verifiable only when the exact public-key fingerprint is trusted independently
of the exported report.

## Published Key

The manuscript benchmark key has SHA-256 fingerprint:

`5f6765ef7ec0845078c4344f2542c945492bea3f38427d6ab909def3e9c01643`

The complete public-key document is included in the archived benchmark and
will be deposited with the versioned software release. The live HTTPS API is a
discovery mechanism; the archived fingerprint is the long-term trust anchor.

## Routine Rotation

Routine rotation creates a new active key. Previous public-key documents remain
available by immutable key ID and are labelled `retired`. A retired key remains
acceptable for verifying receipts issued while that key was active.

## Revocation

When compromise or unauthorized use is suspected, the affected public-key
document is labelled `revoked` with a dated incident notice in the next
versioned release. The verifier may confirm that the historical signature is
cryptographically valid, but it fails the trust check for a revoked key.
Revocation cannot prove which signatures were created before compromise; users
must consult the dated release notice.

## Scope

Successful verification establishes server origin for the exact signed audit
bytes under a trusted active or retired key. It does not establish scientific
correctness, prespecification, append-only publication time, or absence of
other analyses.
