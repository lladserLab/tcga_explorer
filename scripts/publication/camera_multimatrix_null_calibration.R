#!/usr/bin/env Rscript

# Publication-only, paired CAMERA null-calibration engine.
#
# This engine is intentionally separate from backend/scripts/camera_gsea.R and
# from the previously frozen CAMERA operating-characteristic engine. It does
# not alter TRACE's production GSEA contract.

suppressPackageStartupMessages(library(jsonlite))
suppressPackageStartupMessages(library(limma))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L) {
  stop("Usage: Rscript camera_multimatrix_null_calibration.R <input.json>")
}

payload <- fromJSON(args[[1]], simplifyVector = TRUE)
required <- c(
  "matrix_path", "gmt_path", "genes", "sample_ids", "labels_path",
  "tasks_path", "output_path", "min_gene_set_size", "max_gene_set_size",
  "expected_limma_version"
)
missing <- required[!vapply(required, function(field) {
  !is.null(payload[[field]]) && length(payload[[field]]) > 0L
}, logical(1))]
if (length(missing)) {
  stop("Multi-matrix CAMERA input is missing: ", paste(missing, collapse = ", "))
}

observed_limma <- as.character(packageVersion("limma"))
expected_limma <- as.character(payload$expected_limma_version)
if (!identical(observed_limma, expected_limma)) {
  stop("Expected limma ", expected_limma, "; observed ", observed_limma, ".")
}

genes <- toupper(trimws(as.character(payload$genes)))
sample_ids <- as.character(payload$sample_ids)
n_genes <- length(genes)
n_samples <- length(sample_ids)
if (n_genes < 100L || n_samples < 10L) {
  stop("The frozen matrix is too small for this calibration.")
}
if (anyDuplicated(genes) || anyDuplicated(sample_ids)) {
  stop("Gene symbols and sample identifiers must be unique.")
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
  stop("The frozen expression matrix is truncated.")
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
  stop("The calibration requires a complete finite expression matrix.")
}

gmt_lines <- readLines(
  normalizePath(as.character(payload$gmt_path), mustWork = TRUE),
  warn = FALSE,
  encoding = "UTF-8"
)
gmt_lines <- gmt_lines[nzchar(trimws(gmt_lines)) & !startsWith(gmt_lines, "#")]
gmt_fields <- strsplit(gmt_lines, "\t", fixed = TRUE)
if (any(lengths(gmt_fields) < 3L)) stop("The GMT file contains an invalid row.")
pathway_names <- vapply(gmt_fields, `[[`, character(1), 1L)
if (any(!nzchar(pathway_names)) || anyDuplicated(pathway_names)) {
  stop("GMT pathway names must be non-empty and unique.")
}

indices <- lapply(gmt_fields, function(fields) {
  symbols <- unique(toupper(trimws(fields[-c(1L, 2L)])))
  symbols <- symbols[nzchar(symbols)]
  matched <- match(symbols, genes, nomatch = 0L)
  unique(matched[matched > 0L])
})
names(indices) <- pathway_names
min_size <- as.integer(payload$min_gene_set_size)
max_size <- as.integer(payload$max_gene_set_size)
eligible <- lengths(indices) >= min_size & lengths(indices) <= max_size
indices <- indices[eligible]
if (!length(indices)) stop("No pathway is eligible for CAMERA.")

labels <- read.csv(as.character(payload$labels_path), stringsAsFactors = FALSE)
tasks <- read.csv(as.character(payload$tasks_path), stringsAsFactors = FALSE)
label_by_replicate <- split(labels, labels$replicate)
output_path <- as.character(payload$output_path)
dir.create(dirname(output_path), recursive = TRUE, showWarnings = FALSE)

parse_positions <- function(value) {
  if (is.na(value) || !nzchar(value)) {
    integer(0)
  } else {
    as.integer(strsplit(value, ";", fixed = TRUE)[[1L]]) + 1L
  }
}

result_fields <- c(
  "task_id", "replicate", "correlation_mode", "configured_correlation",
  "group_a_n", "group_b_n", "pathways_tested", "min_fdr",
  "rejections_q_le_0_05", "rejections_q_le_0_10", "rejections_q_le_0_25",
  "camera_correlation_mean", "camera_correlation_median",
  "camera_correlation_p05", "camera_correlation_p95",
  "camera_correlation_minimum", "camera_correlation_maximum",
  "camera_correlation_mean_absolute", "camera_correlation_above_0_01",
  "camera_correlation_proportion_above_0_01", "camera_seconds"
)

write_csv <- function(frame, path, append = FALSE, col.names = !append) {
  write.table(
    frame,
    file = path,
    sep = ",",
    row.names = FALSE,
    col.names = col.names,
    quote = TRUE,
    append = append,
    na = ""
  )
}

