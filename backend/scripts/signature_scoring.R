#!/usr/bin/env Rscript

suppressPackageStartupMessages(library(jsonlite))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1) {
  stop("Usage: signature_scoring.R <input.json>")
}

input <- jsonlite::fromJSON(args[[1]], simplifyVector = TRUE)
expected_schema <- "trace-bioconductor-signature-engine-v1"
if (!identical(as.character(input$schema_version), expected_schema)) {
  stop("Unsupported signature-scoring input schema.")
}

method <- as.character(input$method)
package_name <- switch(
  method,
  singscore = "singscore",
  ssgsea = "GSVA",
  aucell = "AUCell",
  stop("Unsupported signature-scoring method.")
)
if (!requireNamespace(package_name, quietly = TRUE)) {
  stop(sprintf("Required Bioconductor package %s is unavailable.", package_name))
}
actual_version <- as.character(utils::packageVersion(package_name))
if (!identical(actual_version, as.character(input$expected_package_version))) {
  stop(sprintf(
    "Unexpected %s version %s; expected %s.",
    package_name,
    actual_version,
    as.character(input$expected_package_version)
  ))
}

gene_symbols <- as.character(input$gene_symbols)
gene_rows <- as.integer(input$gene_row_indices_zero_based)
sample_ids <- as.character(input$sample_ids)
sample_indices <- as.integer(input$sample_indices_zero_based)
source_rows <- as.integer(input$source_row_count)
source_samples <- as.integer(input$source_sample_count)
if (
  length(gene_symbols) == 0 ||
  length(gene_symbols) != length(gene_rows) ||
  length(sample_ids) == 0 ||
  length(sample_ids) != length(sample_indices)
) {
  stop("Signature-scoring matrix indices are incomplete.")
}
if (
  anyDuplicated(gene_symbols) || anyDuplicated(sample_ids) ||
  any(gene_rows < 0L | gene_rows >= source_rows) ||
  any(sample_indices < 0L | sample_indices >= source_samples)
) {
  stop("Signature-scoring matrix indices are invalid.")
}

matrix_path <- normalizePath(as.character(input$matrix_path), mustWork = TRUE)
expected_bytes <- as.double(source_rows) * as.double(source_samples) * 4
actual_bytes <- file.info(matrix_path)$size
if (!is.finite(actual_bytes) || actual_bytes != expected_bytes) {
  stop("The source float32 matrix size does not match its declared dimensions.")
}
source_endian <- as.character(input$source_endian)
if (identical(source_endian, "native")) {
  source_endian <- .Platform$endian
}
if (!(source_endian %in% c("little", "big"))) {
  stop("Unsupported source matrix byte order.")
}

expr <- matrix(
  NA_real_,
  nrow = length(gene_rows),
  ncol = length(sample_indices),
  dimnames = list(gene_symbols, sample_ids)
)
connection <- file(matrix_path, open = "rb")
on.exit(close(connection), add = TRUE)
for (index in seq_along(gene_rows)) {
  seek(
    connection,
    where = as.double(gene_rows[[index]]) * as.double(source_samples) * 4,
    origin = "start"
  )
  values <- readBin(
    connection,
    what = numeric(),
    n = source_samples,
    size = 4,
    signed = TRUE,
    endian = source_endian
  )
  if (length(values) != source_samples) {
    stop(sprintf("Expression row %d is truncated.", gene_rows[[index]]))
  }
  expr[index, ] <- values[sample_indices + 1L]
}
close(connection)
on.exit(NULL, add = FALSE)
if (any(!is.finite(expr))) {
  stop(
    "The frozen expression universe contains non-finite values in the canonical population."
  )
}

up_genes <- intersect(as.character(input$up_genes), rownames(expr))
down_genes <- intersect(as.character(input$down_genes), rownames(expr))
if (
  length(up_genes) != length(as.character(input$up_genes)) ||
  length(down_genes) != length(as.character(input$down_genes))
) {
  stop("A signature gene is absent from the loaded frozen universe.")
}
if (length(intersect(up_genes, down_genes)) > 0) {
  stop("A signature gene cannot belong to both directions.")
}
signature_genes <- c(up_genes, down_genes)
constant_signature_genes <- signature_genes[
  vapply(
    signature_genes,
    function(gene) {
      values <- expr[gene, ]
      length(values) < 2 || isTRUE(all.equal(max(values), min(values)))
    },
    logical(1)
  )
]

