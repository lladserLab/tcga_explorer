suppressPackageStartupMessages({
  library(jsonlite)
  library(survival)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1) {
  stop("Usage: Rscript pancancer_cox_scan.R <input.json>")
}

payload <- fromJSON(args[[1]], simplifyDataFrame = FALSE)

`%||%` <- function(left, right) {
  if (is.null(left) || length(left) == 0) {
    return(right)
  }
  left
}

as_null_if_bad <- function(value) {
  if (is.null(value) || length(value) == 0 || is.na(value) || !is.finite(value)) {
    return(NULL)
  }
  unname(value)
}

record_fields <- c(
  "patient_id",
  "sample_barcode",
  "expression_value",
  "time_days",
  "event",
  "sample_type",
  "stage",
  "gender",
  "race",
  "age_at_index"
)

normalize_record <- function(record) {
  values <- lapply(record_fields, function(field) {
    value <- record[[field]]
    if (is.null(value) || length(value) == 0) {
      return(NA)
    }
    value[[1]]
  })
  names(values) <- record_fields
  as.data.frame(values, stringsAsFactors = FALSE, check.names = FALSE)
}

empty_result <- function(cohort, status, code, reason) {
  list(
    cohort = cohort$cohort,
    cohort_label = cohort$cohort_label %||% cohort$cohort,
    disease_type = cohort$disease_type %||% NULL,
    primary_site = cohort$primary_site %||% NULL,
    endpoint = cohort$endpoint %||% NULL,
    endpoint_label = cohort$endpoint_label %||% NULL,
    endpoint_source = cohort$endpoint_source %||% NULL,
    status = status,
    code = code,
    reason = reason,
    warnings = cohort$warnings %||% list()
  )
}

fit_cohort <- function(cohort) {
  records <- cohort$records %||% list()
  if (length(records) == 0) {
    return(empty_result(cohort, "skipped", "NO_RECORDS", "No patient records with expression and endpoint were available."))
  }

  data <- do.call(rbind, lapply(records, normalize_record))
  data$time_days <- as.numeric(data$time_days)
  data$event <- as.integer(data$event)
  data$expression_value <- as.numeric(data$expression_value)
  data <- data[complete.cases(data[, c("time_days", "event", "expression_value")]), , drop = FALSE]
  data <- data[data$time_days > 0 & data$event %in% c(0, 1), , drop = FALSE]

  n_patients <- nrow(data)
  n_events <- sum(data$event == 1, na.rm = TRUE)
  if (n_patients < payload$min_patients) {
    return(empty_result(cohort, "skipped", "INSUFFICIENT_PATIENTS", sprintf("Requires at least %s patients; found %s.", payload$min_patients, n_patients)))
  }
  if (n_events < payload$min_events) {
    return(empty_result(cohort, "skipped", "NO_EVENTS", sprintf("Requires at least %s events; found %s.", payload$min_events, n_events)))
  }

  expression_sd <- sd(data$expression_value, na.rm = TRUE)
  expression_mean <- mean(data$expression_value, na.rm = TRUE)
  if (is.na(expression_sd) || !is.finite(expression_sd) || expression_sd <= 0) {
    return(empty_result(cohort, "skipped", "NO_EXPRESSION_VARIATION", "Expression has no usable variation after filters."))
  }

  data$expression_z <- (data$expression_value - expression_mean) / expression_sd
  surv_obj <- Surv(data$time_days, data$event)
  fit <- tryCatch(coxph(surv_obj ~ expression_z, data = data), error = function(e) e)
  if (inherits(fit, "error")) {
    return(empty_result(cohort, "failed", "COX_FAILED", conditionMessage(fit)))
  }

  cox_summary <- summary(fit)
  coefficient <- cox_summary$coefficients[1, "coef"]
  standard_error <- cox_summary$coefficients[1, "se(coef)"]
  p_value <- cox_summary$coefficients[1, "Pr(>|z|)"]
  hazard_ratio <- cox_summary$conf.int[1, "exp(coef)"]
  hr_conf_low <- cox_summary$conf.int[1, "lower .95"]
  hr_conf_high <- cox_summary$conf.int[1, "upper .95"]
  ph_test <- tryCatch(cox.zph(fit), error = function(e) NULL)
  ph_p_value <- NULL
  if (!is.null(ph_test) && "GLOBAL" %in% rownames(ph_test$table)) {
    ph_p_value <- as_null_if_bad(ph_test$table["GLOBAL", "p"])
  }

  list(
    cohort = cohort$cohort,
    cohort_label = cohort$cohort_label %||% cohort$cohort,
    disease_type = cohort$disease_type %||% NULL,
    primary_site = cohort$primary_site %||% NULL,
    endpoint = cohort$endpoint,
    endpoint_label = cohort$endpoint_label,
    endpoint_source = cohort$endpoint_source,
    status = "completed",
    n_patients = n_patients,
    n_events = n_events,
    expression_mean = as_null_if_bad(expression_mean),
    expression_sd = as_null_if_bad(expression_sd),
    log_hr = as_null_if_bad(coefficient),
    standard_error = as_null_if_bad(standard_error),
    hazard_ratio = as_null_if_bad(hazard_ratio),
    hr_conf_low = as_null_if_bad(hr_conf_low),
    hr_conf_high = as_null_if_bad(hr_conf_high),
    p_value = as_null_if_bad(p_value),
    ph_p_value = ph_p_value,
    warnings = cohort$warnings %||% list()
  )
}

results <- lapply(payload$cohorts %||% list(), fit_cohort)
output <- list(scan_id = payload$scan_id, results = results)
write_json(output, payload$output_path, auto_unbox = TRUE, null = "null", na = "null", pretty = TRUE)
