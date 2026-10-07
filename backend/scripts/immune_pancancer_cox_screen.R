suppressPackageStartupMessages({
  library(jsonlite)
  library(survival)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1) {
  stop("Usage: Rscript immune_pancancer_cox_screen.R <input.json>")
}

payload <- fromJSON(args[[1]], simplifyVector = FALSE)

`%||%` <- function(left, right) {
  if (is.null(left) || length(left) == 0) {
    return(right)
  }
  left
}

fieldnames <- c(
  "gene_symbol",
  "cohort",
  "cohort_label",
  "disease_type",
  "primary_site",
  "endpoint",
  "endpoint_label",
  "endpoint_source",
  "status",
  "code",
  "reason",
  "n_patients",
  "n_events",
  "expression_mean",
  "expression_sd",
  "log_hr",
  "standard_error",
  "hazard_ratio",
  "hr_conf_low",
  "hr_conf_high",
  "p_value",
  "cox_warning_count",
  "cox_warnings"
)

as_null_if_bad <- function(value) {
  if (is.null(value) || length(value) == 0 || is.na(value) || !is.finite(value)) {
    return(NA)
  }
  unname(value)
}

base_row <- function(gene, cohort) {
  list(
    gene_symbol = gene,
    cohort = cohort$cohort,
    cohort_label = cohort$cohort_label %||% cohort$cohort,
    disease_type = cohort$disease_type %||% NA,
    primary_site = cohort$primary_site %||% NA,
    endpoint = cohort$endpoint %||% NA,
    endpoint_label = cohort$endpoint_label %||% NA,
    endpoint_source = cohort$endpoint_source %||% NA,
    status = NA,
    code = NA,
    reason = NA,
    n_patients = NA,
    n_events = NA,
    expression_mean = NA,
    expression_sd = NA,
    log_hr = NA,
    standard_error = NA,
    hazard_ratio = NA,
    hr_conf_low = NA,
    hr_conf_high = NA,
    p_value = NA,
    cox_warning_count = 0,
    cox_warnings = NA
  )
}

empty_result <- function(gene, cohort, status, code, reason) {
  row <- base_row(gene, cohort)
  row$status <- status
  row$code <- code
  row$reason <- reason
  row
}

append_rows <- function(path, rows, first_write) {
  if (length(rows) == 0) {
    return(first_write)
  }
  frame <- do.call(
    rbind,
    lapply(rows, function(row) {
      missing <- setdiff(fieldnames, names(row))
      if (length(missing)) {
        row[missing] <- NA
      }
      as.data.frame(row[fieldnames], stringsAsFactors = FALSE, check.names = FALSE)
    })
  )
  write.table(
    frame,
    file = path,
    sep = ",",
    row.names = FALSE,
    col.names = first_write,
    append = !first_write,
    na = "",
    qmethod = "double"
  )
  FALSE
}

read_expression_row <- function(connection, row_index, sample_count) {
  offset <- as.numeric(row_index) * as.numeric(sample_count) * 4
  seek(connection, where = offset, origin = "start", rw = "read")
  readBin(connection, what = "numeric", n = sample_count, size = 4, endian = "little")
}

fit_gene <- function(gene, cohort, records, barcodes, gene_to_row, matrix_connection, sample_count) {
  row_index <- gene_to_row[[gene]]
  if (is.null(row_index)) {
    return(empty_result(gene, cohort, "skipped", "GENE_NOT_IN_MATRIX", "Gene was not present in this cohort expression matrix."))
  }

  expression <- read_expression_row(matrix_connection, row_index, sample_count)
  if (length(expression) != sample_count) {
    return(empty_result(gene, cohort, "failed", "MATRIX_READ_FAILED", "Expression row could not be read completely."))
  }
  names(expression) <- barcodes

  data <- records
  data$time_days <- as.numeric(data$time_days)
  data$event <- as.integer(data$event)
  data$expression_value <- as.numeric(expression[data$sample_barcode])
  data <- data[complete.cases(data[, c("time_days", "event", "expression_value")]), , drop = FALSE]
  data <- data[data$time_days > 0 & data$event %in% c(0, 1) & is.finite(data$expression_value), , drop = FALSE]

  n_patients <- nrow(data)
  n_events <- sum(data$event == 1, na.rm = TRUE)
  if (n_patients < payload$min_patients) {
    return(empty_result(gene, cohort, "skipped", "INSUFFICIENT_PATIENTS", sprintf("Requires at least %s patients; found %s.", payload$min_patients, n_patients)))
  }
  if (n_events < payload$min_events) {
    return(empty_result(gene, cohort, "skipped", "NO_EVENTS", sprintf("Requires at least %s events; found %s.", payload$min_events, n_events)))
  }

  expression_mean <- mean(data$expression_value, na.rm = TRUE)
  expression_sd <- sd(data$expression_value, na.rm = TRUE)
  if (is.na(expression_sd) || !is.finite(expression_sd) || expression_sd <= 0) {
    return(empty_result(gene, cohort, "skipped", "NO_EXPRESSION_VARIATION", "Expression has no usable variation after filters."))
  }

  data$expression_z <- (data$expression_value - expression_mean) / expression_sd
  warnings <- character()
  fit <- withCallingHandlers(
    tryCatch(
      coxph(Surv(time_days, event) ~ expression_z, data = data, ties = "efron"),
      error = function(error) error
    ),
    warning = function(warning) {
      warnings <<- c(warnings, conditionMessage(warning))
      invokeRestart("muffleWarning")
    }
  )
  if (inherits(fit, "error")) {
    return(empty_result(gene, cohort, "failed", "COX_FAILED", conditionMessage(fit)))
  }

  cox_summary <- summary(fit)
  coefficient <- as_null_if_bad(cox_summary$coefficients[1, "coef"])
  standard_error <- as_null_if_bad(cox_summary$coefficients[1, "se(coef)"])
  p_value <- as_null_if_bad(cox_summary$coefficients[1, "Pr(>|z|)"])
  hazard_ratio <- as_null_if_bad(cox_summary$conf.int[1, "exp(coef)"])
  hr_conf_low <- as_null_if_bad(cox_summary$conf.int[1, "lower .95"])
  hr_conf_high <- as_null_if_bad(cox_summary$conf.int[1, "upper .95"])
  if (is.na(coefficient) || is.na(standard_error) || is.na(p_value)) {
    return(empty_result(gene, cohort, "failed", "COX_NONFINITE", "Cox model returned non-finite primary statistics."))
  }

  row <- base_row(gene, cohort)
  row$status <- "completed"
  row$n_patients <- n_patients
  row$n_events <- n_events
  row$expression_mean <- as_null_if_bad(expression_mean)
  row$expression_sd <- as_null_if_bad(expression_sd)
  row$log_hr <- coefficient
  row$standard_error <- standard_error
  row$hazard_ratio <- hazard_ratio
  row$hr_conf_low <- hr_conf_low
  row$hr_conf_high <- hr_conf_high
  row$p_value <- p_value
  row$cox_warning_count <- length(unique(warnings))
  row$cox_warnings <- if (length(warnings)) paste(unique(warnings), collapse = " | ") else NA
  row
}

output_path <- payload$output_csv_path
if (file.exists(output_path)) {
  unlink(output_path)
}
first_write <- TRUE
genes <- vapply(payload$genes, function(item) item$gene_symbol, character(1))

for (cohort in payload$cohorts %||% list()) {
  cohort_rows <- list()
  records <- tryCatch(
    read.csv(cohort$records_csv_path, stringsAsFactors = FALSE, check.names = FALSE),
    error = function(error) error
  )
  if (inherits(records, "error") || nrow(records) == 0) {
    for (gene in genes) {
      cohort_rows[[length(cohort_rows) + 1]] <- empty_result(gene, cohort, "skipped", "NO_RECORDS", "No patient records passed endpoint and sample filters.")
    }
    first_write <- append_rows(output_path, cohort_rows, first_write)
    next
  }

  metadata <- tryCatch(fromJSON(cohort$metadata_path, simplifyVector = FALSE), error = function(error) error)
  if (inherits(metadata, "error")) {
    for (gene in genes) {
      cohort_rows[[length(cohort_rows) + 1]] <- empty_result(gene, cohort, "failed", "METADATA_READ_FAILED", conditionMessage(metadata))
    }
    first_write <- append_rows(output_path, cohort_rows, first_write)
    next
  }

  barcodes <- unlist(metadata$barcodes, use.names = FALSE)
  sample_count <- as.integer(metadata$sample_count)
  gene_to_row <- metadata$gene_to_row
  connection <- file(cohort$matrix_path, open = "rb")
  for (gene in genes) {
    cohort_rows[[length(cohort_rows) + 1]] <- fit_gene(gene, cohort, records, barcodes, gene_to_row, connection, sample_count)
  }
  close(connection)
  first_write <- append_rows(output_path, cohort_rows, first_write)
}

if (first_write) {
  empty <- as.data.frame(setNames(replicate(length(fieldnames), character(), simplify = FALSE), fieldnames), check.names = FALSE)
  write.table(empty, file = output_path, sep = ",", row.names = FALSE, col.names = TRUE, na = "", qmethod = "double")
}
