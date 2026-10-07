#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L) {
  stop("Usage: expression_comparison.R <engine_input.json>")
}
if (!requireNamespace("jsonlite", quietly = TRUE)) {
  stop("The jsonlite package is required.")
}

cfg <- jsonlite::fromJSON(args[[1L]], simplifyVector = FALSE)
values <- read.csv(
  cfg$values_csv,
  stringsAsFactors = FALSE,
  check.names = FALSE,
  na.strings = c("", "NA", "NaN"),
  colClasses = c(
    "character", "character", "character", "character", "character", "numeric"
  )
)
groups <- read.csv(
  cfg$groups_csv,
  stringsAsFactors = FALSE,
  check.names = FALSE,
  na.strings = c("", "NA", "NaN"),
  colClasses = "character"
)
values$expression_value <- as.numeric(values$expression_value)
genes <- vapply(
  cfg$genes_resolved,
  function(item) as.character(item$gene_symbol),
  character(1L)
)
group_a_label <- as.character(cfg$group_a_label)
group_b_label <- as.character(cfg$group_b_label)
fdr_threshold <- as.numeric(cfg$fdr_threshold)
minimum_n <- as.integer(cfg$minimum_finite_samples_per_group)

finite_or_na <- function(value) {
  value <- as.numeric(value)
  if (length(value) == 0L || !is.finite(value[[1L]])) NA_real_ else value[[1L]]
}

describe_group <- function(x, label) {
  x <- x[is.finite(x)]
  quantiles <- if (length(x)) {
    as.numeric(quantile(x, probs = c(0.25, 0.75), names = FALSE, type = 7))
  } else {
    c(NA_real_, NA_real_)
  }
  list(
    label = label,
    n = length(x),
    mean = if (length(x)) mean(x) else NA_real_,
    sd = if (length(x) > 1L) sd(x) else NA_real_,
    median = if (length(x)) median(x) else NA_real_,
    q1 = quantiles[[1L]],
    q3 = quantiles[[2L]],
    min = if (length(x)) min(x) else NA_real_,
    max = if (length(x)) max(x) else NA_real_
  )
}

metadata_for_gene <- function(symbol) {
  index <- match(symbol, genes)
  if (is.na(index)) stop(paste("Missing metadata for", symbol))
  cfg$genes_resolved[[index]]
}

