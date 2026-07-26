#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(jsonlite)
  library(survival)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) {
  stop("Usage: external_concordance.R <input.csv> <output.json>")
}

input_path <- args[[1]]
output_path <- args[[2]]
data <- read.csv(input_path, stringsAsFactors = FALSE, check.names = FALSE)

required <- c("patient_id", "sample_id", "expression", "time_months", "event")
missing_columns <- setdiff(required, names(data))
if (length(missing_columns) > 0) {
  stop(sprintf("Missing required columns: %s", paste(missing_columns, collapse = ", ")))
}

data <- data[
  is.finite(data$expression) &
    is.finite(data$time_months) &
    data$time_months >= 0 &
    data$event %in% c(0, 1),
  ,
  drop = FALSE
]
if (nrow(data) < 10 || sum(data$event) < 5) {
  stop("External comparator has fewer than 10 patients or five events.")
}

threshold <- stats::median(data$expression)
data$group <- factor(
  ifelse(data$expression >= threshold, "High", "Low"),
  levels = c("Low", "High")
)
if (length(unique(data$group)) != 2) {
  stop("Median split did not produce two groups.")
}

survival_object <- Surv(data$time_months, data$event)
logrank <- survdiff(survival_object ~ group, data = data, rho = 0)
logrank_p <- pchisq(logrank$chisq, df = length(logrank$n) - 1, lower.tail = FALSE)

cox <- coxph(
  survival_object ~ group,
  data = data,
  ties = "efron",
  x = TRUE,
  y = TRUE
)
cox_summary <- summary(cox)
coefficient <- unname(coef(cox)[["groupHigh"]])
standard_error <- unname(sqrt(diag(vcov(cox)))[["groupHigh"]])
cox_p <- unname(cox_summary$coefficients["groupHigh", "Pr(>|z|)"])

km <- survfit(survival_object ~ group, data = data)
km_table <- summary(km)$table
if (is.null(dim(km_table))) {
  km_table <- matrix(km_table, nrow = 1)
}
row_names <- sub("^group=", "", rownames(km_table))

group_summary <- lapply(c("Low", "High"), function(group_name) {
  subset <- data[data$group == group_name, , drop = FALSE]
  table_index <- match(group_name, row_names)
  median_months <- if (
    !is.na(table_index) &&
      "median" %in% colnames(km_table) &&
      is.finite(km_table[table_index, "median"])
  ) {
    unname(km_table[table_index, "median"])
  } else {
    NA_real_
  }
  list(
    group = group_name,
    patients = nrow(subset),
    events = sum(subset$event),
    median_survival_months = median_months
  )
})
names(group_summary) <- c("Low", "High")

payload <- list(
  status = "completed",
  contrast = "High vs Low",
  cutoff_method = "median",
  cutoff_value = threshold,
  n_patients = nrow(data),
  n_events = sum(data$event),
  group_summary = group_summary,
  logrank = list(
    chisq = unname(logrank$chisq),
    degrees_of_freedom = length(logrank$n) - 1,
    p_value = unname(logrank_p)
  ),
  cox = list(
    ties = "efron",
    coefficient = coefficient,
    standard_error = standard_error,
    hazard_ratio = exp(coefficient),
    conf_low = exp(coefficient - qnorm(0.975) * standard_error),
    conf_high = exp(coefficient + qnorm(0.975) * standard_error),
    p_value = cox_p
  ),
  software = list(
    r_version = R.version.string,
    survival_version = as.character(packageVersion("survival"))
  )
)

write_json(
  payload,
  output_path,
  auto_unbox = TRUE,
  pretty = TRUE,
  digits = 16,
  na = "null"
)