done <- character(0)
if (file.exists(output_path) && file.info(output_path)$size > 0L) {
  checkpoint <- read.csv(output_path, stringsAsFactors = FALSE)
  if (nrow(checkpoint)) {
    done <- paste(checkpoint$task_id, checkpoint$correlation_mode, sep = "::")
  }
}

append_result <- function(row) {
  frame <- as.data.frame(row, stringsAsFactors = FALSE)
  frame <- frame[, result_fields, drop = FALSE]
  append <- file.exists(output_path) && file.info(output_path)$size > 0L
  write_csv(frame, output_path, append = append, col.names = !append)
}

quantile_value <- function(values, probability) {
  as.numeric(quantile(values, probs = probability, names = FALSE, type = 7))
}

for (task_index in seq_len(nrow(tasks))) {
  task <- tasks[task_index, , drop = FALSE]
  replicate_key <- as.character(task$replicate[[1L]])
  label <- label_by_replicate[[replicate_key]]
  if (is.null(label) || nrow(label) != 1L) {
    stop("Missing frozen labels for replicate ", replicate_key)
  }
  group_b_indices <- parse_positions(
    as.character(label$group_b_zero_based_positions[[1L]])
  )
  expected_b <- as.integer(label$group_b_n[[1L]])
  if (length(group_b_indices) != expected_b || anyDuplicated(group_b_indices)) {
    stop("Frozen group-B positions are inconsistent.")
  }
  groups <- rep("a", n_samples)
  groups[group_b_indices] <- "b"
  design <- cbind(Intercept = 1, B_minus_A = as.integer(groups == "b"))

  for (correlation_mode in c("estimated_per_set", "fixed_0_01")) {
    done_key <- paste(as.character(task$task_id[[1L]]), correlation_mode, sep = "::")
    if (done_key %in% done) next
    inter_gene_cor <- if (identical(correlation_mode, "estimated_per_set")) {
      NA_real_
    } else {
      0.01
    }
    started <- proc.time()[["elapsed"]]
    camera_result <- limma::camera(
      expression,
      index = indices,
      design = design,
      contrast = "B_minus_A",
      use.ranks = FALSE,
      allow.neg.cor = FALSE,
      inter.gene.cor = inter_gene_cor,
      trend.var = TRUE,
      sort = FALSE
    )
    elapsed <- proc.time()[["elapsed"]] - started
    if (!all(rownames(camera_result) == names(indices))) {
      stop("CAMERA changed the pathway order.")
    }
    fdr <- as.numeric(camera_result$FDR)
    if (any(!is.finite(fdr))) stop("CAMERA returned a non-finite FDR.")

    correlations <- if (identical(correlation_mode, "estimated_per_set")) {
      as.numeric(camera_result$Correlation)
    } else {
      numeric(0)
    }
    if (length(correlations) && any(!is.finite(correlations))) {
      stop("CAMERA returned a non-finite correlation.")
    }

    row <- list(
      task_id = as.character(task$task_id[[1L]]),
      replicate = as.integer(task$replicate[[1L]]),
      correlation_mode = correlation_mode,
      configured_correlation = if (identical(correlation_mode, "fixed_0_01")) 0.01 else NA_real_,
      group_a_n = sum(groups == "a"),
      group_b_n = sum(groups == "b"),
      pathways_tested = nrow(camera_result),
      min_fdr = min(fdr),
      rejections_q_le_0_05 = sum(fdr <= 0.05),
      rejections_q_le_0_10 = sum(fdr <= 0.10),
      rejections_q_le_0_25 = sum(fdr <= 0.25),
      camera_correlation_mean = if (length(correlations)) mean(correlations) else NA_real_,
      camera_correlation_median = if (length(correlations)) median(correlations) else NA_real_,
      camera_correlation_p05 = if (length(correlations)) quantile_value(correlations, 0.05) else NA_real_,
      camera_correlation_p95 = if (length(correlations)) quantile_value(correlations, 0.95) else NA_real_,
      camera_correlation_minimum = if (length(correlations)) min(correlations) else NA_real_,
      camera_correlation_maximum = if (length(correlations)) max(correlations) else NA_real_,
      camera_correlation_mean_absolute = if (length(correlations)) mean(abs(correlations)) else NA_real_,
      camera_correlation_above_0_01 = if (length(correlations)) sum(correlations > 0.01) else NA_integer_,
      camera_correlation_proportion_above_0_01 = if (length(correlations)) mean(correlations > 0.01) else NA_real_,
      camera_seconds = as.numeric(elapsed)
    )
    append_result(row)
    done <- c(done, done_key)
  }
}