gene_results <- vector("list", length(genes))
summary_rows <- vector("list", length(genes) * 2L)
for (gene_index in seq_along(genes)) {
  symbol <- genes[[gene_index]]
  meta <- metadata_for_gene(symbol)
  gene_values <- values[values$gene_symbol == symbol, , drop = FALSE]
  a <- gene_values$expression_value[gene_values$group_key == "a"]
  b <- gene_values$expression_value[gene_values$group_key == "b"]
  a <- a[is.finite(a)]
  b <- b[is.finite(b)]
  desc_a <- describe_group(a, group_a_label)
  desc_b <- describe_group(b, group_b_label)
  summary_rows[[2L * gene_index - 1L]] <- data.frame(
    gene_symbol = symbol,
    group_key = "a",
    group_label = group_a_label,
    n = desc_a$n,
    mean = desc_a$mean,
    sd = desc_a$sd,
    median = desc_a$median,
    q1 = desc_a$q1,
    q3 = desc_a$q3,
    min = desc_a$min,
    max = desc_a$max,
    stringsAsFactors = FALSE
  )
  summary_rows[[2L * gene_index]] <- data.frame(
    gene_symbol = symbol,
    group_key = "b",
    group_label = group_b_label,
    n = desc_b$n,
    mean = desc_b$mean,
    sd = desc_b$sd,
    median = desc_b$median,
    q1 = desc_b$q1,
    q3 = desc_b$q3,
    min = desc_b$min,
    max = desc_b$max,
    stringsAsFactors = FALSE
  )

  sufficient <- length(a) >= minimum_n && length(b) >= minimum_n
  policy_status <- if (is.null(meta$inferential_status)) {
    "inferential"
  } else {
    as.character(meta$inferential_status)
  }
  included <- isTRUE(meta$included_in_multiplicity)
  status <- if (sufficient) "analyzed" else "not_evaluable"
  inferential_status <- if (sufficient) policy_status else "not_evaluable"
  mean_difference <- if (length(a) && length(b)) mean(b) - mean(a) else NA_real_
  median_difference <- if (length(a) && length(b)) median(b) - median(a) else NA_real_
  welch_statistic <- NA_real_
  welch_df <- NA_real_
  welch_p <- NA_real_
  ci_low <- NA_real_
  ci_high <- NA_real_
  mann_u <- NA_real_
  mann_p <- NA_real_
  hedges_g <- NA_real_
  rank_biserial <- NA_real_

  if (sufficient) {
    variance_a <- var(a)
    variance_b <- var(b)
    standard_error_squared <- variance_b / length(b) + variance_a / length(a)
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
      ci_low <- unname(welch$conf.int[[1L]])
      ci_high <- unname(welch$conf.int[[2L]])
    } else if (is.finite(mean_difference) && mean_difference == 0) {
      # A zero Welch standard error is handled explicitly so all-tie genes are
      # neutral and JSON never contains NaN/Inf.
      welch_statistic <- 0
      welch_p <- 1
      ci_low <- mean_difference
      ci_high <- mean_difference
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
      # For two samples, R's W is the Mann-Whitney U for the first argument.
      mann_u <- unname(mann$statistic)
      mann_p <- mann$p.value
    }
    if (is.finite(mann_u)) {
      rank_biserial <- 2 * mann_u / (length(b) * length(a)) - 1
    }

    pooled_variance <- (
      (length(b) - 1) * variance_b + (length(a) - 1) * variance_a
    ) / (length(a) + length(b) - 2)
    if (is.finite(pooled_variance) && pooled_variance > 0) {
      pooled_sd <- sqrt(pooled_variance)
      cohens_d <- mean_difference / pooled_sd
      correction <- 1 - 3 / (4 * (length(a) + length(b)) - 9)
      hedges_g <- correction * cohens_d
    } else if (is.finite(mean_difference) && mean_difference == 0) {
      hedges_g <- 0
    }

    # A target that participated in group construction remains useful for
    # descriptive effects and U/rank-biserial, but is not an independent test.
    if (identical(policy_status, "descriptive_only")) {
      welch_statistic <- NA_real_
      welch_df <- NA_real_
      welch_p <- NA_real_
      ci_low <- NA_real_
      ci_high <- NA_real_
      mann_p <- NA_real_
    }
  }

  gene_results[[gene_index]] <- list(
    gene_symbol = symbol,
    status = status,
    inferential_status = inferential_status,
    group_a = desc_a,
    group_b = desc_b,
    mean_difference_b_minus_a = mean_difference,
    mean_difference_ci_low = ci_low,
    mean_difference_ci_high = ci_high,
    median_difference_b_minus_a = median_difference,
    hedges_g = hedges_g,
    rank_biserial = rank_biserial,
    welch_t = list(
      statistic = welch_statistic,
      df = welch_df,
      p_value = welch_p,
      fdr = NA_real_
    ),
    mann_whitney = list(
      u_statistic = mann_u,
      p_value = mann_p,
      fdr = NA_real_
    ),
    significant_at_fdr = FALSE,
    included_in_multiplicity = included && sufficient,
    circularity_reason = if (is.null(meta$circularity_reason)) {
      NULL
    } else {
      as.character(meta$circularity_reason)
    }
  )
}

