suppressPackageStartupMessages({
  library(jsonlite)
  library(survival)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1) {
  stop("Usage: Rscript hierarchical_pancancer_cox.R <input.json>")
}

payload <- fromJSON(args[[1]], simplifyDataFrame = FALSE)

`%||%` <- function(left, right) {
  if (is.null(left) || length(left) == 0) right else left
}

min_patients <- as.integer(payload$min_patients %||% 20L)
min_events <- as.integer(payload$min_events %||% 10L)
min_censored <- as.integer(payload$min_censored %||% 5L)

scalar <- function(value, default = NA) {
  if (is.null(value) || length(value) == 0) return(default)
  value[[1]]
}

clean_text <- function(value) {
  value <- trimws(as.character(scalar(value, "")))
  if (is.na(value)) "" else value
}

null_if_bad <- function(value) {
  if (is.null(value) || length(value) == 0 || is.na(value) || !is.finite(value)) {
    return(NULL)
  }
  unname(value)
}

release_metadata <- function(release) {
  list(
    release_id = clean_text(release$release_id),
    study_id = clean_text(release$study_id),
    study_cluster_id = clean_text(release$study_cluster_id %||% release$study_id),
    cancer_id = clean_text(release$cancer_id),
    endpoint = clean_text(release$endpoint),
    time_origin = clean_text(release$time_origin),
    clinical_context = clean_text(release$clinical_context),
    model_family = clean_text(release$model_family %||% "univariable_cox"),
    effect_scale = "within_study_iqr",
    effect_scale_label = "Cox hazard ratio per +1 within-study expression IQR"
  )
}

empty_result <- function(release, status, code, reason, n_patients = NULL,
                         n_events = NULL, n_censored = NULL) {
  c(
    release_metadata(release),
    list(
      status = status,
      code = code,
      reason = reason,
      n_patients = n_patients,
      n_events = n_events,
      n_censored = n_censored,
      warnings = list()
    )
  )
}

normalize_record <- function(record, position) {
  sample_id <- record$sample_id %||% record$sample_barcode
  data.frame(
    input_position = position,
    patient_id = clean_text(record$patient_id),
    sample_id = clean_text(sample_id),
    expression_value = suppressWarnings(as.numeric(scalar(record$expression_value))),
    time_days = suppressWarnings(as.numeric(scalar(record$time_days))),
    event = suppressWarnings(as.integer(scalar(record$event))),
    stringsAsFactors = FALSE,
    check.names = FALSE
  )
}

fit_release <- function(release) {
  metadata <- release_metadata(release)
  required_metadata <- c(
    "release_id", "study_id", "cancer_id", "endpoint", "time_origin",
    "clinical_context", "model_family"
  )
  missing_metadata <- required_metadata[vapply(
    required_metadata,
    function(field) identical(metadata[[field]], ""),
    logical(1)
  )]
  if (length(missing_metadata)) {
    return(empty_result(
      release,
      "skipped",
      "MISSING_UNIVERSE_METADATA",
      paste("Missing required universe metadata:", paste(missing_metadata, collapse = ", "))
    ))
  }
  if (metadata$model_family != "univariable_cox") {
    return(empty_result(
      release,
      "skipped",
      "UNSUPPORTED_MODEL_FAMILY",
      "This release-level runner currently fits only the univariable_cox model family."
    ))
  }

  records <- release$records %||% list()
  if (!length(records)) {
    return(empty_result(release, "skipped", "NO_RECORDS", "No patient records were supplied."))
  }
  data <- do.call(rbind, lapply(seq_along(records), function(index) {
    normalize_record(records[[index]], index)
  }))

  if (any(data$patient_id == "")) {
    return(empty_result(
      release,
      "skipped",
      "MISSING_PATIENT_IDS",
      "Every record must identify its patient before sample selection and Cox fitting."
    ))
  }
  duplicate_patients <- sort(unique(data$patient_id[duplicated(data$patient_id)]))
  if (length(duplicate_patients)) {
    return(empty_result(
      release,
      "skipped",
      "DUPLICATE_PATIENTS",
      paste0(
        "The release contains multiple records for ", length(duplicate_patients),
        " patient(s); deterministic upstream sample selection is required."
      )
    ))
  }

  data <- data[complete.cases(data[, c("expression_value", "time_days", "event")]), , drop = FALSE]
  data <- data[
    is.finite(data$expression_value) & is.finite(data$time_days) &
      data$time_days > 0 & data$event %in% c(0L, 1L),
    , drop = FALSE
  ]
  data <- data[order(data$patient_id, data$sample_id, data$input_position), , drop = FALSE]
  rownames(data) <- NULL

  n_patients <- nrow(data)
  n_events <- sum(data$event == 1L)
  n_censored <- sum(data$event == 0L)
  if (n_patients < min_patients) {
    return(empty_result(
      release, "skipped", "INSUFFICIENT_PATIENTS",
      sprintf("Requires at least %s patients; found %s.", min_patients, n_patients),
      n_patients, n_events, n_censored
    ))
  }
  if (n_events < min_events) {
    return(empty_result(
      release, "skipped", "INSUFFICIENT_EVENTS",
      sprintf("Requires at least %s events; found %s.", min_events, n_events),
      n_patients, n_events, n_censored
    ))
  }
  if (n_censored < min_censored) {
    return(empty_result(
      release, "skipped", "INSUFFICIENT_CENSORED",
      sprintf("Requires at least %s censored patients; found %s.", min_censored, n_censored),
      n_patients, n_events, n_censored
    ))
  }

  quartiles <- as.numeric(quantile(
    data$expression_value,
    probs = c(0.25, 0.5, 0.75),
    names = FALSE,
    na.rm = TRUE,
    type = 7
  ))
  expression_iqr <- quartiles[[3]] - quartiles[[1]]
  if (!is.finite(expression_iqr) || expression_iqr <= 0) {
    return(empty_result(
      release, "skipped", "NO_EXPRESSION_IQR",
      "Expression has no positive finite within-study IQR after filtering.",
      n_patients, n_events, n_censored
    ))
  }
  data$expression_iqr <- (data$expression_value - quartiles[[2]]) / expression_iqr

  model_warnings <- character()
  fit <- tryCatch(
    withCallingHandlers(
      coxph(
        Surv(time_days, event) ~ expression_iqr,
        data = data,
        ties = "efron",
        x = TRUE
      ),
      warning = function(warning) {
        model_warnings <<- c(model_warnings, conditionMessage(warning))
        invokeRestart("muffleWarning")
      }
    ),
    error = function(error) error
  )
  if (inherits(fit, "error")) {
    result <- empty_result(
      release, "failed", "COX_FAILED", conditionMessage(fit),
      n_patients, n_events, n_censored
    )
    result$warnings <- as.list(unique(model_warnings))
    return(result)
  }

  fit_summary <- summary(fit)
  coefficient <- unname(fit_summary$coefficients["expression_iqr", "coef"])
  standard_error <- unname(fit_summary$coefficients["expression_iqr", "se(coef)"])
  p_value <- unname(fit_summary$coefficients["expression_iqr", "Pr(>|z|)"])
  if (!all(is.finite(c(coefficient, standard_error, p_value))) || standard_error <= 0) {
    result <- empty_result(
      release, "failed", "COX_NONFINITE",
      "Cox returned a non-finite IQR-scaled expression estimate.",
      n_patients, n_events, n_censored
    )
    result$warnings <- as.list(unique(model_warnings))
    return(result)
  }

  ph_p_value <- NA_real_
  ph_test <- tryCatch(cox.zph(fit), error = function(error) error)
  if (inherits(ph_test, "error")) {
    model_warnings <- c(model_warnings, paste("cox.zph failed:", conditionMessage(ph_test)))
  } else if (!is.null(ph_test$table) && "expression_iqr" %in% rownames(ph_test$table)) {
    ph_p_value <- unname(ph_test$table["expression_iqr", "p"])
  }

  c(
    metadata,
    list(
      status = "completed",
      code = "COMPLETED",
      reason = NULL,
      n_patients = n_patients,
      n_events = n_events,
      n_censored = n_censored,
      expression_q1 = null_if_bad(quartiles[[1]]),
      expression_median = null_if_bad(quartiles[[2]]),
      expression_q3 = null_if_bad(quartiles[[3]]),
      expression_iqr = null_if_bad(expression_iqr),
      term = "expression_iqr",
      log_hr = null_if_bad(coefficient),
      standard_error = null_if_bad(standard_error),
      hazard_ratio = null_if_bad(exp(coefficient)),
      hr_conf_low = null_if_bad(exp(coefficient - 1.96 * standard_error)),
      hr_conf_high = null_if_bad(exp(coefficient + 1.96 * standard_error)),
      p_value = null_if_bad(p_value),
      ph_p_value = null_if_bad(ph_p_value),
      warnings = as.list(unique(model_warnings))
    )
  )
}

results <- lapply(payload$releases %||% list(), fit_release)
output <- list(
  scan_id = payload$scan_id,
  estimand = list(
    model_family = "univariable_cox",
    effect_scale = "within_study_iqr",
    effect_scale_label = "Cox hazard ratio per +1 within-study expression IQR",
    ties = "efron",
    expression_quantile_type = 7
  ),
  eligibility_thresholds = list(
    min_patients = min_patients,
    min_events = min_events,
    min_censored = min_censored
  ),
  software_versions = list(
    R = R.version.string,
    survival = as.character(packageVersion("survival")),
    jsonlite = as.character(packageVersion("jsonlite"))
  ),
  results = results
)
write_json(
  output,
  payload$output_path,
  auto_unbox = TRUE,
  null = "null",
  na = "null",
  pretty = TRUE,
  digits = NA
)
