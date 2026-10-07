#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
backup_dir="$repo_dir/release_backups/database"
postgres_container=$(
  docker ps \
    --filter label=com.docker.compose.project=tcga_explorer \
    --filter label=com.docker.compose.service=postgres \
    --format '{{.ID}}' \
    | head -n 1
)

if [ -z "$postgres_container" ]; then
  echo "The running TRACE PostgreSQL container was not found." >&2
  exit 1
fi

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
target="$backup_dir/tcga_explorer-$timestamp.dump"
temporary="$target.part"
trap 'rm -f "$temporary"' EXIT HUP INT TERM

docker exec "$postgres_container" \
  pg_dump --username=tcga --dbname=tcga_explorer \
    --format=custom --compress=9 --no-owner --no-acl \
  > "$temporary"
docker exec -i "$postgres_container" pg_restore --list < "$temporary" >/dev/null
chmod 600 "$temporary"
mv "$temporary" "$target"
trap - EXIT HUP INT TERM
shasum -a 256 "$target" > "$target.sha256"
chmod 600 "$target.sha256"
echo "Verified database backup created: $target"
