import asyncio
import re
from pathlib import Path

import httpx
from fastapi import FastAPI

from app.api_docs import install_api_docs


def test_api_docs_are_same_origin_and_prefix_safe():
    async def check():
        for prefix in ["", "/tcga_explorer"]:
            app = FastAPI(title="TRACE <test>", docs_url=None, redoc_url=None, root_path=prefix)
            install_api_docs(app)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                for viewer in ["docs", "redoc"]:
                    response = await client.get(f"{prefix}/api/{viewer}")
                    assert response.status_code == 200
                    assert "TRACE &lt;test&gt;" in response.text
                    assert 'data-schema="' + prefix + '/api/openapi.json"' in response.text
                    assert "<noscript>" in response.text
                    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", response.text)
                    for asset in re.findall(r'(?:src|href)="([^"]+/api/docs-assets/[^"]+)"', response.text):
                        payload = await client.get(asset)
                        assert payload.status_code == 200, asset
                        assert len(payload.content) > 50
                        if prefix:
                            stripped = await client.get(asset.removeprefix(prefix))
                            assert stripped.status_code == 200
                            assert stripped.content == payload.content
                    assert "cdn.jsdelivr" not in response.text
                    assert "fonts.googleapis" not in response.text
                assert (await client.get(prefix + "/api/docs-assets/absent.js")).status_code == 404
    asyncio.run(check())


def test_documentation_burst_does_not_consume_the_compute_api_allowance():
    edge = (Path(__file__).resolve().parents[2] / "infra/nginx/default.conf").read_text()
    docs_location = edge.split("location ~ ^/tcga_explorer/api/(docs|", 1)[1].split(
        "location /tcga_explorer/api/", 1
    )[0]
    assert "limit_req zone=tcga_public_docs burst=30 nodelay;" in docs_location
    assert "limit_req zone=tcga_public_api" not in docs_location
    assert "limit_except GET { deny all; }" in docs_location
    assert "zone=tcga_public_api:10m rate=2r/s;" in edge
    assert "zone=tcga_public_docs:10m rate=10r/s;" in edge
