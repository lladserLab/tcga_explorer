"""Isolated real-schema documentation server: no DB, lifespan or compute jobs."""
from pathlib import Path
import re

from fastapi import FastAPI

from app.api_docs import install_api_docs
from app.main import app as production_app

app = FastAPI(docs_url=None, redoc_url=None, openapi_url="/api/openapi.json", root_path="/tcga_explorer")
app.openapi = production_app.openapi
install_api_docs(app)
policy_source = Path(__file__).resolve().parents[2] / "infra/nginx/default.conf"
CSP = re.search(r'add_header Content-Security-Policy "([^"]+)"', policy_source.read_text())[1]


@app.middleware("http")
async def real_edge_policy(request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = CSP
    return response
