# Apache deployment for apps.cienciavida.org

`apps.cienciavida.org` terminates HTTPS with Apache. Run the Docker stack on host port `3000` and proxy only the `/tcga_explorer/` prefix to the container Nginx.

## Docker app

Create `.env` on the host running Docker:

```env
VITE_BASE_PATH=/tcga_explorer/
VITE_API_BASE_URL=/tcga_explorer
PUBLIC_BASE_URL=https://apps.cienciavida.org/tcga_explorer
PUBLIC_PATH_PREFIX=/tcga_explorer
APP_RELEASE_COMMIT=FULL_40_CHARACTER_GIT_COMMIT
APP_RELEASE_REF=EXACT_RELEASE_TAG
TCGA_EXPLORER_HTTP_BIND=127.0.0.1
TCGA_EXPLORER_HTTP_PORT=3000
```

The loopback bind is required when Apache runs on the same host. If Apache is
on another host, bind to a specific private interface and restrict port 3000
with the host firewall; do not expose the container proxy directly to the
internet.

Start or rebuild the app:

```bash
grep -Fx "APP_RELEASE_COMMIT=$(git rev-parse HEAD)" .env
grep -Fx "APP_RELEASE_REF=$(git describe --tags --exact-match HEAD)" .env
docker compose up -d --build
```

Do not leave the two release values as `development` in a submitted
deployment. They are returned by `/api/v1/health`, and the final
cross-browser gate rejects an HTTPS server whose reported commit differs from
the clean tagged checkout.

Verify from the same host:

```bash
curl -I http://127.0.0.1:3000/tcga_explorer/
curl http://127.0.0.1:3000/tcga_explorer/api/v1/health
curl -I http://127.0.0.1:3000/tcga_explorer/api/docs
```

## Apache virtual host

Enable the proxy modules if needed:

```bash
sudo a2enmod proxy proxy_http headers rewrite
sudo systemctl reload apache2
```

Add these directives inside the SSL virtual host for `apps.cienciavida.org`:

```apache
ProxyPreserveHost On
ProxyRequests Off
ProxyTimeout 600
RequestHeader set X-Forwarded-Proto "https"

RewriteEngine On
# An origin-relative 308 preserves the request method and existing query.
# The browser also retains a fragment because it never sends it to Apache.
RewriteRule ^/?tcga_explorer$ /tcga_explorer/ [R=308,L,NE]

ProxyPass        /tcga_explorer/ http://127.0.0.1:3000/tcga_explorer/ retry=0 timeout=600
ProxyPassReverse /tcga_explorer/ http://127.0.0.1:3000/tcga_explorer/

<Location "/tcga_explorer/api/v1/">
    LimitRequestBody 67108864
</Location>

<Location "/tcga_explorer/mcp">
    LimitRequestBody 67108864
</Location>
```

The 64 MiB transport limit accommodates the bounded inline external-covariate
schema, including public batch requests that repeat one dataset. Application
validation still limits each dataset to 10 variables and 2,000 unique TCGA
participants.

Reload Apache:

```bash
sudo apachectl configtest
sudo systemctl reload apache2
```

The frontend build uses `/tcga_explorer/` as its asset base and `/tcga_explorer/api` as its API base, so Apache does not need a global `/api/` proxy that could conflict with other apps on the same domain.

Verify the canonical redirect before testing the application. The `Location`
header must remain origin-relative and must retain the query string:

```bash
curl -sS -D - -o /dev/null \
  'https://apps.cienciavida.org/tcga_explorer?view=help'
# Expected: HTTP 308 and Location: /tcga_explorer/?view=help

curl -sS -D - -o /dev/null \
  'https://apps.cienciavida.org/tcga_explorer/methods/signature-scoring?source=deployment'
# Expected: HTTP 308 and a relative Location ending in
# /methods/signature-scoring/?source=deployment

curl -I \
  'https://apps.cienciavida.org/tcga_explorer/methods/signature-scoring/'
# Expected: HTTP 200, text/html and Cache-Control: no-cache
```

The same prefix proxy carries the Streamable HTTP MCP endpoint. After reload,
verify the public API, OpenAPI document, and MCP URL:

```bash
curl https://apps.cienciavida.org/tcga_explorer/api/v1/health
curl -I https://apps.cienciavida.org/tcga_explorer/api/openapi.json
curl -i \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"deployment-check","version":"1.0"}}}' \
  https://apps.cienciavida.org/tcga_explorer/mcp
```

Confirm that the health payload reports the expected full commit and tag under
`release.commit` and `release.ref`.
