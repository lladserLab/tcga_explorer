#!/usr/bin/env Rscript

# Batch null calibration for the production Expression Comparison statistics.
#
# This runner intentionally repeats the inferential branches in
# backend/scripts/expression_comparison.R without producing plots. A parity test
# compares its gene-level p and q values against the production engine.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L) {
  stop("Usage: expression_comparison_null_calibration.R <config.json>")
}
if (!requireNamespace("jsonlite", quietly = TRUE)) {
  stop("The jsonlite package is required.")
}

cfg <- jsonlite::fromJSON(args[[1L]], simplifyVector = FALSE)
panel <- read.csv(
  cfg$panel_values_csv,
  stringsAsFactors = FALSE,
  check.names = FALSE,
  na.strings = c("", "NA", "NaN")
)
permutations <- read.csv(
  cfg$permutations_csv,
  stringsAsFactors = FALSE,
  check.names = FALSE,
  colClasses = "character"
)

required_panel <- c(
  "gene_symbol",
  "sample_index_zero_based",
  "sample_id",
  "expression_value"
)
required_permutations <- c(
  "replicate",
  "group_a_n",
  "group_b_n",
  "group_b_zero_based_positions"
)
if (!all(required_panel %in% names(panel))) {
  stop("Panel values are missing required columns.")
}
if (!all(required_permutations %in% names(permutations))) {
  stop("Permutation records are missing required columns.")
}

panel$sample_index_zero_based <- as.integer(panel$sample_index_zero_based)
panel$expression_value <- as.numeric(panel$expression_value)
minimum_n <- as.integer(cfg$minimum_finite_samples_per_group)
thresholds <- as.numeric(unlist(cfg$q_thresholds, use.names = FALSE))
if (!length(thresholds) || any(!is.finite(thresholds))) {
  stop("At least one finite q threshold is required.")
}

genes <- unique(as.character(panel$gene_symbol))
sample_index <- sort(unique(panel$sample_index_zero_based))
if (!identical(sample_index, seq.int(0L, length(sample_index) - 1L))) {
  stop("Panel sample positions must form a zero-based contiguous index.")
}
sample_count <- length(sample_index)
sample_ids <- rep(NA_character_, sample_count)
values_by_gene <- vector("list", length(genes))
names(values_by_gene) <- genes
for (gene in genes) {
  rows <- panel[panel$gene_symbol == gene, , drop = FALSE]
  rows <- rows[order(rows$sample_index_zero_based), , drop = FALSE]
  if (
    nrow(rows) != sample_count ||
      !identical(rows$sample_index_zero_based, sample_index)
  ) {
    stop(paste("Gene", gene, "does not contain one value per indexed sample."))
  }
  if (all(is.na(sample_ids))) {
    sample_ids <- as.character(rows$sample_id)
  } else if (!identical(sample_ids, as.character(rows$sample_id))) {
    stop("Sample order differs between panel genes.")
  }
  values_by_gene[[gene]] <- as.numeric(rows$expression_value)
}

parse_positions <- function(value) {
  value <- as.character(value)
  if (!nzchar(value)) return(integer())
  as.integer(strsplit(value, ";", fixed = TRUE)[[1L]]) + 1L
}

threshold_suffix <- function(value) {
  gsub("\\.", "_", sprintf("%.2f", value))
}

safe_min <- function(values) {
  values <- values[is.finite(values)]
  if (length(values)) min(values) else NA_real_
}

replicate_rows <- vector("list", nrow(permutations))
gene_rows <- vector("list", nrow(permutations) * length(genes))
gene_row_index <- 0L