welch_indices <- which(vapply(
  gene_results,
  function(row) isTRUE(row$included_in_multiplicity) && is.finite(row$welch_t$p_value),
  logical(1L)
))
mann_indices <- which(vapply(
  gene_results,
  function(row) isTRUE(row$included_in_multiplicity) && is.finite(row$mann_whitney$p_value),
  logical(1L)
))
if (length(welch_indices)) {
  adjusted <- p.adjust(
    vapply(gene_results[welch_indices], function(row) row$welch_t$p_value, numeric(1L)),
    method = "BH"
  )
  for (index in seq_along(welch_indices)) {
    gene_results[[welch_indices[[index]]]]$welch_t$fdr <- adjusted[[index]]
  }
}
if (length(mann_indices)) {
  adjusted <- p.adjust(
    vapply(gene_results[mann_indices], function(row) row$mann_whitney$p_value, numeric(1L)),
    method = "BH"
  )
  for (index in seq_along(mann_indices)) {
    gene_results[[mann_indices[[index]]]]$mann_whitney$fdr <- adjusted[[index]]
  }
}
for (index in seq_along(gene_results)) {
  row <- gene_results[[index]]
  gene_results[[index]]$significant_at_fdr <- (
    is.finite(row$welch_t$fdr) && row$welch_t$fdr <= fdr_threshold
  ) || (
    is.finite(row$mann_whitney$fdr) && row$mann_whitney$fdr <= fdr_threshold
  )
}

statistics_rows <- do.call(rbind, lapply(gene_results, function(row) {
  data.frame(
    gene_symbol = row$gene_symbol,
    status = row$status,
    inferential_status = row$inferential_status,
    group_a_label = row$group_a$label,
    group_a_n = row$group_a$n,
    group_a_mean = row$group_a$mean,
    group_a_sd = row$group_a$sd,
    group_a_median = row$group_a$median,
    group_a_q1 = row$group_a$q1,
    group_a_q3 = row$group_a$q3,
    group_a_min = row$group_a$min,
    group_a_max = row$group_a$max,
    group_b_label = row$group_b$label,
    group_b_n = row$group_b$n,
    group_b_mean = row$group_b$mean,
    group_b_sd = row$group_b$sd,
    group_b_median = row$group_b$median,
    group_b_q1 = row$group_b$q1,
    group_b_q3 = row$group_b$q3,
    group_b_min = row$group_b$min,
    group_b_max = row$group_b$max,
    mean_difference_b_minus_a = row$mean_difference_b_minus_a,
    mean_difference_ci_low = row$mean_difference_ci_low,
    mean_difference_ci_high = row$mean_difference_ci_high,
    median_difference_b_minus_a = row$median_difference_b_minus_a,
    hedges_g = row$hedges_g,
    rank_biserial = row$rank_biserial,
    welch_t_statistic = row$welch_t$statistic,
    welch_df = row$welch_t$df,
    welch_p_value = row$welch_t$p_value,
    welch_fdr = row$welch_t$fdr,
    mann_whitney_u = row$mann_whitney$u_statistic,
    mann_whitney_p_value = row$mann_whitney$p_value,
    mann_whitney_fdr = row$mann_whitney$fdr,
    significant_at_fdr = row$significant_at_fdr,
    stringsAsFactors = FALSE
  )
}))
write.csv(statistics_rows, cfg$statistics_csv, row.names = FALSE, na = "")
write.csv(do.call(rbind, summary_rows), cfg$summaries_csv, row.names = FALSE, na = "")

group_colors <- c(a = "#436E8E", b = "#D0803C")
all_finite <- values$expression_value[is.finite(values$expression_value)]
global_range <- range(all_finite)
if (!all(is.finite(global_range))) global_range <- c(0, 1)
if (diff(global_range) == 0) global_range <- global_range + c(-0.5, 0.5)
padding <- diff(global_range) * 0.06
plot_range <- global_range + c(-padding, padding)

