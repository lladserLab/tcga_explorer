"""Same-origin documentation; no CDN, inline JavaScript or external validator."""
from html import escape
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

ASSETS = Path(__file__).parent / "static/api-docs"


def install_api_docs(app: FastAPI) -> None:
    # Explicit files also work when a reverse proxy strips root_path. A mounted
    # StaticFiles app can otherwise repeat the prefix in its filesystem lookup.
    asset_names = frozenset({
        "swagger-ui-bundle.js", "swagger-ui.css", "redoc.standalone.js",
        "init.js", "docs.css", "vendor-manifest.json", "swagger-LICENSE", "redoc-LICENSE",
    })

    @app.get("/api/docs-assets/{asset_name}", include_in_schema=False)
    def asset(asset_name: str) -> FileResponse:
        if asset_name not in asset_names:
            raise HTTPException(status_code=404, detail="Documentation asset not found.")
        return FileResponse(ASSETS / asset_name, headers={"Cache-Control": "no-cache"})

    def document(request: Request, viewer: str) -> HTMLResponse:
        prefix = escape(request.scope.get("root_path", "").rstrip("/"), quote=True)
        title = escape(app.title)
        bundle = "swagger-ui-bundle.js" if viewer == "swagger" else "redoc.standalone.js"
        stylesheet = f'<link rel="stylesheet" href="{prefix}/api/docs-assets/swagger-ui.css">' if viewer == "swagger" else ""
        return HTMLResponse(f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · {"Swagger UI" if viewer == "swagger" else "ReDoc"}</title>
{stylesheet}<link rel="stylesheet" href="{prefix}/api/docs-assets/docs.css">
<script defer src="{prefix}/api/docs-assets/{bundle}"></script>
<script defer src="{prefix}/api/docs-assets/init.js"></script></head>
<body><header class="docs-header"><h1>{title}</h1><nav aria-label="API documentation">
<a href="{prefix}/">Explorer</a><a href="{prefix}/api/guide">Integration guide</a>
<a href="{prefix}/api/openapi.json">OpenAPI JSON</a></nav></header>
<p id="docs-status" role="status">Loading API reference…</p>
<noscript><p>The interactive reference needs JavaScript. The integration guide
and OpenAPI JSON above remain available without it.</p></noscript>
<main id="api-reference" data-viewer="{viewer}" data-schema="{prefix}/api/openapi.json" aria-label="API reference"></main>
</body></html>''')

    @app.get("/api/docs", include_in_schema=False)
    def swagger(request: Request) -> HTMLResponse:
        return document(request, "swagger")

    @app.get("/api/redoc", include_in_schema=False)
    def redoc(request: Request) -> HTMLResponse:
        return document(request, "redoc")