started <- proc.time()[["elapsed"]]
for (permutation_index in seq_len(nrow(permutations))) {
  permutation <- permutations[permutation_index, , drop = FALSE]
  replicate_id <- as.integer(permutation$replicate)
  positions_b <- parse_positions(permutation$group_b_zero_based_positions)
  if (
    length(positions_b) != as.integer(permutation$group_b_n) ||
      anyDuplicated(positions_b) ||
      any(positions_b < 1L | positions_b > sample_count)
  ) {
    stop(paste("Invalid group-B positions in replicate", replicate_id))
  }
  positions_a <- setdiff(seq_len(sample_count), positions_b)
  if (length(positions_a) != as.integer(permutation$group_a_n)) {
    stop(paste("Invalid group-A count in replicate", replicate_id))
  }

  replicate_gene_rows <- vector("list", length(genes))
  for (gene_index in seq_along(genes)) {
    gene <- genes[[gene_index]]
    values <- values_by_gene[[gene]]
    a <- values[positions_a]
    b <- values[positions_b]
    a <- a[is.finite(a)]
    b <- b[is.finite(b)]
    sufficient <- length(a) >= minimum_n && length(b) >= minimum_n
    welch_statistic <- NA_real_
    welch_df <- NA_real_
    welch_p <- NA_real_
    mann_u <- NA_real_
    mann_p <- NA_real_

    if (sufficient) {
      variance_a <- var(a)
      variance_b <- var(b)
      standard_error_squared <- variance_b / length(b) + variance_a / length(a)
      mean_difference <- mean(b) - mean(a)
      if (is.finite(standard_error_squared) && standard_error_squared > 0) {
        welch <- t.test(
          b,
          a,
          alternative = "two.sided",
          var.equal = FALSE,
          conf.level = 0.95
        )
        welch_statistic <- unname(welch$statistic)
        welch_df <- unname(welch$parameter)
        welch_p <- welch$p.value
      } else if (is.finite(mean_difference) && mean_difference == 0) {
        welch_statistic <- 0
        welch_p <- 1
      }

      combined <- c(b, a)
      if (length(unique(combined)) == 1L) {
        mann_u <- length(b) * length(a) / 2
        mann_p <- 1
      } else {
        mann <- suppressWarnings(
          wilcox.test(
            b,
            a,
            alternative = "two.sided",
            exact = FALSE,
            correct = TRUE
          )
        )
        mann_u <- unname(mann$statistic)
        mann_p <- mann$p.value
      }
    }

    replicate_gene_rows[[gene_index]] <- data.frame(
      replicate = replicate_id,
      gene_symbol = gene,
      group_a_n = length(a),
      group_b_n = length(b),
      evaluable = sufficient,
      welch_t_statistic = welch_statistic,
      welch_df = welch_df,
      welch_p_value = welch_p,
      welch_fdr = NA_real_,
      mann_whitney_u = mann_u,
      mann_whitney_p_value = mann_p,
      mann_whitney_fdr = NA_real_,
      stringsAsFactors = FALSE
    )
  }

  statistics_rows <- do.call(rbind, replicate_gene_rows)
  welch_indices <- which(is.finite(statistics_rows$welch_p_value))
  mann_indices <- which(is.finite(statistics_rows$mann_whitney_p_value))
  if (length(welch_indices)) {
    statistics_rows$welch_fdr[welch_indices] <- p.adjust(
      statistics_rows$welch_p_value[welch_indices],
      method = "BH"
    )
  }
  if (length(mann_indices)) {
    statistics_rows$mann_whitney_fdr[mann_indices] <- p.adjust(
      statistics_rows$mann_whitney_p_value[mann_indices],
      method = "BH"
    )
  }

  replicate_summary <- list(
    replicate = replicate_id,
    group_a_n = length(positions_a),
    group_b_n = length(positions_b),
    evaluable_genes = sum(statistics_rows$evaluable),
    welch_min_q = safe_min(statistics_rows$welch_fdr),
    mann_whitney_min_q = safe_min(statistics_rows$mann_whitney_fdr)
  )
  for (threshold in thresholds) {
    suffix <- threshold_suffix(threshold)
    welch_rejected <- is.finite(statistics_rows$welch_fdr) &
      statistics_rows$welch_fdr <= threshold
    mann_rejected <- is.finite(statistics_rows$mann_whitney_fdr) &
      statistics_rows$mann_whitney_fdr <= threshold
    either_rejected <- welch_rejected | mann_rejected
    replicate_summary[[paste0("welch_rejections_q_le_", suffix)]] <- sum(welch_rejected)
    replicate_summary[[paste0("welch_any_q_le_", suffix)]] <- any(welch_rejected)
    replicate_summary[[paste0("mann_whitney_rejections_q_le_", suffix)]] <- sum(mann_rejected)
    replicate_summary[[paste0("mann_whitney_any_q_le_", suffix)]] <- any(mann_rejected)
    replicate_summary[[paste0("either_family_rejections_q_le_", suffix)]] <- sum(either_rejected)
    replicate_summary[[paste0("either_family_any_q_le_", suffix)]] <- any(either_rejected)
  }
  replicate_rows[[permutation_index]] <- as.data.frame(
    replicate_summary,
    stringsAsFactors = FALSE,
    check.names = FALSE
  )
  for (row_index in seq_len(nrow(statistics_rows))) {
    gene_row_index <- gene_row_index + 1L
    gene_rows[[gene_row_index]] <- statistics_rows[row_index, , drop = FALSE]
  }
}
elapsed <- proc.time()[["elapsed"]] - started

replicate_output <- do.call(rbind, replicate_rows)
gene_output <- do.call(rbind, gene_rows[seq_len(gene_row_index)])
write.csv(
  replicate_output,
  cfg$replicate_output_csv,
  row.names = FALSE,
  na = ""
)
write.csv(
  gene_output,
  cfg$gene_output_csv,
  row.names = FALSE,
  na = ""
)

engine <- list(
  schema_version = "trace-expression-null-calibration-engine-v1",
  production_pipeline_version = as.character(cfg$production_pipeline_version),
  production_reference_script = as.character(cfg$production_reference_script),
  exact_statistics = list(
    welch = "stats::t.test(b, a, two.sided, var.equal=FALSE, conf.level=0.95)",
    mann_whitney = "stats::wilcox.test(b, a, two.sided, exact=FALSE, correct=TRUE)",
    multiplicity = "stats::p.adjust(method='BH') separately by test"
  ),
  contrast = as.character(cfg$contrast),
  genes = length(genes),
  samples = sample_count,
  replicates = nrow(permutations),
  minimum_finite_samples_per_group = minimum_n,
  q_thresholds = thresholds,
  elapsed_seconds = elapsed,
  software_versions = list(
    R = R.version.string,
    jsonlite = as.character(utils::packageVersion("jsonlite"))
  )
)
jsonlite::write_json(
  engine,
  cfg$engine_output_json,
  auto_unbox = TRUE,
  pretty = TRUE,
  digits = NA,
  na = "null"
)
