#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
TEX_IMAGE="${TEX_IMAGE:-texlive/texlive@sha256:1a1b8588cd73ac33fe1d7722c4065b3e6eaa3f3a20fb54d2934e42310264d134}"
export TEX_IMAGE

metadata_args=()
browser_args=()
if [[ "${1:-}" == "--strict-owner-metadata" ]]; then
  metadata_args=(--strict)
  browser_args=(--require-final)
  shift
fi
if [[ "$#" -gt 0 ]]; then
  echo "Usage: $0 [--strict-owner-metadata]" >&2
  exit 2
fi

python3 -m py_compile \
  scripts/tcga_trace_cli.py \
  scripts/publication/apply_submission_metadata.py \
  scripts/publication/build_oup_preview.py \
  scripts/publication/build_submission_archive.py \
  scripts/publication/capture_reviewer_screenshots.py \
  scripts/publication/check_editorial_compliance.py \
  scripts/publication/check_project_identity.py \
  scripts/publication/check_submission_artifacts.py \
  scripts/publication/check_submission_metadata.py \
  scripts/publication/export_immune_atlas_benchmark.py \
  scripts/publication/finalize_submission_package.py \
  scripts/publication/run_cutpoint_benchmark.py \
  scripts/publication/run_single_gene_benchmark_suite.py \
  scripts/publication/run_feature_benchmarks.py \
  scripts/publication/run_reproducibility_benchmark.py \
  scripts/publication/run_server_attestation_benchmark.py \
  scripts/publication/run_browser_compatibility.py \
  scripts/publication/run_runtime_benchmark.py \
  scripts/publication/run_clean_reproduction_benchmark.py \
  scripts/publication/run_statistical_calibration.py \
  scripts/publication/run_skcm_sample_rule_sensitivity.py \
  scripts/publication/export_data_snapshot_manifest.py \
  scripts/publication/verify_submission_archive.py \
  scripts/publication/verify_reproducibility_bundle.py \
  scripts/publication/write_license_template.py

if [[ "${#metadata_args[@]}" -gt 0 ]]; then
  scripts/publication/check_submission_metadata.py "${metadata_args[@]}"
else
  scripts/publication/check_submission_metadata.py
fi

scripts/publication/check_project_identity.py

docker compose run --rm --no-deps \
  -v "$PWD/backend/tests:/app/tests:ro" \
  backend pytest -q /app/tests

docker compose run --rm --no-deps \
  -v "$PWD:/workspace:ro" \
  -w /workspace \
  backend pytest -q -p no:cacheprovider scripts/publication/tests

docker compose run --rm --no-deps \
  -v "$PWD:/workspace:ro" \
  -w /workspace \
  backend pytest -q -p no:cacheprovider scripts/tests

docker build -f frontend/Dockerfile -t tcga-trace-frontend-check .

manifest_tmp="$(mktemp)"
archive_tmp=""
trap 'rm -f "$manifest_tmp" ${archive_tmp:+"$archive_tmp"}' EXIT
scripts/publication/export_data_snapshot_manifest.py --hash-count-matrices --output "$manifest_tmp"
python3 - "$manifest_tmp" docs/publication/benchmark/data_snapshot_manifest.json <<'PY'
import json
import sys
from pathlib import Path

generated = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
tracked = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
if generated["manifest_hash"] != tracked["manifest_hash"]:
    raise SystemExit(
        "Data snapshot manifest hash mismatch: "
        f"generated {generated['manifest_hash']} != tracked {tracked['manifest_hash']}. "
        "Run scripts/publication/export_data_snapshot_manifest.py --hash-count-matrices "
        "and update the submission hash records."
    )
print(f"Data snapshot manifest hash OK: {tracked['manifest_hash']}")
PY

scripts/publication/run_reproducibility_benchmark.py \
  --docker-compose-service backend

docker compose run --rm --no-deps \
  -v "$PWD:/workspace:ro" \
  -w /workspace \
  backend python3 scripts/publication/run_server_attestation_benchmark.py --check-only

scripts/publication/run_clean_reproduction_benchmark.py --check-only

scripts/publication/run_statistical_calibration.py --check-only
scripts/publication/run_runtime_benchmark.py --check-only
if [[ "${#browser_args[@]}" -gt 0 ]]; then
  scripts/publication/run_browser_compatibility.py --check-only "${browser_args[@]}"
else
  scripts/publication/run_browser_compatibility.py --check-only
fi

python3 - docs/publication/benchmark/lihc_cdc20_os_cutpoint_benchmark/benchmark_results.raw.json <<'PY'
import json
import sys
from pathlib import Path

record = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
median = next(
    item["result"]
    for item in record["results"]
    if item.get("result", {}).get("cutpoint_method") == "median"
)
rmst = median["metrics"]["rmst"]
fractions = [round(float(item["tau_fraction"]), 2) for item in rmst.get("tau_sensitivity", [])]
if fractions != [0.75, 0.9, 1.0]:
    raise SystemExit(f"Unexpected RMST tau sensitivity fractions: {fractions}")
if not rmst.get("tau_definition", {}).get("cutpoint_independent"):
    raise SystemExit("RMST tau is not marked as cutpoint independent")
print("RMST tau sensitivity OK: 0.75, 0.90, 1.00")
PY

python3 - docs/publication/benchmark/immune_pancancer_atlas_v2_1/atlas_summary.json <<'PY'
import json
import sys
from pathlib import Path

record = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected_hash = "4d942e93715ec953f0501b13a818d2f19e34f21d851367057924f0af3c2d0252"
assert record["headline"]["immune_genes"] == 3118
assert record["audit"]["expression_matrix_count"] == 32
assert record["audit"]["reproducibility_hash"] == expected_hash
print(f"ImmPort atlas audit hash OK: {expected_hash}")
PY

python3 - docs/publication/benchmark <<'PY'
import csv
import math
import sys
from pathlib import Path

root = Path(sys.argv[1])
missing = []
for path in sorted(root.glob("*_cutpoint_benchmark/summary.csv")):
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("method") != "maxstat":
                continue
            try:
                value = float(row.get("maxstat_corrected_p_value") or "nan")
            except ValueError:
                value = math.nan
            if not math.isfinite(value) or row.get("maxstat_corrected_p_status") != "completed":
                missing.append(str(path))
if missing:
    raise SystemExit("Missing completed maxstat corrected p-values in: " + ", ".join(missing))
print("Maxstat corrected p-values OK")
PY

make -C manuscript/bioinformatics_app_note clean all
scripts/publication/check_editorial_compliance.py

docker run --rm \
  -e LC_ALL=C \
  -e LANG=C \
  -v "$PWD/manuscript/bioinformatics_app_note":/work \
  -w /work \
  "$TEX_IMAGE" \
  texcount -inc -brief main.tex supplementary.tex

scripts/publication/check_submission_artifacts.py
archive_tmp="$(mktemp)"
if [[ "${#metadata_args[@]}" -gt 0 ]]; then
  scripts/publication/build_submission_archive.py --strict-owner-metadata --output "$archive_tmp" >/dev/null
else
  scripts/publication/build_submission_archive.py --output "$archive_tmp" >/dev/null
fi
scripts/publication/verify_submission_archive.py "$archive_tmp"

git diff --check