grDevices::svg(
  cfg$violin_svg,
  width = max(9, length(genes) * 0.62),
  height = 6.2,
  bg = "white",
  onefile = TRUE
)
par(mar = c(7.2, 4.8, 3.1, 1.0), xpd = NA)
plot(
  NA,
  xlim = c(0.45, length(genes) + 0.55),
  ylim = plot_range,
  xaxt = "n",
  xlab = "",
  ylab = "Expression",
  main = "Expression distributions by group",
  bty = "l"
)
axis(1, at = seq_along(genes), labels = genes, las = 2, cex.axis = 0.8)
abline(h = pretty(plot_range), col = "#E6EAEC", lwd = 0.8)
for (gene_index in seq_along(genes)) {
  gene_values <- values[values$gene_symbol == genes[[gene_index]], , drop = FALSE]
  for (group_key in c("a", "b")) {
    x <- gene_values$expression_value[gene_values$group_key == group_key]
    x <- x[is.finite(x)]
    center <- gene_index + if (group_key == "a") -0.18 else 0.18
    if (length(unique(x)) > 1L) {
      density_values <- density(x, n = 128, from = plot_range[[1L]], to = plot_range[[2L]])
      width_values <- density_values$y / max(density_values$y) * 0.15
      polygon(
        c(center - width_values, rev(center + width_values)),
        c(density_values$x, rev(density_values$x)),
        col = grDevices::adjustcolor(group_colors[[group_key]], alpha.f = 0.52),
        border = group_colors[[group_key]],
        lwd = 0.8
      )
    } else if (length(x)) {
      segments(center - 0.12, x[[1L]], center + 0.12, x[[1L]], col = group_colors[[group_key]], lwd = 3)
    }
    if (length(x)) {
      points(center, median(x), pch = 21, bg = "white", col = group_colors[[group_key]], cex = 0.7)
    }
  }
}
legend(
  "topright",
  legend = c(group_a_label, group_b_label),
  fill = unname(group_colors),
  border = unname(group_colors),
  bty = "n",
  cex = 0.85
)
dev.off()

box_values <- list()
box_names <- character()
box_colors <- character()
for (symbol in genes) {
  gene_values <- values[values$gene_symbol == symbol, , drop = FALSE]
  for (group_key in c("a", "b")) {
    box_values[[length(box_values) + 1L]] <- gene_values$expression_value[
      gene_values$group_key == group_key & is.finite(gene_values$expression_value)
    ]
    box_names <- c(box_names, paste0(symbol, "\n", toupper(group_key)))
    box_colors <- c(box_colors, group_colors[[group_key]])
  }
}
grDevices::svg(
  cfg$boxplot_svg,
  width = max(9, length(genes) * 0.72),
  height = 6.2,
  bg = "white",
  onefile = TRUE
)
par(mar = c(7.2, 4.8, 3.1, 1.0), xpd = NA)
if (length(all_finite)) {
  boxplot(
    box_values,
    names = box_names,
    col = grDevices::adjustcolor(box_colors, alpha.f = 0.58),
    border = box_colors,
    outline = TRUE,
    las = 2,
    cex.axis = 0.72,
    ylab = "Expression",
    main = "Expression boxplots by group",
    bty = "l",
    ylim = plot_range
  )
  legend(
    "topright",
    legend = c(group_a_label, group_b_label),
    fill = unname(group_colors),
    border = unname(group_colors),
    bty = "n",
    cex = 0.85
  )
} else {
  plot.new()
  plot.window(xlim = c(0, 1), ylim = c(0, 1))
  title(main = "Expression boxplots by group")
  text(0.5, 0.52, "No finite expression values", col = "#52616A")
  text(0.5, 0.43, "Statistics are reported as not evaluable", cex = 0.82, col = "#6D7880")
  box(col = "#AAB4B9")
}
dev.off()

