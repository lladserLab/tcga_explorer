suppressPackageStartupMessages({
  library(jsonlite)
  library(survival)
})

script_argument <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_directory <- if (length(script_argument)) {
  dirname(normalizePath(sub("^--file=", "", script_argument[[1]])))
} else {
  getwd()
}
source(file.path(script_directory, "clinical_covariates.R"))
source(file.path(script_directory, "cox_diagnostics.R"))

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
  "grade",
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
  data$stage <- trimws(as.character(data$stage))
  data$stage[is.na(data$stage) | data$stage == ""] <- NA
  data$grade <- trimws(as.character(data$grade))
  data$grade[is.na(data$grade) | data$grade == ""] <- NA
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

  model_skip <- function(model_id, label, covariates, reason, model_data, covariate_encoding = list()) {
    list(
      model = model_id,
      label = label,
      covariates = as.list(covariates),
      covariate_encoding = covariate_encoding,
      status = "skipped",
      reason = reason,
      n_patients = nrow(model_data),
      n_events = sum(model_data$event, na.rm = TRUE),
      warnings = list()
    )
  }

  fit_expression_model <- function(model_id, label, covariates) {
    model_data <- data[, c("time_days", "event", "expression_z", covariates), drop = FALSE]
    prepared <- prepare_ordinal_covariates(model_data, covariates)
    encoded_covariates <- prepared$covariates
    covariate_encoding <- prepared$metadata
    model_data <- prepared$data[, c("time_days", "event", "expression_z", encoded_covariates), drop = FALSE]
    model_data <- model_data[complete.cases(model_data), , drop = FALSE]

    if (nrow(model_data) < payload$min_patients) {
      return(model_skip(
        model_id,
        label,
        encoded_covariates,
        sprintf("Requires at least %s complete patients after ordinal covariate filtering; found %s.", payload$min_patients, nrow(model_data)),
        model_data,
        covariate_encoding
      ))
    }
    model_events <- sum(model_data$event == 1, na.rm = TRUE)
    if (model_events < payload$min_events) {
      return(model_skip(
        model_id,
        label,
        encoded_covariates,
        sprintf("Requires at least %s events after ordinal covariate filtering; found %s.", payload$min_events, model_events),
        model_data,
        covariate_encoding
      ))
    }
    for (covariate in encoded_covariates) {
      observed <- model_data[[covariate]][is.finite(model_data[[covariate]])]
      if (length(unique(observed)) < 2) {
        return(model_skip(
          model_id,
          label,
          encoded_covariates,
          paste0("Ordinal covariate ", covariate, " has fewer than two observed scores after filtering."),
          model_data,
          covariate_encoding
        ))
      }
    }

    formula_terms <- c("expression_z", encoded_covariates)
    formula <- as.formula(paste("Surv(time_days, event) ~", paste(formula_terms, collapse = " + ")))
    model_warnings <- character()
    fit <- tryCatch(
      withCallingHandlers(
        coxph(formula, data = model_data, ties = "efron"),
        warning = function(warning) {
          model_warnings <<- c(model_warnings, conditionMessage(warning))
          invokeRestart("muffleWarning")
        }
      ),
      error = function(error) error
    )
    if (inherits(fit, "error")) {
      return(list(
        model = model_id,
        label = label,
        covariates = as.list(encoded_covariates),
        covariate_encoding = covariate_encoding,
        status = "failed",
        reason = conditionMessage(fit),
        n_patients = nrow(model_data),
        n_events = model_events,
        warnings = as.list(unique(model_warnings))
      ))
    }

    cox_summary <- summary(fit)
    coefficient_names <- rownames(cox_summary$coefficients)
    row_index <- match("expression_z", coefficient_names)
    if (is.na(row_index)) {
      return(model_skip(
        model_id,
        label,
        encoded_covariates,
        "Could not isolate the standardized expression coefficient.",
        model_data,
        covariate_encoding
      ))
    }
    coefficient <- unname(cox_summary$coefficients[row_index, "coef"])
    standard_error <- unname(cox_summary$coefficients[row_index, "se(coef)"])
    p_value <- unname(cox_summary$coefficients[row_index, "Pr(>|z|)"])
    hazard_ratio <- unname(cox_summary$conf.int[row_index, "exp(coef)"])
    hr_conf_low <- unname(cox_summary$conf.int[row_index, "lower .95"])
    hr_conf_high <- unname(cox_summary$conf.int[row_index, "upper .95"])
    if (!all(is.finite(c(coefficient, standard_error, p_value, hazard_ratio, hr_conf_low, hr_conf_high)))) {
      return(model_skip(
        model_id,
        label,
        encoded_covariates,
        "Cox model returned non-finite standardized-expression estimates.",
        model_data,
        covariate_encoding
      ))
    }
    common_scale_log_hr <- coefficient / expression_sd
    common_scale_standard_error <- standard_error / expression_sd
    common_scale_hazard_ratio <- exp(common_scale_log_hr)
    common_scale_hr_conf_low <- exp(
      common_scale_log_hr - 1.96 * common_scale_standard_error
    )
    common_scale_hr_conf_high <- exp(
      common_scale_log_hr + 1.96 * common_scale_standard_error
    )

    ph_p_value <- NA_real_
    ph_global_p_value <- NA_real_
    ph_test <- tryCatch(cox.zph(fit), error = function(error) error)
    if (inherits(ph_test, "error")) {
      model_warnings <- c(model_warnings, paste("cox.zph failed:", conditionMessage(ph_test)))
    } else if (!is.null(ph_test$table) && "p" %in% colnames(ph_test$table)) {
      ph_table <- ph_test$table
      if ("expression_z" %in% rownames(ph_table)) {
        ph_p_value <- unname(ph_table["expression_z", "p"])
      }
      if ("GLOBAL" %in% rownames(ph_table)) {
        ph_global_p_value <- unname(ph_table["GLOBAL", "p"])
      }
      if (is.finite(ph_p_value) && ph_p_value < 0.05) {
        model_warnings <- c(
          model_warnings,
          paste(
            "Expression-specific proportional hazards test p < 0.05; interpret",
            "the average per-SD HR with the prespecified two-year temporal diagnostic."
          )
        )
      } else if (is.finite(ph_global_p_value) && ph_global_p_value < 0.05) {
        model_warnings <- c(
          model_warnings,
          "Global proportional hazards test p < 0.05 while the expression term was not flagged."
        )
      }
    }
    time_varying_effect <- fit_prespecified_time_varying_effect(
      data = model_data,
      formula_terms = formula_terms,
      marker_formula_term = "expression_z",
      marker_coefficient = "expression_z",
      effect_label = "Expression per +1 within-cohort SD",
      ph_p_value = ph_p_value
    )

    list(
      model = model_id,
      label = label,
      covariates = as.list(encoded_covariates),
      covariate_encoding = covariate_encoding,
      status = "completed",
      term = "expression_z",
      n_patients = nrow(model_data),
      n_events = model_events,
      log_hr = as_null_if_bad(coefficient),
      standard_error = as_null_if_bad(standard_error),
      hazard_ratio = as_null_if_bad(hazard_ratio),
      hr_conf_low = as_null_if_bad(hr_conf_low),
      hr_conf_high = as_null_if_bad(hr_conf_high),
      p_value = as_null_if_bad(p_value),
      ph_p_value = as_null_if_bad(ph_p_value),
      ph_global_p_value = as_null_if_bad(ph_global_p_value),
      time_varying_effect = time_varying_effect,
      common_scale_term = "expression_value",
      common_scale_unit = "per +1 input score unit",
      common_scale_log_hr = as_null_if_bad(common_scale_log_hr),
      common_scale_standard_error = as_null_if_bad(
        common_scale_standard_error
      ),
      common_scale_hazard_ratio = as_null_if_bad(
        common_scale_hazard_ratio
      ),
      common_scale_hr_conf_low = as_null_if_bad(
        common_scale_hr_conf_low
      ),
      common_scale_hr_conf_high = as_null_if_bad(
        common_scale_hr_conf_high
      ),
      common_scale_p_value = as_null_if_bad(p_value),
      warnings = as.list(unique(model_warnings))
    )
  }

  cox_models <- list(
    fit_expression_model("univariable", "Primary univariable continuous Cox", character(0)),
    fit_expression_model("stage_adjusted", "Sensitivity adjusted for ordinal stage", c("stage")),
    fit_expression_model("grade_adjusted", "Sensitivity adjusted for ordinal grade", c("grade")),
    fit_expression_model("stage_grade_adjusted", "Sensitivity adjusted for ordinal stage and grade", c("stage", "grade"))
  )
  primary_model <- cox_models[[1]]
  if (is.null(primary_model$status) || primary_model$status != "completed") {
    result <- empty_result(
      cohort,
      "failed",
      "COX_FAILED",
      primary_model$reason %||% "Primary continuous Cox model did not complete."
    )
    result$cox_models <- cox_models
    return(result)
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
    n_patients = primary_model$n_patients,
    n_events = primary_model$n_events,
    expression_mean = as_null_if_bad(expression_mean),
    expression_sd = as_null_if_bad(expression_sd),
    log_hr = primary_model$log_hr,
    standard_error = primary_model$standard_error,
    hazard_ratio = primary_model$hazard_ratio,
    hr_conf_low = primary_model$hr_conf_low,
    hr_conf_high = primary_model$hr_conf_high,
    p_value = primary_model$p_value,
    ph_p_value = primary_model$ph_p_value,
    ph_global_p_value = primary_model$ph_global_p_value,
    time_varying_effect = primary_model$time_varying_effect,
    common_scale_log_hr = primary_model$common_scale_log_hr,
    common_scale_standard_error = primary_model$common_scale_standard_error,
    common_scale_hazard_ratio = primary_model$common_scale_hazard_ratio,
    common_scale_hr_conf_low = primary_model$common_scale_hr_conf_low,
    common_scale_hr_conf_high = primary_model$common_scale_hr_conf_high,
    common_scale_p_value = primary_model$common_scale_p_value,
    cox_models = cox_models,
    warnings = cohort$warnings %||% list()
  )
}

results <- lapply(payload$cohorts %||% list(), fit_cohort)
output <- list(
  scan_id = payload$scan_id,
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
