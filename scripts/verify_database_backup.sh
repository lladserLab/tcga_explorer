#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 release_backups/database/<backup>.dump" >&2
  exit 2
fi

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
backup_dir="$repo_dir/release_backups/database"
requested=$1
case "$requested" in
  /*) candidate=$requested ;;
  *) candidate="$repo_dir/$requested" ;;
esac

backup_dir_real=$(cd "$backup_dir" && pwd -P)
candidate_dir_real=$(cd "$(dirname "$candidate")" 2>/dev/null && pwd -P) || {
  echo "Backup directory does not exist." >&2
  exit 2
}
if [ "$candidate_dir_real" != "$backup_dir_real" ] || [ ! -f "$candidate" ]; then
  echo "Only regular files directly inside release_backups/database are accepted." >&2
  exit 2
fi

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

if [ -f "$candidate.sha256" ]; then
  (cd "$backup_dir_real" && shasum -a 256 -c "$(basename "$candidate.sha256")")
fi
docker exec -i "$postgres_container" pg_restore --list < "$candidate" >/dev/null
echo "Backup checksum and archive structure are valid: $candidate"