evenly_spaced <- function(ids, n_keep) {
  ids <- sort(unique(ids))
  if (length(ids) <= n_keep) return(ids)
  indices <- unique(as.integer(round(seq(1, length(ids), length.out = n_keep))))
  if (length(indices) < n_keep) {
    indices <- sort(c(indices, setdiff(seq_along(ids), indices)[seq_len(n_keep - length(indices))]))
  }
  ids[indices[seq_len(n_keep)]]
}
group_rows <- groups[groups$group_key %in% c("a", "b"), , drop = FALSE]
ids_a <- sort(unique(group_rows$sample_barcode[group_rows$group_key == "a"]))
ids_b <- sort(unique(group_rows$sample_barcode[group_rows$group_key == "b"]))
sample_cap <- as.integer(cfg$heatmap_max_samples)
if (length(ids_a) + length(ids_b) <= sample_cap) {
  keep_a <- ids_a
  keep_b <- ids_b
} else {
  keep_a_n <- max(1L, min(length(ids_a), floor(sample_cap * length(ids_a) / (length(ids_a) + length(ids_b)))))
  keep_b_n <- max(1L, min(length(ids_b), sample_cap - keep_a_n))
  remaining <- sample_cap - keep_a_n - keep_b_n
  if (remaining > 0L) {
    add_a <- min(remaining, length(ids_a) - keep_a_n)
    keep_a_n <- keep_a_n + add_a
    remaining <- remaining - add_a
    keep_b_n <- keep_b_n + min(remaining, length(ids_b) - keep_b_n)
  }
  keep_a <- evenly_spaced(ids_a, keep_a_n)
  keep_b <- evenly_spaced(ids_b, keep_b_n)
}
heatmap_samples <- c(keep_a, keep_b)
heatmap_groups <- c(rep("a", length(keep_a)), rep("b", length(keep_b)))
heatmap_matrix <- matrix(
  NA_real_,
  nrow = length(genes),
  ncol = length(heatmap_samples),
  dimnames = list(genes, heatmap_samples)
)
for (gene_index in seq_along(genes)) {
  gene_values <- values[values$gene_symbol == genes[[gene_index]], , drop = FALSE]
  positions <- match(gene_values$sample_barcode, heatmap_samples)
  present <- !is.na(positions) & is.finite(gene_values$expression_value)
  heatmap_matrix[gene_index, positions[present]] <- gene_values$expression_value[present]
  finite_values <- heatmap_matrix[gene_index, is.finite(heatmap_matrix[gene_index, ])]
  center <- if (length(finite_values)) mean(finite_values) else NA_real_
  spread <- if (length(finite_values) > 1L) sd(finite_values) else NA_real_
  if (is.finite(spread) && spread > 0) {
    heatmap_matrix[gene_index, ] <- (heatmap_matrix[gene_index, ] - center) / spread
  } else {
    heatmap_matrix[gene_index, is.finite(heatmap_matrix[gene_index, ])] <- 0
  }
}
heat_colors <- grDevices::colorRampPalette(c("#2C5C86", "#F7F7F5", "#A9473F"))(101L)
color_for_z <- function(z) {
  if (!is.finite(z)) return("#D9DEE1")
  bounded <- min(2.5, max(-2.5, z))
  index <- as.integer(round((bounded + 2.5) / 5 * 100)) + 1L
  heat_colors[[index]]
}
grDevices::svg(
  cfg$heatmap_svg,
  width = max(9, min(18, 4.5 + length(heatmap_samples) * 0.055)),
  height = max(5.2, min(13, 2.7 + length(genes) * 0.34)),
  bg = "white",
  onefile = TRUE
)
par(mar = c(if (length(heatmap_samples) <= 50L) 6.5 else 2.5, 7.5, 3.5, 1.2))
plot.new()
plot.window(xlim = c(0, length(heatmap_samples)), ylim = c(0, length(genes) + 1.05), xaxs = "i", yaxs = "i")
for (gene_index in seq_along(genes)) {
  y_bottom <- length(genes) - gene_index
  for (sample_index in seq_along(heatmap_samples)) {
    rect(
      sample_index - 1,
      y_bottom,
      sample_index,
      y_bottom + 1,
      col = color_for_z(heatmap_matrix[gene_index, sample_index]),
      border = NA
    )
  }
}
for (sample_index in seq_along(heatmap_samples)) {
  rect(
    sample_index - 1,
    length(genes) + 0.08,
    sample_index,
    length(genes) + 0.34,
    col = group_colors[[heatmap_groups[[sample_index]]]],
    border = NA
  )
}
z_legend_width <- max(3, min(length(heatmap_samples) * 0.32, 36))
z_breaks <- seq(0, z_legend_width, length.out = length(heat_colors) + 1L)
for (color_index in seq_along(heat_colors)) {
  rect(
    z_breaks[[color_index]],
    length(genes) + 0.56,
    z_breaks[[color_index + 1L]],
    length(genes) + 0.78,
    col = heat_colors[[color_index]],
    border = NA
  )
}
rect(0, length(genes) + 0.56, z_legend_width, length(genes) + 0.78, border = "#6D7880", col = NA, lwd = 0.5)
text(c(0, z_legend_width / 2, z_legend_width), length(genes) + 0.91, labels = c("-2.5", "0", "+2.5"), cex = 0.58, adj = c(0, 0.5, 1))
text(z_legend_width + 0.45, length(genes) + 0.67, labels = "within-gene z", cex = 0.58, adj = 0)
axis(
  2,
  at = rev(seq_along(genes)) - 0.5,
  labels = genes,
  las = 2,
  tick = FALSE,
  cex.axis = 0.8
)
if (length(heatmap_samples) <= 50L) {
  axis(
    1,
    at = seq_along(heatmap_samples) - 0.5,
    labels = heatmap_samples,
    las = 2,
    tick = FALSE,
    cex.axis = 0.48
  )
}
box(col = "#6D7880", lwd = 0.7)
title(main = "Within-gene expression z scores")
legend(
  "topright",
  inset = c(0, -0.035),
  xpd = NA,
  legend = c(group_a_label, group_b_label),
  fill = unname(group_colors),
  border = NA,
  bty = "n",
  horiz = TRUE,
  cex = 0.75
)
dev.off()

