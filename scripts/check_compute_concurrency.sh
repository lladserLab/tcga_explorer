#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT
readonly TEST_IMAGE="${1:-trace-explorer-ci-tests:local}"
readonly PG_IMAGE="postgres:16@sha256:95206741a5b214807675e14165369d05b93a9cf692223b616d07cca227e74b0b"
readonly TEST_CONTAINER="trace-lifecycle-test-$$"
cleanup() { docker stop "$TEST_CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT
# No published ports or external network. Trust applies only inside this
# temporary shared network namespace; production credentials are never read.
docker run -d --rm --name "$TEST_CONTAINER" --network none \
  --tmpfs /var/lib/postgresql/data:rw,nosuid \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=trace_lifecycle_test \
  "$PG_IMAGE" >/dev/null
for attempt in $(seq 1 30); do
  if docker exec "$TEST_CONTAINER" pg_isready -U postgres -d trace_lifecycle_test >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" -eq 30 ]]; then
    echo "Isolated PostgreSQL did not become ready" >&2
    exit 1
  fi
  sleep 1
done
docker run --rm --network "container:$TEST_CONTAINER" --entrypoint python3 \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/workspace/backend:/workspace:/app \
  -e TRACE_LIFECYCLE_TEST_POSTGRES_URL=postgresql+psycopg://postgres@127.0.0.1:5432/trace_lifecycle_test \
  -v "$ROOT:/workspace:ro" -w /workspace "$TEST_IMAGE" \
  -m pytest -q -p no:cacheprovider backend/tests/test_compute_postgres_concurrency.py
