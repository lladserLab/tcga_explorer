# Runtime and concurrency benchmark

- Run ID: `20260725T202243684364Z`
- Generated: `2026-07-25T20:27:23.609628+00:00`
- API: `http://192.168.1.31:3000/tcga_explorer`
- Source commit: `ac32eb643e6c60b0281881cd879ce0d6e88b2843`
- Dirty worktree: `True`
- Host: Mac13,2 / Apple M1 Ultra / 20 logical CPUs / 65536 MiB
- Docker engine: 29.4.1 / aarch64 / 20 CPUs / 7934 MiB
- Pipeline versions: `{"analysis": "expression-complete-interpretation-contract-v6.6", "combined_signatures": "expression-complete-interpretation-contract-v3.8", "immune_atlas": "immune-pancancer-primary-plus-ordinal-sensitivity-cox-audit-v2.1", "multiverse": "prespecified-multiverse-interpretation-contract-v1.5", "pancancer": "common-scale-reml-hksj-interpretation-contract-v2.9"}`
- Data manifest: `6964900d3c7d20f9fcefa8c4c78399bbe12a29dc9e6d23a25a0929f9bb180264`

## Definitions

- **Uncached:** No completed compute job or analysis artifact matched the exact request. A unique display-only plot title or session label forced a cache miss without changing the statistical specification.
- **Cached Repeat:** The exact single-analysis request was resubmitted after completion and returned the retained compute job.
- **Wall Time:** Client-observed time from the start of POST submission through the first terminal job response.
- **Queue Wait:** Job started_at minus created_at.
- **Compute Time:** Job completed_at minus started_at.
- **Memory:** Backend plus worker Docker cgroup memory. Absolute peak includes resident baseline; delta is peak minus pre-request baseline.
- **Cold Scope:** Cold denotes an analysis-result cache miss, not a cold operating-system page cache or a fresh TCGA data import.

## Queue contract

- Global worker concurrency: 2
- Queue capacity: 50
- Active jobs per anonymous client: 5
- Hourly limits per client: `{"analysis_or_combined": 10, "batch": 2, "multiverse": 1, "pancancer": 2}`
- Request-size limits: `{"batch_analyses": 25, "multiverse_specifications": 72}`
- Public batch children execute serially inside one worker slot, so a batch never bypasses the global concurrency ceiling.

## Results

| Workflow | Units | Cached | Wall (s) | Queue (s) | Compute (s) | Peak MiB | Delta MiB | Status |
| --- | ---: | :---: | ---: | ---: | ---: | ---: | ---: | --- |
| Single analysis, uncached result | 1 | no | 5.121 | 0.939 | 3.202 | 553.6 | 330.0 | completed |
| Single analysis, exact cached repeat | 1 | yes | 0.037 | -- | -- | 224.7 | 0.000 | completed |
| Two independent single analyses | 2 | no | 5.231 | 0.938 | 3.398 | 775.7 | 552.0 | completed |
| Public batch, 10 analyses | 10 | no | 32.47 | 0.216 | 31.78 | 561.7 | 335.4 | completed |
| Prespecified multiverse, 72 cells | 72 | no | 218.8 | 0.487 | 217.9 | 568.9 | 341.1 | completed |
| Pan-cancer scan, 33 requested cohorts | 33 | no | 7.180 | 0.224 | 6.537 | 439.9 | 213.2 | completed |

Memory is the aggregate backend plus worker Docker cgroup usage. The approximately one-second sampler can miss sub-second spikes; reported values are observed peaks rather than allocator maxima.
