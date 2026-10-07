# Serial nested make avoids jobserver descriptor failures during x64 emulation.
options(repos=c(BioCsoft='https://bioconductor.posit.co/packages/3.20/bioc',BioCann='https://bioconductor.posit.co/packages/3.20/data/annotation',BioCexp='https://bioconductor.posit.co/packages/3.20/data/experiment',CRAN='https://p3m.dev/cran/__linux__/noble/2026-07-25'))
Sys.setenv(RENV_CONFIG_REPOS_OVERRIDE='https://p3m.dev/cran/__linux__/noble/2026-07-25',MAKEFLAGS='-j1')
renv::restore(lockfile='/project/backend/renv.lock',library='/usr/local/lib/R/site-library',prompt=FALSE)
