# Apache deployment for apps.cienciavida.org

`apps.cienciavida.org` terminates HTTPS with Apache. Run the Docker stack on an internal host port and proxy only the `/tcga_explorer/` prefix to the container Nginx.

## Docker app

Create `.env` on the host running Docker:

```env
VITE_BASE_PATH=/tcga_explorer/
VITE_API_BASE_URL=/tcga_explorer
TCGA_EXPLORER_HTTP_BIND=127.0.0.1
TCGA_EXPLORER_HTTP_PORT=18080
```

Start or rebuild the app:

```bash
docker compose up -d --build
```

Verify from the same host:

```bash
curl -I http://127.0.0.1:18080/tcga_explorer/
curl http://127.0.0.1:18080/tcga_explorer/api/health
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

RedirectMatch 301 ^/tcga_explorer$ /tcga_explorer/

ProxyPass        /tcga_explorer/ http://127.0.0.1:18080/tcga_explorer/ retry=0 timeout=600
ProxyPassReverse /tcga_explorer/ http://127.0.0.1:18080/tcga_explorer/
```

Reload Apache:

```bash
sudo apachectl configtest
sudo systemctl reload apache2
```

The frontend build uses `/tcga_explorer/` as its asset base and `/tcga_explorer/api` as its API base, so Apache does not need a global `/api/` proxy that could conflict with other apps on the same domain.
