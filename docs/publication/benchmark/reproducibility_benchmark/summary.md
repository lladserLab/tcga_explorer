# Audit Reconstruction Benchmark

This benchmark tests reproducibility as an executable contract, not as the presence of downloadable files.
The integrity threat model is accidental drift, corruption or incomplete transfer. Unsigned hashes do not establish authenticity against an exporter who can recompute them.

| Analysis | Type | Patients | Internal checks | Numeric comparisons | Max abs. error | Max rel. error | Isolated reruns | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Single gene | single | 365 | 40/40 | 170 | 1.14e-13 | 4e-14 | 2/2 | passed |
| Weighted signature | weighted | 79 | 43/43 | 131 | 2.84e-14 | 7.39e-15 | 2/2 | passed |
| Two signatures | combined_signatures | 80 | 42/42 | 159 | 4.06e-14 | 5.82e-14 | 2/2 | passed |

## Clean-Container Reproduction

- Environments: 2 (amd64, arm64)
- Capsule reruns: 6/6
- Clean negative controls: 2/2
- Isolation: pinned environment; no network, application source, TCGA matrix or database.

## Integrity Boundary

- Baseline reproducibility hash valid: yes
- Patient row tamper detected: yes
- Request tamper detected: yes
- Expression component tamper detected: yes
- Source provenance tamper detected: yes
- Plot outside reproducibility hash: yes
- Plot checksum tamper detected: yes
- Methodology outside reproducibility hash: yes
- Methodology checksum tamper detected: yes
- Generated at outside reproducibility hash: yes
- Quality metadata outside reproducibility hash: yes

- Boundary statement: The controls detect drift relative to recorded unsigned hashes. An exporter able to modify content and recompute every hash is outside scope; authenticity requires independent attestation.
