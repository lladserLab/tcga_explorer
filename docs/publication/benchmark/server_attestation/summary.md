# Server Attestation Benchmark

Status: **passed**.

## Frozen Subject

- Type: `survival_analysis`
- ID: `3695c8ead2134ecb9b2d10c72544c19e`
- Audit schema: `tcga-trace-analysis-audit-v4`
- Audit SHA-256: `903155badd8b3e94e5f604b74310607f6161ed2646128b901620f5b17c3188bd`
- Reproducibility hash: `6549cad343a51ba60d02e661f2b1d1e4afec7fc6593a9ec406eae0ebafbd9117`
- Ed25519 key ID: `ed25519-sha256-5f6765ef7ec0845078c4344f2542c945492bea3f38427d6ab909def3e9c01643`

## Acceptance Controls

- Exact report verifies: `true`
- Altered report is rejected: `true`
- Recomputed unsigned digests cannot forge the signature: `true`

The receipt establishes server origin for the exact audit bytes only when the public key is trusted through the declared HTTPS issuer or an independently archived matching fingerprint. It does not establish scientific correctness, prespecification or append-only publication time.
