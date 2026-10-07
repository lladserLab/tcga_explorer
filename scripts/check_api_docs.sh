#!/usr/bin/env bash
# Isolated real-schema/CSP browser test. No databases, public jobs or host ports.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
probe_name="trace-api-docs-check-$$"
image="${1:-trace-explorer-ci-backend:local}"
cleanup() { docker stop "$probe_name" >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker run --rm -d --name "$probe_name" \
  -v "$ROOT:/workspace:ro" -w /workspace \
  -e PYTHONPATH=/workspace/backend:/workspace:/app \
  --entrypoint python3 "$image" \
  -m uvicorn backend.tests.api_docs_test_server:app --host 0.0.0.0 --port 8000 >/dev/null
docker exec "$probe_name" curl --fail --silent --show-error \
  --retry 20 --retry-connrefused --retry-delay 1 --max-time 10 \
  http://127.0.0.1:8000/tcga_explorer/api/openapi.json -o /dev/null
docker run --rm --network "container:$probe_name" \
  -v "$ROOT:/workspace:ro" \
  -e TRACE_DOCS_URL=http://127.0.0.1:8000/tcga_explorer/ \
  -e NODE_PATH=/tmp/node_modules \
  mcr.microsoft.com/playwright:v1.62.1-noble@sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e \
  bash -lc 'cd /tmp && npm install --no-save --ignore-scripts @playwright/test@1.62.1 >/dev/null && node /workspace/scripts/check_api_docs_browser.cjs'
