#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
env_file="$repo_dir/.env"
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

admin_password=$(openssl rand -hex 32)
runtime_password=$(openssl rand -hex 32)
temporary_file=$(mktemp "$repo_dir/.env.security.XXXXXX")
trap 'rm -f "$temporary_file"' EXIT HUP INT TERM

if [ -f "$env_file" ]; then
  awk '
    !/^POSTGRES_ADMIN_PASSWORD=/ && !/^POSTGRES_RUNTIME_PASSWORD=/ { print }
  ' "$env_file" > "$temporary_file"
fi
{
  printf '\nPOSTGRES_ADMIN_PASSWORD=%s\n' "$admin_password"
  printf 'POSTGRES_RUNTIME_PASSWORD=%s\n' "$runtime_password"
} >> "$temporary_file"
chmod 600 "$temporary_file"

printf "ALTER ROLE tcga PASSWORD '%s';\n" "$admin_password" \
  | docker exec -i "$postgres_container" \
      psql --no-psqlrc --set=ON_ERROR_STOP=1 -U tcga -d tcga_explorer \
      >/dev/null

mv "$temporary_file" "$env_file"
trap - EXIT HUP INT TERM
echo "TRACE database credentials were rotated and stored in .env (mode 600)."
