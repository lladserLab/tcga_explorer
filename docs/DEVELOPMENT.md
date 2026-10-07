# Development and self-hosting

TRACE separates the interface, scientific engine and cohort storage. A source checkout contains code and study specifications. It does not contain patient matrices, a populated database, private uploads, analysis outputs or installers.

## Frontend

Use Node 22.12 or later and npm:

```sh
cd frontend
npm ci
npm test
npm run videos:fetch
npm run dev
```

The development server proxies requests to the backend. Inspect [vite.config.js](../frontend/vite.config.js) for routing and the configured target. Production builds use `/tcga_explorer/` by default:

```sh
VITE_BASE_PATH=/tcga_explorer/ VITE_API_BASE_URL=/tcga_explorer npm run build
```

Videos are optional for frontend development. `npm run videos:list` lists the seven current files without downloading them; `npm run videos:check` verifies local copies. The download command uses the versioned manifest and validates both size and SHA-256 before replacing a file. Build desktop assets with the videos present and `VITE_TRACE_LOCAL_DESKTOP=true`.

## Backend and scientific runtime

The API runs under Python and calls R scripts for statistical analyses. Python dependencies are hash-locked in `backend/requirements.lock`; the R environment is locked in `backend/renv.lock`. The runtime uses R 4.4.2. The [backend Dockerfile](../backend/Dockerfile) installs and verifies that environment.

For an existing compatible Python/R development environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r backend/requirements.lock
.venv/bin/python -m pytest -q backend/tests scripts/tests
```

Tests that require unavailable R packages skip explicitly. A passing Python-only run therefore does not verify the R runtime. Full scientific checks use the built backend image and its locked R library. Native packaging has additional platform checks under `desktop/`.

## Self-host the web service

Docker Compose is used for the web server. It is not an end-user requirement for desktop installations.

```sh
cp .env.example .env
```

Edit `.env` before starting. Set independent, random, URL-safe values of at least 32 characters for `POSTGRES_ADMIN_PASSWORD` and `POSTGRES_RUNTIME_PASSWORD`. Set `PUBLIC_BASE_URL`, `ALLOWED_HOSTS`, `CORS_ORIGINS`, `MCP_ALLOWED_HOSTS` and `MCP_ALLOWED_ORIGINS` for your own deployment. Never commit this file.

The default Compose configuration expects a TCGA snapshot in the sibling `../TCGA` directory and the official TCGA-CDR clinical file in `clinical/`. It imports metadata and preloads expression caches. A fresh cache can take considerable time to build. External sources are stored separately under `external_repository/`; import recipes and source terms live in `repository_registry/studies/`.

```sh
docker compose up -d --build
```

Open `http://localhost:3000/tcga_explorer/`. The public API health endpoint is `http://localhost:3000/tcga_explorer/api/v1/health` and API documentation is at `http://localhost:3000/tcga_explorer/api/docs`. The public-facing port defaults to loopback. See [deployment](APACHE_DEPLOYMENT.md) before exposing the server.

The frontend image downloads verified tutorial videos during its build. To omit them in a development image, set the build argument `TRACE_INCLUDE_GUIDE_VIDEOS=false`; the written guides remain available.

Study specifications identify import sources and policies, rather than shipping the data. Review [repository import documentation](EXTERNAL_RNASEQ_REPOSITORY.md) and the source's terms before importing a study. Source identifiers are preserved when TRACE constructs a normalized release.

## Tests and checks

```sh
python3 scripts/build_static_methods.py --check
python3 scripts/vendor_api_docs.py --check
python3 scripts/lock_python_dependencies.py --check
cd frontend
npm test
npm run build
npm run test:e2e
```

Playwright needs its browser binaries installed for `test:e2e`. CI checks frontend tests, production builds, backend tests, native unit checks and committed-source secrets. Full Docker/R checks can also be run through the manual runtime workflow.

The Examples module retains a small set of aggregate teaching results under `docs/publication/benchmark/`. These support the application and regression tests; the research manuscript and its experiment archive are maintained separately. Runtime scientific scripts remain under `backend/scripts/`.

## Contributions

Open an issue describing the observed behavior, expected behavior, environment and steps to reproduce it. Exclude patient data, private access tokens and credentials. For code changes, run the tests relevant to the affected module and follow [frontend conventions](../frontend/AGENTS.md) for interface work. Keep generated data, build outputs and local runtime folders outside Git.
