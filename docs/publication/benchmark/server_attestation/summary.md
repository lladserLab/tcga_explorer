# Server Attestation Benchmark

Status: **passed**.

## Frozen Subject

- Type: `survival_analysis`
- ID: `ba68bc76e27641268a6566d72324c789`
- Audit schema: `tcga-trace-analysis-audit-v4`
- Audit SHA-256: `1c1d83e143b2af02db26ade89bfdd89fbaff03de7be8afd5600849157edf77e0`
- Reproducibility hash: `6df7bcf7cfd814d1100f1e9701571c2facf11ae7469d1234c7452f3479fc592b`
- Ed25519 key ID: `ed25519-sha256-5f6765ef7ec0845078c4344f2542c945492bea3f38427d6ab909def3e9c01643`

## Acceptance Controls

- Exact report verifies: `true`
- Altered report is rejected: `true`
- Recomputed unsigned digests cannot forge the signature: `true`

The receipt establishes server origin for the exact audit bytes only when the public key is trusted through the declared HTTPS issuer or an independently archived matching fingerprint. It does not establish scientific correctness, prespecification or append-only publication time.
