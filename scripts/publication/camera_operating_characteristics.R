#!/usr/bin/env Rscript

# Publication-only CAMERA operating-characteristic engine.
#
# This script deliberately lives outside backend/scripts.  It evaluates frozen
# sensitivity designs and never changes TRACE's production CAMERA contract.

suppressPackageStartupMessages(library(jsonlite))
suppressPackageStartupMessages(library(limma))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L) {
  stop("Usage: Rscript camera_operating_characteristics.R <input.json>")
}

payload <- fromJSON(args[[1]], simplifyVector = TRUE)

required <- c(
  "action", "matrix_path", "gmt_path", "genes", "sample_ids",
  "min_gene_set_size", "max_gene_set_size", "expected_limma_version"
)
missing <- required[!vapply(required, function(field) {
  !is.null(payload[[field]]) && length(payload[[field]]) > 0L
}, logical(1))]
if (length(missing)) {
  stop("Operating-characteristic input is missing: ", paste(missing, collapse = ", "))
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
  stop("The frozen matrix is too small for this operating-characteristic design.")
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
  stop("The power design requires a complete finite expression matrix.")
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

if (identical(as.character(payload$action), "prepare")) {
  output_dir <- as.character(payload$output_dir)
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

  # This is the exact interGeneCorrelation calculation for an intercept-only
  # design, factored once across all eligible sets.  It uses no artificial
  # labels and therefore cannot select pathways for favorable power results.
  design <- matrix(1, nrow = n_samples, ncol = 1L)
  qr_design <- qr(design)
  residual_coordinates <- qr.qty(qr_design, t(expression))[-1L, , drop = FALSE]
  standardized_residuals <- t(residual_coordinates) /
    sqrt(pmax(colMeans(residual_coordinates^2), 1e-08))

  sizes <- lengths(indices)
  correlations <- vapply(indices, function(iset) {
    m <- length(iset)
    vif <- m * mean(colMeans(standardized_residuals[iset, , drop = FALSE])^2)
    (vif - 1) / (m - 1)
  }, numeric(1))

  size_stratum <- ifelse(
    sizes <= 49L,
    "small_15_49",
    ifelse(sizes <= 149L, "medium_50_149", "large_150_500")
  )
  candidates <- data.frame(
    pathway = names(indices),
    size_used = as.integer(sizes),
    all_sample_residual_correlation = as.numeric(correlations),
    size_stratum = size_stratum,
    stringsAsFactors = FALSE
  )
  candidates <- candidates[order(candidates$pathway), , drop = FALSE]
  write_csv(candidates, file.path(output_dir, "pathway_candidates.csv"))

  selected_rows <- list()
  counter <- 1L
  quantiles <- c(low_q25 = 0.25, high_q75 = 0.75)
  for (stratum in c("small_15_49", "medium_50_149", "large_150_500")) {
    stratum_rows <- candidates[candidates$size_stratum == stratum, , drop = FALSE]
    if (!nrow(stratum_rows)) stop("A required size stratum is empty: ", stratum)
    for (rho_stratum in names(quantiles)) {
      target <- as.numeric(quantile(
        stratum_rows$all_sample_residual_correlation,
        probs = quantiles[[rho_stratum]],
        names = FALSE,
        type = 7
      ))
      order_index <- order(
        abs(stratum_rows$all_sample_residual_correlation - target),
        stratum_rows$pathway
      )
      chosen <- stratum_rows[order_index[[1L]], , drop = FALSE]
      pathway <- as.character(chosen$pathway[[1L]])
      selected_rows[[counter]] <- data.frame(
        selection_id = sprintf("P%02d", counter),
        pathway = pathway,
        size_used = as.integer(chosen$size_used[[1L]]),
        all_sample_residual_correlation = as.numeric(
          chosen$all_sample_residual_correlation[[1L]]
        ),
        size_stratum = stratum,
        correlation_stratum = rho_stratum,
        stratum_quantile_target = target,
        member_genes = paste(genes[indices[[pathway]]], collapse = ";"),
        stringsAsFactors = FALSE
      )
      counter <- counter + 1L
    }
  }
  selected <- do.call(rbind, selected_rows)
  if (anyDuplicated(selected$pathway)) {
    stop("The frozen selection algorithm chose a pathway more than once.")
  }
  write_csv(selected, file.path(output_dir, "selected_pathways.csv"))

  metadata <- list(
    schema_version = "trace-camera-power-pathway-selection-v1",
    action = "prepare",
    labels_used = FALSE,
    outcomes_used = FALSE,
    samples = n_samples,
    genes = n_genes,
    eligible_pathways = length(indices),
    size_strata = list(
      small_15_49 = c(15L, 49L),
      medium_50_149 = c(50L, 149L),
      large_150_500 = c(150L, 500L)
    ),
    correlation_quantiles = list(low_q25 = 0.25, high_q75 = 0.75),
    correlation_design = "intercept-only residual correlation across all source samples",
    r_version = R.version.string,
    limma_version = observed_limma
  )
  write_json(
    metadata,
    path = file.path(output_dir, "selection_metadata.json"),
    auto_unbox = TRUE,
    pretty = TRUE,
    null = "null",
    digits = NA
  )
  quit(save = "no", status = 0L)
}

if (!identical(as.character(payload$action), "run")) {
  stop("Unknown action: ", as.character(payload$action))
}

run_type <- as.character(payload$run_type)
if (!run_type %in% c("power", "fixed_null")) {
  stop("run_type must be power or fixed_null.")
}
tasks <- read.csv(as.character(payload$tasks_path), stringsAsFactors = FALSE)
labels <- read.csv(as.character(payload$labels_path), stringsAsFactors = FALSE)
output_path <- as.character(payload$output_path)
dir.create(dirname(output_path), recursive = TRUE, showWarnings = FALSE)

label_by_replicate <- split(labels, labels$replicate)
parse_positions <- function(value) {
  if (is.na(value) || !nzchar(value)) integer(0) else as.integer(strsplit(value, ";", fixed = TRUE)[[1L]]) + 1L
}

injections <- NULL
selected <- NULL
if (identical(run_type, "power")) {
  injections <- read.csv(as.character(payload$injections_path), stringsAsFactors = FALSE)
  selected <- read.csv(as.character(payload$selected_pathways_path), stringsAsFactors = FALSE)
}

correlation_modes <- as.character(payload$correlation_modes)
if (!length(correlation_modes) || any(!correlation_modes %in% c("estimated_per_set", "fixed_0_01"))) {
  stop("Unknown CAMERA correlation mode.")
}

result_fields <- c(
  "task_id", "run_type", "replicate", "pathway", "selection_id",
  "size_stratum", "correlation_stratum", "size_used", "effect_sd",
  "active_fraction", "active_gene_count", "correlation_mode",
  "configured_correlation", "estimated_target_correlation", "target_direction",
  "direction_correct", "target_p_value", "target_fdr", "target_rank_by_p",
  "target_detected_q_le_0_05", "rejections_q_le_0_05",
  "rejections_q_le_0_10", "rejections_q_le_0_25", "min_fdr",
  "residual_covariance_max_abs_delta", "camera_seconds", "pathways_tested"
)

done <- character(0)
if (file.exists(output_path) && file.info(output_path)$size > 0L) {
  checkpoint <- read.csv(output_path, stringsAsFactors = FALSE)
  if (nrow(checkpoint)) done <- paste(checkpoint$task_id, checkpoint$correlation_mode, sep = "::")
}

all_sample_sd <- apply(expression, 1L, sd)
if (any(!is.finite(all_sample_sd)) || any(all_sample_sd <= 0)) {
  stop("Every frozen gene must have a positive finite all-sample SD.")
}

append_result <- function(row) {
  frame <- as.data.frame(row, stringsAsFactors = FALSE)
  frame <- frame[, result_fields, drop = FALSE]
  append <- file.exists(output_path) && file.info(output_path)$size > 0L
  write_csv(frame, output_path, append = append, col.names = !append)
}

for (task_index in seq_len(nrow(tasks))) {
  task <- tasks[task_index, , drop = FALSE]
  replicate_key <- as.character(task$replicate[[1L]])
  label <- label_by_replicate[[replicate_key]]
  if (is.null(label) || nrow(label) != 1L) stop("Missing frozen labels for replicate ", replicate_key)
  group_b_indices <- parse_positions(as.character(label$group_b_zero_based_positions[[1L]]))
  if (length(group_b_indices) != as.integer(label$group_b_n[[1L]])) {
    stop("Frozen group-B positions are inconsistent.")
  }
  groups <- rep("a", n_samples)
  groups[group_b_indices] <- "b"
  design <- cbind(Intercept = 1, B_minus_A = as.integer(groups == "b"))

  pathway <- ""
  selection_id <- ""
  size_stratum_value <- ""
  correlation_stratum_value <- ""
  effect_sd <- 0
  active_fraction <- 0
  active_indices <- integer(0)
  residual_delta <- 0
  analysis_matrix <- expression

  if (identical(run_type, "power")) {
    pathway <- as.character(task$pathway[[1L]])
    effect_sd <- as.numeric(task$effect_sd[[1L]])
    active_fraction <- as.numeric(task$active_fraction[[1L]])
    selected_row <- selected[selected$pathway == pathway, , drop = FALSE]
    if (nrow(selected_row) != 1L) stop("Unknown selected pathway: ", pathway)
    injection_row <- injections[
      injections$pathway == pathway &
        abs(injections$active_fraction - active_fraction) < 1e-12,
      , drop = FALSE
    ]
    if (nrow(injection_row) != 1L) stop("Missing frozen active-gene set for ", pathway)
    active_genes <- strsplit(as.character(injection_row$active_genes[[1L]]), ";", fixed = TRUE)[[1L]]
    active_indices <- match(active_genes, genes)
    if (anyNA(active_indices)) stop("An injected gene is absent from the frozen matrix.")
    analysis_matrix <- expression
    shifts <- effect_sd * all_sample_sd[active_indices]
    analysis_matrix[active_indices, group_b_indices] <- sweep(
      analysis_matrix[active_indices, group_b_indices, drop = FALSE],
      1L,
      shifts,
      "+"
    )
    qr_design <- qr(design)
    residual_before <- qr.resid(qr_design, t(expression[active_indices, , drop = FALSE]))
    residual_after <- qr.resid(qr_design, t(analysis_matrix[active_indices, , drop = FALSE]))
    residual_delta <- max(abs(residual_before - residual_after))
    selection_id <- as.character(selected_row$selection_id[[1L]])
    size_stratum_value <- as.character(selected_row$size_stratum[[1L]])
    correlation_stratum_value <- as.character(selected_row$correlation_stratum[[1L]])
  }

  for (correlation_mode in correlation_modes) {
    done_key <- paste(as.character(task$task_id[[1L]]), correlation_mode, sep = "::")
    if (done_key %in% done) next
    inter_gene_cor <- if (identical(correlation_mode, "estimated_per_set")) NA_real_ else 0.01
    started <- proc.time()[["elapsed"]]
    camera_result <- limma::camera(
      analysis_matrix,
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
    p_values <- as.numeric(camera_result$PValue)
    target_index <- if (identical(run_type, "power")) match(pathway, rownames(camera_result)) else NA_integer_
    if (identical(run_type, "power") && is.na(target_index)) stop("Injected pathway was not tested.")
    target_direction <- if (identical(run_type, "power")) as.character(camera_result$Direction[[target_index]]) else ""
    target_correlation <- NA_real_
    if (identical(run_type, "power") && identical(correlation_mode, "estimated_per_set")) {
      target_correlation <- as.numeric(camera_result$Correlation[[target_index]])
    }
    target_p <- if (identical(run_type, "power")) p_values[[target_index]] else NA_real_
    target_fdr <- if (identical(run_type, "power")) fdr[[target_index]] else NA_real_
    target_rank <- if (identical(run_type, "power")) {
      rank(p_values, ties.method = "min")[[target_index]]
    } else NA_integer_
    row <- list(
      task_id = as.character(task$task_id[[1L]]),
      run_type = run_type,
      replicate = as.integer(task$replicate[[1L]]),
      pathway = pathway,
      selection_id = selection_id,
      size_stratum = size_stratum_value,
      correlation_stratum = correlation_stratum_value,
      size_used = if (identical(run_type, "power")) as.integer(camera_result$NGenes[[target_index]]) else NA_integer_,
      effect_sd = effect_sd,
      active_fraction = active_fraction,
      active_gene_count = length(active_indices),
      correlation_mode = correlation_mode,
      configured_correlation = if (identical(correlation_mode, "fixed_0_01")) 0.01 else NA_real_,
      estimated_target_correlation = target_correlation,
      target_direction = target_direction,
      direction_correct = if (identical(run_type, "power")) identical(target_direction, "Up") else NA,
      target_p_value = target_p,
      target_fdr = target_fdr,
      target_rank_by_p = target_rank,
      target_detected_q_le_0_05 = if (identical(run_type, "power")) target_fdr <= 0.05 else NA,
      rejections_q_le_0_05 = sum(fdr <= 0.05),
      rejections_q_le_0_10 = sum(fdr <= 0.10),
      rejections_q_le_0_25 = sum(fdr <= 0.25),
      min_fdr = min(fdr),
      residual_covariance_max_abs_delta = residual_delta,
      camera_seconds = as.numeric(elapsed),
      pathways_tested = nrow(camera_result)
    )
    append_result(row)
    done <- c(done, done_key)
  }
}