score_singscore <- function(expression_matrix, up, down) {
  ranked <- singscore::rankGenes(expression_matrix, tiesMethod = "min")
  if (length(up) > 0 && length(down) > 0) {
    result <- singscore::simpleScore(
      ranked,
      upSet = up,
      downSet = down,
      centerScore = TRUE,
      knownDirection = TRUE
    )
    return(list(
      score = as.numeric(result$TotalScore),
      up = as.numeric(result$UpScore),
      down = as.numeric(result$DownScore)
    ))
  }
  genes <- if (length(up) > 0) up else down
  result <- singscore::simpleScore(
    ranked,
    upSet = genes,
    centerScore = TRUE,
    knownDirection = TRUE
  )
  raw <- as.numeric(result$TotalScore)
  if (length(up) > 0) {
    return(list(score = raw, up = raw, down = rep(0, length(raw))))
  }
  list(score = -raw, up = rep(0, length(raw)), down = -raw)
}

score_ssgsea <- function(expression_matrix, genes) {
  if (length(genes) == 0) {
    return(rep(0, ncol(expression_matrix)))
  }
  parameter <- GSVA::ssgseaParam(
    expression_matrix,
    geneSets = list(signature = genes),
    minSize = 2,
    maxSize = Inf,
    alpha = 0.25,
    normalize = FALSE,
    checkNA = "yes",
    use = "all.obs"
  )
  result <- GSVA::gsva(
    parameter,
    verbose = FALSE,
    BPPARAM = BiocParallel::SerialParam(progressbar = FALSE)
  )
  as.numeric(result["signature", ])
}

score_aucell <- function(expression_matrix, up, down, auc_max_rank, tie_seeds) {
  if (length(tie_seeds) != ncol(expression_matrix)) {
    stop("AUCell requires one deterministic tie seed per sample.")
  }
  up_scores <- numeric(ncol(expression_matrix))
  down_scores <- numeric(ncol(expression_matrix))
  gene_sets <- list()
  if (length(up) > 0) gene_sets$up <- up
  if (length(down) > 0) gene_sets$down <- down
  for (index in seq_len(ncol(expression_matrix))) {
    # AUCell randomizes exact ties. Resetting the pinned seed for each sample
    # makes a sample's ranking invariant to sample order and subsetting.
    set.seed(as.integer(tie_seeds[[index]]))
    ranking <- AUCell::AUCell_buildRankings(
      expression_matrix[, index, drop = FALSE],
      plotStats = FALSE,
      splitByBlocks = FALSE,
      keepZeroesAsNA = FALSE,
      verbose = FALSE
    )
    auc <- AUCell::AUCell_calcAUC(
      gene_sets,
      ranking,
      nCores = 1,
      normAUC = TRUE,
      aucMaxRank = auc_max_rank,
      verbose = FALSE
    )
    auc_values <- AUCell::getAUC(auc)
    if ("up" %in% rownames(auc_values)) {
      up_scores[[index]] <- as.numeric(auc_values["up", 1])
    }
    if ("down" %in% rownames(auc_values)) {
      down_scores[[index]] <- as.numeric(auc_values["down", 1])
    }
  }
  list(up = up_scores, down = down_scores)
}

started <- proc.time()[["elapsed"]]
if (method == "singscore") {
  singscore_scores <- score_singscore(expr, up_genes, down_genes)
  scores <- singscore_scores$score
  up_scores <- singscore_scores$up
  down_scores <- singscore_scores$down
} else if (method == "ssgsea") {
  up_scores <- score_ssgsea(expr, up_genes)
  down_scores <- score_ssgsea(expr, down_genes)
  scores <- up_scores - down_scores
} else {
  auc_scores <- score_aucell(
    expr,
    up_genes,
    down_genes,
    as.integer(input$parameters$auc_max_rank),
    as.integer(input$sample_tie_seeds)
  )
  up_scores <- auc_scores$up
  down_scores <- auc_scores$down
  scores <- up_scores - down_scores
}
if (any(!is.finite(scores))) {
  stop("Signature scoring produced non-finite values.")
}

output <- list(
  schema_version = expected_schema,
  method = method,
  package = package_name,
  package_version = actual_version,
  r_version = as.character(getRversion()),
  elapsed_seconds = unname(proc.time()[["elapsed"]] - started),
  constant_signature_genes = unname(constant_signature_genes),
  scores = lapply(seq_along(sample_ids), function(index) {
    list(
      sample_id = sample_ids[[index]],
      score = unname(scores[[index]]),
      up_score = unname(up_scores[[index]]),
      down_score = unname(down_scores[[index]])
    )
  })
)
jsonlite::write_json(
  output,
  path = as.character(input$output_path),
  auto_unbox = TRUE,
  digits = 16,
  null = "null",
  na = "null"
)
