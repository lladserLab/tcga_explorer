# Invoke once per package: Rscript install_r_sources.R path/to/package.tar.gz.
# Installing in-process avoids Rcmd subprocess issues during cross-builds.
args <- commandArgs(trailingOnly=TRUE)
if(length(args) != 1L) stop('Provide one source package archive')
lib <- file.path(R.home(),'library')
.libPaths(c(lib,.libPaths()))
tools:::.install_packages(c(paste0('--library=',lib),args[[1]]))
