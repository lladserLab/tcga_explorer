# Security operations

TRACE Explorer is a public research service, not a clinical system. This file
records the operational controls that must remain true for the paper release.

## Deployment boundary

- Publish only the edge Nginx port, bound to `127.0.0.1` when Apache or another
  host reverse proxy terminates public TLS.
- PostgreSQL is reachable only on the internal `data` network. Neither the
  backend nor the frontend publishes a host port; browser traffic enters through
  the rate-limited edge proxy on the project application network.
- The backend uses the non-owner, non-superuser `trace_app` role. Schema
  creation, Alembic and grants run once in the short-lived `migrate` service
  with the rotated PostgreSQL bootstrap role; that credential is not present in
  the backend or worker containers.
- Containers use read-only root filesystems where practical, drop Linux
  capabilities, set `no-new-privileges`, and have explicit memory, CPU and PID
  ceilings.

## Secrets

Run `scripts/rotate_database_credentials.sh` on the deployment host before the
first hardened restart and after suspected disclosure. It generates independent
64-character credentials, rotates the live database owner password, and writes
only to the Git-ignored `.env` file with mode `0600`. Never paste `.env` into an
issue, manuscript bundle or diagnostic log.

Attestation private keys and private-dataset access tokens are also secrets.
The server stores only SHA-256 token digests. The browser keeps the returned
private-dataset token in session storage, so closing the tab intentionally ends
local access.

## Private uploads

- Uploads must be de-identified and expire after the configured retention time.
- The dataset ID is an identifier, not an authorization credential. REST and MCP
  requests must also supply `X-TRACE-Dataset-Token` or the equivalent Bearer
  token.
- Private responses use `Cache-Control: private, no-store`; upload directories
  use mode `0700` and normalized files use mode `0600`.
- Raw uploaded files are deleted after normalization. Compute artifacts retain
  the same token boundary as their source dataset.

## Backup and recovery

Create a compressed, checksum-protected logical backup with:

```bash
./scripts/backup_database.sh
```

Validate an archive without restoring it with:

```bash
./scripts/verify_database_backup.sh \
  release_backups/database/tcga_explorer-YYYYMMDDTHHMMSSZ.dump
```

Backups are local, Git-ignored and mode `0600`. Copy them to an encrypted,
access-controlled destination according to the host's retention policy. A full
restore is deliberately not automated in the application repository because it
replaces live state. Perform restore drills in an isolated PostgreSQL instance,
verify Alembic head, row counts and representative analysis records, then record
the drill date and operator.

## Release checks

Before a public release:

1. Run backend, frontend and browser tests.
2. Validate `docker compose config` and both Nginx configurations.
3. Scan final images and dependency lockfiles; triage every high or critical
   finding rather than relying on a total count alone.
4. Confirm legacy compute routes return 404, quotas use the edge-resolved IP,
   and private resources reject missing and incorrect tokens.
5. Verify response security headers, CORS from an allowed and a disallowed
   origin, upload size rejection, database-role privileges and one fresh backup.

## Known image finding

The paper-release scan reports no fixable high or critical vulnerabilities in
the TRACE backend or frontend images. The pinned official PostgreSQL 16 image
still reports Go standard-library findings in `/usr/local/bin/gosu`. That helper
runs only during container startup to drop from the image entrypoint user to the
unprivileged PostgreSQL user; it is not a network service or application
dependency. PostgreSQL remains isolated on the internal `data` network, without
a published host port. Reassess this finding whenever the pinned PostgreSQL
digest changes; do not suppress it globally in the scanner.
