#!/usr/bin/env Rscript

suppressPackageStartupMessages(library(jsonlite))
suppressPackageStartupMessages(library(limma))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L) {
  stop("Usage: Rscript camera_gsea.R <input.json>")
}

`%||%` <- function(left, right) {
  if (is.null(left) || length(left) == 0L) right else left
}

payload <- fromJSON(args[[1]], simplifyVector = FALSE)
required <- c(
  "matrix_path",
  "output_path",
  "gene_set_path",
  "genes",
  "sample_ids",
  "groups",
  "min_gene_set_size",
  "max_gene_set_size"
)
missing <- required[!vapply(required, function(field) {
  !is.null(payload[[field]]) && length(payload[[field]]) > 0L
}, logical(1))]
if (length(missing)) {
  stop("CAMERA input is missing: ", paste(missing, collapse = ", "))
}

expected_limma <- as.character(payload$expected_limma_version %||% "3.62.2")
observed_limma <- as.character(packageVersion("limma"))
if (!identical(observed_limma, expected_limma)) {
  stop(
    "CAMERA requires limma ", expected_limma,
    "; observed ", observed_limma, "."
  )
}

genes <- toupper(trimws(unlist(payload$genes, use.names = FALSE)))
sample_ids <- as.character(unlist(payload$sample_ids, use.names = FALSE))
groups <- tolower(as.character(unlist(payload$groups, use.names = FALSE)))
n_genes <- length(genes)
n_samples <- length(sample_ids)
if (n_genes < 100L) stop("CAMERA requires at least 100 ranked genes.")
if (n_samples < 10L || length(groups) != n_samples) {
  stop("CAMERA sample IDs and group assignments are inconsistent.")
}
if (anyDuplicated(genes)) stop("CAMERA gene symbols must be unique.")
if (anyDuplicated(sample_ids)) stop("CAMERA sample IDs must be unique.")
if (!setequal(unique(groups), c("a", "b"))) {
  stop("CAMERA groups must contain both a and b.")
}

matrix_path <- normalizePath(as.character(payload$matrix_path), mustWork = TRUE)
connection <- file(matrix_path, open = "rb")
values <- readBin(
  connection,
  what = numeric(),
  n = n_genes * n_samples,
  size = 4L,
  endian = "little"
)
close(connection)
if (length(values) != n_genes * n_samples) {
  stop("The CAMERA expression matrix is truncated.")
}
expression <- matrix(
  values,
  nrow = n_genes,
  ncol = n_samples,
  byrow = TRUE,
  dimnames = list(genes, sample_ids)
)
rm(values)
if (any(!is.finite(expression))) {
  stop("CAMERA received non-finite expression after complete-case filtering.")
}

gmt_lines <- readLines(
  normalizePath(as.character(payload$gene_set_path), mustWork = TRUE),
  warn = FALSE,
  encoding = "UTF-8"
)
gmt_lines <- gmt_lines[nzchar(trimws(gmt_lines)) & !startsWith(gmt_lines, "#")]
gmt_fields <- strsplit(gmt_lines, "\t", fixed = TRUE)
if (any(lengths(gmt_fields) < 3L)) stop("The GMT file contains an invalid row.")
pathway_names <- trimws(vapply(gmt_fields, `[[`, character(1), 1L))
if (any(!nzchar(pathway_names)) || anyDuplicated(pathway_names)) {
  stop("GMT pathway names must be non-empty and unique.")
}

min_size <- as.integer(payload$min_gene_set_size)
max_size <- as.integer(payload$max_gene_set_size)
indices <- lapply(gmt_fields, function(fields) {
  symbols <- unique(toupper(trimws(fields[-c(1L, 2L)])))
  symbols <- symbols[nzchar(symbols)]
  matched <- match(symbols, genes, nomatch = 0L)
  unique(matched[matched > 0L])
})
names(indices) <- pathway_names
eligible <- lengths(indices) >= min_size & lengths(indices) <= max_size
indices <- indices[eligible]
if (!length(indices)) stop("No pathway is eligible for CAMERA.")

design <- cbind(Intercept = 1, B_minus_A = as.integer(groups == "b"))
started <- proc.time()[["elapsed"]]
camera_result <- limma::camera(
  expression,
  index = indices,
  design = design,
  contrast = "B_minus_A",
  use.ranks = FALSE,
  allow.neg.cor = FALSE,
  inter.gene.cor = NA_real_,
  trend.var = TRUE,
  sort = FALSE
)
elapsed <- proc.time()[["elapsed"]] - started

if (!all(rownames(camera_result) == names(indices))) {
  stop("CAMERA returned pathways in an unexpected order.")
}
if (any(!is.finite(camera_result$PValue))) {
  stop("CAMERA returned a non-finite p-value.")
}

rows <- lapply(seq_len(nrow(camera_result)), function(index) {
  list(
    pathway = rownames(camera_result)[[index]],
    size_used = as.integer(camera_result$NGenes[[index]]),
    correlation = as.numeric(camera_result$Correlation[[index]]),
    direction = as.character(camera_result$Direction[[index]]),
    p_value = as.numeric(camera_result$PValue[[index]])
  )
})

output <- list(
  schema_version = "trace-camera-gene-set-test-v1",
  method = "limma_camera",
  hypothesis = "competitive",
  contrast = "group_b_minus_group_a",
  two_sided = TRUE,
  use_ranks = FALSE,
  trend_variance = TRUE,
  inter_gene_correlation = "estimated_per_gene_set",
  allow_negative_correlation = FALSE,
  negative_variance_inflation_policy = "variance_inflation_factor_lower_bounded_at_one",
  multiplicity = "BH across all eligible pathways",
  genes = n_genes,
  samples = n_samples,
  group_a_n = sum(groups == "a"),
  group_b_n = sum(groups == "b"),
  pathways_tested = length(rows),
  elapsed_seconds = as.numeric(elapsed),
  r_version = R.version.string,
  limma_version = observed_limma,
  pathways = rows
)
write_json(
  output,
  path = as.character(payload$output_path),
  auto_unbox = TRUE,
  pretty = TRUE,
  null = "null",
  digits = NA
)
