FROM rocker/r-ver@sha256:df26749182af64d5263bf64149d51a427b476ed28c4e046997143be3f97fdd7c

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RENV_CONFIG_REPOS_OVERRIDE=https://p3m.dev/cran/2026-07-25

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    libpq-dev \
    libcurl4-openssl-dev \
    libssl-dev \
    libxml2-dev \
    cmake \
    libcairo2-dev \
    libfontconfig1-dev \
    libfreetype6-dev \
    libharfbuzz-dev \
    libfribidi-dev \
    libnlopt-dev \
    libpng-dev \
    libtiff5-dev \
    libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/renv.lock /opt/tcga-trace/renv.lock
RUN Rscript -e "install.packages('renv', repos='https://p3m.dev/cran/2026-07-25'); stopifnot(as.character(packageVersion('renv')) == '1.2.3'); renv::restore(lockfile='/opt/tcga-trace/renv.lock', library=.libPaths()[1], repos='https://p3m.dev/cran/2026-07-25', prompt=FALSE)"

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN python3 -m pip install --break-system-packages --no-cache-dir -r /app/requirements.txt

COPY backend/app /app/app
COPY backend/renv.lock /app/renv.lock
COPY backend/alembic.ini /app/alembic.ini
COPY backend/alembic /app/alembic
COPY backend/scripts /app/scripts
COPY repository_registry /app/repository_registry
COPY docs/API.md /app/docs/API.md
COPY docs/API_ES.md /app/docs/API_ES.md
COPY docs/publication/benchmark /app/publication/benchmark

ENV PYTHONPATH=/app

CMD ["sh", "-c", "alembic -c /app/alembic.ini upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
