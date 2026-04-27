#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR" || exit 1
mkdir -p logs

MAX_WORKERS="${TCGA_SYNC_MAX_WORKERS:-10}"

docker compose run --rm updater apply --source all --max-workers "$MAX_WORKERS" --reimport
status=$?

if [ "$status" -eq 20 ]; then
  docker compose up -d backend frontend nginx
  exit 0
fi

if [ "$status" -eq 0 ]; then
  exit 0
fi

exit "$status"
