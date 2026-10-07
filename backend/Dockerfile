FROM rocker/r-ver@sha256:df26749182af64d5263bf64149d51a427b476ed28c4e046997143be3f97fdd7c

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RENV_CONFIG_REPOS_OVERRIDE=https://p3m.dev/cran/2026-07-25

RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    libpq-dev \
    libcurl4-openssl-dev \
    libssl-dev \
    libxml2-dev \
    cmake \
    curl \
    libcairo2-dev \
    libfontconfig1-dev \
    libfreetype6-dev \
    libharfbuzz-dev \
    libfribidi-dev \
    libnlopt-dev \
    libpng-dev \
    libtiff5-dev \
    libjpeg-dev \
    libmagick++-dev \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://bioconductor.org/packages/3.20/bioc/src/contrib/limma_3.62.2.tar.gz -o /tmp/limma_3.62.2.tar.gz \
    && echo "6abb60905719281fa3ccd5f2a6c201e2878a4c0a0a8e30cec662a541e67fb475  /tmp/limma_3.62.2.tar.gz" | sha256sum -c - \
    && Rscript -e "cran <- 'https://p3m.dev/cran/2026-07-25'; install.packages(c('renv','statmod','BiocManager'), repos=cran, Ncpus=1); stopifnot(as.character(packageVersion('renv')) == '1.2.3'); stopifnot(as.character(packageVersion('statmod')) == '1.5.2'); stopifnot(as.character(packageVersion('BiocManager')) == '1.30.27'); install.packages('/tmp/limma_3.62.2.tar.gz', repos=NULL, type='source', Ncpus=1); stopifnot(as.character(packageVersion('limma')) == '3.62.2')" \
    && rm -f /tmp/limma_3.62.2.tar.gz

# Install each signature engine in its own cacheable, sequential layer. This
# keeps failures attributable and avoids the opaque *.ts errors emitted by
# BiocManager's parallel top-level Makefile.
RUN curl -fsSL https://bioconductor.org/packages/3.20/bioc/src/contrib/singscore_1.26.0.tar.gz -o /tmp/singscore_1.26.0.tar.gz \
    && echo "1b0e074ab683316323a2f68d201c8d17c1aa9270752dbf50504cf9b921abf7fb  /tmp/singscore_1.26.0.tar.gz" | sha256sum -c - \
    && USE_BUNDLED_LIBUV=1 Rscript -e "cran <- 'https://p3m.dev/cran/2026-07-25'; bioc_repos <- BiocManager::repositories(version='3.20'); bioc_repos[['CRAN']] <- cran; options(repos=bioc_repos); install.packages('fs', repos=cran, Ncpus=1); stopifnot(requireNamespace('fs', quietly=TRUE)); BiocManager::install('singscore', version='3.20', ask=FALSE, update=FALSE, dependencies=NA, Ncpus=1); install.packages('/tmp/singscore_1.26.0.tar.gz', repos=NULL, type='source', Ncpus=1); stopifnot(as.character(packageVersion('singscore')) == '1.26.0')" \
    && rm -f /tmp/singscore_1.26.0.tar.gz

RUN curl -fsSL https://bioconductor.org/packages/3.20/bioc/src/contrib/GSVA_2.0.7.tar.gz -o /tmp/GSVA_2.0.7.tar.gz \
    && echo "94634cef31e8e67464d416de0c6121077509852b1fa4b8febf0337333af2cd19  /tmp/GSVA_2.0.7.tar.gz" | sha256sum -c - \
    && Rscript -e "cran <- 'https://p3m.dev/cran/2026-07-25'; bioc_repos <- BiocManager::repositories(version='3.20'); bioc_repos[['CRAN']] <- cran; options(repos=bioc_repos); BiocManager::install('GSVA', version='3.20', ask=FALSE, update=FALSE, dependencies=NA, Ncpus=1); install.packages('/tmp/GSVA_2.0.7.tar.gz', repos=NULL, type='source', Ncpus=1); stopifnot(as.character(packageVersion('GSVA')) == '2.0.7')" \
    && rm -f /tmp/GSVA_2.0.7.tar.gz

RUN curl -fsSL https://bioconductor.org/packages/3.20/bioc/src/contrib/AUCell_1.28.0.tar.gz -o /tmp/AUCell_1.28.0.tar.gz \
    && echo "00e1c45c8f861bf0cfdf977e64f944c767f831ed7406682d7ddcbbeab159bdd8  /tmp/AUCell_1.28.0.tar.gz" | sha256sum -c - \
    && Rscript -e "cran <- 'https://p3m.dev/cran/2026-07-25'; bioc_repos <- BiocManager::repositories(version='3.20'); bioc_repos[['CRAN']] <- cran; options(repos=bioc_repos); BiocManager::install('AUCell', version='3.20', ask=FALSE, update=FALSE, dependencies=NA, Ncpus=1); install.packages('/tmp/AUCell_1.28.0.tar.gz', repos=NULL, type='source', Ncpus=1); stopifnot(as.character(packageVersion('AUCell')) == '1.28.0')" \
    && rm -f /tmp/AUCell_1.28.0.tar.gz

COPY backend/renv.lock /opt/tcga-trace/renv.lock
RUN Rscript -e "cran <- 'https://p3m.dev/cran/2026-07-25'; bioc_repos <- BiocManager::repositories(version='3.20'); bioc_repos[['CRAN']] <- cran; options(repos=bioc_repos); renv::restore(lockfile='/opt/tcga-trace/renv.lock', library=.libPaths()[1], prompt=FALSE)"

# Assert the final library state after renv::restore, not only the intermediate
# state in which the pinned source archives were installed.
RUN Rscript -e "stopifnot(as.character(getRversion()) == '4.4.2'); stopifnot(requireNamespace('limma', quietly=TRUE), as.character(packageVersion('limma')) == '3.62.2'); stopifnot(requireNamespace('singscore', quietly=TRUE), as.character(packageVersion('singscore')) == '1.26.0'); stopifnot(requireNamespace('GSVA', quietly=TRUE), as.character(packageVersion('GSVA')) == '2.0.7'); stopifnot(requireNamespace('AUCell', quietly=TRUE), as.character(packageVersion('AUCell')) == '1.28.0')"

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
COPY backend/requirements.lock /app/requirements.lock
# Keep application dependencies separate from Debian-owned Python packages.
# In particular, patched wheel/setuptools cannot uninstall apt packages that
# have no pip RECORD, and must not silently leave the old versions active.
RUN python3 -m venv /opt/trace-python
ENV PATH="/opt/trace-python/bin:${PATH}"
RUN python3 -m pip install --no-cache-dir pip==26.2.1 \
    && python3 -m pip install --no-cache-dir --require-hashes -r /app/requirements.lock \
    && python3 -m pip check

COPY backend/app /app/app
COPY backend/renv.lock /app/renv.lock
COPY backend/alembic.ini /app/alembic.ini
COPY backend/alembic /app/alembic
COPY backend/scripts /app/scripts
COPY backend/gene_sets /app/gene_sets
COPY repository_registry /app/repository_registry
COPY docs/API.md /app/docs/API.md
COPY docs/API_ES.md /app/docs/API_ES.md
COPY docs/publication/benchmark /app/publication/benchmark

ENV PYTHONPATH=/app

CMD ["sh", "-c", "python3 -c 'from app.database import wait_for_database; wait_for_database()' && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