genes_analyzed <- sum(vapply(gene_results, function(row) row$status == "analyzed", logical(1L)))
genes_at_welch <- sum(vapply(
  gene_results,
  function(row) is.finite(row$welch_t$fdr) && row$welch_t$fdr <= fdr_threshold,
  logical(1L)
))
genes_at_mann <- sum(vapply(
  gene_results,
  function(row) is.finite(row$mann_whitney$fdr) && row$mann_whitney$fdr <= fdr_threshold,
  logical(1L)
))
output <- list(
  schema_version = "tcga-trace-expression-comparison-engine-result-v1",
  statistics = lapply(gene_results, function(row) {
    row$included_in_multiplicity <- NULL
    row$circularity_reason <- NULL
    row
  }),
  summary = list(
    genes_analyzed = genes_analyzed,
    genes_at_fdr_welch = genes_at_welch,
    genes_at_fdr_mann_whitney = genes_at_mann,
    heatmap_samples = length(heatmap_samples)
  ),
  engine = list(
    language = "R",
    r_version = R.version.string,
    welch = "stats::t.test(var.equal = FALSE, alternative = two.sided)",
    mann_whitney = "stats::wilcox.test(exact = FALSE, correct = TRUE, alternative = two.sided)",
    multiplicity = "stats::p.adjust(method = BH), separately by declared test family",
    contrast = "group_b_minus_group_a",
    deterministic_heatmap_selection = "sorted barcodes with evenly spaced, group-stratified thinning"
  )
)
jsonlite::write_json(
  output,
  cfg$statistics_json,
  pretty = TRUE,
  auto_unbox = TRUE,
  na = "null",
  null = "null",
  digits = 15
)
