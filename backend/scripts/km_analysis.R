suppressPackageStartupMessages({
  library(jsonlite)
  library(survival)
  library(survminer)
  library(ggplot2)
  library(svglite)
})

script_argument <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_directory <- if (length(script_argument)) {
  dirname(normalizePath(sub("^--file=", "", script_argument[[1]])))
} else {
  getwd()
}
source(file.path(script_directory, "clinical_covariates.R"))
source(file.path(script_directory, "cox_diagnostics.R"))
source(file.path(script_directory, "competing_risks.R"))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1) {
  stop("Usage: Rscript km_analysis.R <input.json>")
}

payload <- fromJSON(args[[1]], simplifyDataFrame = FALSE)

MIN_MODEL_EVENTS <- 5L
MIN_SPLINE_EVENTS <- 30L
MIN_RMST_AT_RISK_PER_GROUP <- 5L

`%||%` <- function(left, right) {
  if (is.null(left) || length(left) == 0) {
    return(right)
  }
  left
}

requested_adjustment_covariates <- normalize_requested_covariates(
  payload$adjustment_covariates %||% list()
)
external_covariate_definitions <- payload$external_covariate_definitions %||% list()
requested_external_adjustment_covariates <- normalize_requested_external_covariates(
  payload$external_adjustment_covariates %||% list(),
  external_covariate_definitions
)
adjustment_requested <- (
  length(requested_adjustment_covariates) > 0 ||
  length(requested_external_adjustment_covariates) > 0
)

record_fields <- c(
  "patient_id",
  "sample_barcode",
  "endpoint",
  "expression_value",
  "expression_value_a",
  "expression_value_b",
  "group",
  "group_a",
  "group_b",
  "time_days",
  "event",
  "competing_risk_status",
  "competing_event",
  "competing_risk_source",
  "os_time_days",
  "os_event",
  "sample_type",
  "stage",
  "grade",
  "gender",
  "race",
  "age_at_index",
  vapply(
    requested_external_adjustment_covariates,
    external_covariate_record_name,
    character(1)
  )
)

normalize_record <- function(record) {
  values <- lapply(record_fields, function(field) {
    if (startsWith(field, "external__")) {
      external_name <- sub("^external__", "", field)
      external_values <- record$external_covariates
      value <- if (is.null(external_values) || !length(external_values)) {
        NULL
      } else {
        external_values[[external_name]]
      }
    } else {
      value <- record[[field]]
    }
    if (is.null(value) || length(value) == 0) {
      return(NA)
    }
    value[[1]]
  })
  names(values) <- record_fields
  as.data.frame(values, stringsAsFactors = FALSE, check.names = FALSE)
}

record_frame <- function(items) {
  if (is.null(items) || length(items) == 0) {
    return(data.frame())
  }
  do.call(rbind, lapply(items, normalize_record))
}

records <- record_frame(payload$records)
continuous_records <- record_frame(payload$continuous_records)

if (nrow(records) < 2) {
  stop("At least two records are required")
}

records$time_days <- as.numeric(records$time_days)
records$event <- as.integer(records$event)
records$competing_risk_status <- as.integer(records$competing_risk_status)
records$competing_event <- as.integer(records$competing_event)
records$os_time_days <- as.numeric(records$os_time_days)
records$os_event <- as.integer(records$os_event)
if (all(is.na(records$time_days)) && any(!is.na(records$os_time_days))) {
  records$time_days <- records$os_time_days
}
if (all(is.na(records$event)) && any(!is.na(records$os_event))) {
  records$event <- records$os_event
}
records$expression_value <- as.numeric(records$expression_value)
records$expression_value_a <- as.numeric(records$expression_value_a)
records$expression_value_b <- as.numeric(records$expression_value_b)
records$group <- factor(records$group, levels = payload$group_levels)
records$group <- droplevels(records$group)
records$stage <- trimws(as.character(records$stage))
records$stage[is.na(records$stage) | records$stage == ""] <- NA
records$grade <- trimws(as.character(records$grade))
records$grade[is.na(records$grade) | records$grade == ""] <- NA
if (nrow(continuous_records) > 0) {
  continuous_records$time_days <- as.numeric(continuous_records$time_days)
  continuous_records$event <- as.integer(continuous_records$event)
  continuous_records$competing_risk_status <- as.integer(
    continuous_records$competing_risk_status
  )
  continuous_records$competing_event <- as.integer(
    continuous_records$competing_event
  )
  continuous_records$expression_value <- as.numeric(continuous_records$expression_value)
  continuous_records$stage <- trimws(as.character(continuous_records$stage))
  continuous_records$stage[is.na(continuous_records$stage) | continuous_records$stage == ""] <- NA
  continuous_records$grade <- trimws(as.character(continuous_records$grade))
  continuous_records$grade[is.na(continuous_records$grade) | continuous_records$grade == ""] <- NA
}
group_levels <- levels(records$group)
n_groups <- length(group_levels)
endpoint_label <- payload$endpoint_label %||% "Overall survival"

time_unit <- payload$time_unit %||% "days"
time_divisor <- switch(
  time_unit,
  months = 30.4375,
  years = 365.25,
  days = 1,
  1
)
time_label <- switch(
  time_unit,
  months = "Time (months)",
  years = "Time (years)",
  days = "Time (days)",
  "Time (days)"
)
records$plot_time <- records$time_days / time_divisor

surv_obj <- Surv(records$time_days, records$event)
fit <- survfit(surv_obj ~ group, data = records)
plot_surv_obj <- Surv(records$plot_time, records$event)
plot_fit <- survfit(plot_surv_obj ~ group, data = records)
survdiff_fit <- survdiff(surv_obj ~ group, data = records)
p_value <- pchisq(
  survdiff_fit$chisq,
  length(survdiff_fit$n) - 1,
  lower.tail = FALSE
)

cox_metrics <- list()
cox_models <- list()
signature_interaction_cox_models <- list()
continuous_analysis <- list(
  status = "skipped",
  reason = "An unstratified expression-complete population was not supplied."
)
rmst <- list(status = "skipped", reason = "RMST is reported only for two expression groups.")
competing_risks <- list(
  applicable = FALSE,
  status = "not_applicable",
  reason = "The selected endpoint has no TCGA-CDR competing-risk status."
)
cox_warning_messages <- c()

cox_skip <- function(model_id, label, covariates, reason, data = records, covariate_encoding = list()) {
  list(
    model = model_id,
    label = label,
    covariates = as.list(covariates),
    covariate_encoding = covariate_encoding,
    status = "skipped",
    reason = reason,
    n_patients = nrow(data),
    n_events = sum(data$event, na.rm = TRUE)
  )
}

fit_cox_model <- function(
  model_id,
  label,
  covariates,
  external_covariates = character()
) {
  external_record_names <- vapply(
    external_covariates,
    external_covariate_record_name,
    character(1)
  )
  data <- records[
    ,
    c("time_days", "event", "group", covariates, external_record_names),
    drop = FALSE
  ]
  data <- data[is.finite(data$time_days) & !is.na(data$event) & !is.na(data$group), , drop = FALSE]
  prepared <- prepare_model_covariates(
    data,
    covariates,
    external_covariates,
    external_covariate_definitions
  )
  data <- prepared$data[, c("time_days", "event", "group", prepared$covariates), drop = FALSE]
  encoded_covariates <- prepared$covariates
  covariate_encoding <- prepared$metadata
  data <- data[complete.cases(data), , drop = FALSE]
  data <- droplevels(data)
  data$group <- droplevels(factor(data$group, levels = group_levels))
  if (nrow(data) < 10) {
    return(cox_skip(model_id, label, encoded_covariates, "Fewer than 10 complete patients after clinical covariate filtering.", data, covariate_encoding))
  }
  if (sum(data$event, na.rm = TRUE) < MIN_MODEL_EVENTS) {
    return(cox_skip(
      model_id,
      label,
      encoded_covariates,
      paste0("Fewer than ", MIN_MODEL_EVENTS, " events after clinical covariate filtering."),
      data,
      covariate_encoding
    ))
  }
  if (length(levels(data$group)) != 2) {
    return(cox_skip(model_id, label, encoded_covariates, "Cox marker HR is reported only for two expression groups.", data, covariate_encoding))
  }
  for (covariate in encoded_covariates) {
    if (!model_covariate_has_variation(data[[covariate]])) {
      return(cox_skip(model_id, label, encoded_covariates, paste0("Clinical covariate ", covariate, " has fewer than two observed values after filtering."), data, covariate_encoding))
    }
  }

  formula_terms <- c("group", encoded_covariates)
  formula <- as.formula(paste("Surv(time_days, event) ~", paste(formula_terms, collapse = " + ")))
  parameter_count <- cox_parameter_count(formula, data)
  n_events <- sum(data$event, na.rm = TRUE)
  model_warnings <- c()
  fit <- tryCatch(
    withCallingHandlers(
      coxph(formula, data = data, ties = "efron"),
      warning = function(w) {
        model_warnings <<- c(model_warnings, conditionMessage(w))
        invokeRestart("muffleWarning")
      }
    ),
    error = function(e) e
  )
  if (inherits(fit, "error")) {
    information <- cox_information_diagnostics(
      n_events,
      parameter_count,
      warnings = c(model_warnings, conditionMessage(fit)),
      standard_fit_failed = TRUE
    )
    penalized_sensitivity <- fit_firth_sensitivity(
      formula,
      data,
      information,
      term_pattern = "^group",
      effect_label = paste(group_levels[[2]], "vs", group_levels[[1]])
    )
    return(list(
      model = model_id,
      label = label,
      covariates = as.list(encoded_covariates),
      covariate_encoding = covariate_encoding,
      status = "failed",
      reason = conditionMessage(fit),
      ties = "efron",
      n_patients = nrow(data),
      n_events = n_events,
      information_diagnostics = information,
      penalized_sensitivity = penalized_sensitivity,
      warnings = as.list(unique(model_warnings))
    ))
  }

  cox_summary <- summary(fit)
  coefficient_names <- rownames(cox_summary$coefficients)
  group_rows <- grep("^group", coefficient_names)
  if (length(group_rows) != 1) {
    return(cox_skip(model_id, label, encoded_covariates, "Could not isolate a single expression-group coefficient.", data, covariate_encoding))
  }
  row_index <- group_rows[[1]]
  hazard_ratio <- unname(cox_summary$conf.int[row_index, "exp(coef)"])
  hr_conf_low <- unname(cox_summary$conf.int[row_index, "lower .95"])
  hr_conf_high <- unname(cox_summary$conf.int[row_index, "upper .95"])
  p_value <- unname(cox_summary$coefficients[row_index, "Pr(>|z|)"])
  coefficient <- unname(cox_summary$coefficients[row_index, "coef"])
  standard_error <- unname(cox_summary$coefficients[row_index, "se(coef)"])
  if (!is.finite(hazard_ratio) || !is.finite(hr_conf_low) || !is.finite(hr_conf_high)) {
    information <- cox_information_diagnostics(
      n_events,
      parameter_count,
      warnings = model_warnings,
      standard_fit_failed = TRUE
    )
    penalized_sensitivity <- fit_firth_sensitivity(
      formula,
      data,
      information,
      term = coefficient_names[[row_index]],
      term_pattern = "^group",
      effect_label = paste(group_levels[[2]], "vs", group_levels[[1]])
    )
    return(list(
      model = model_id,
      label = label,
      covariates = as.list(encoded_covariates),
      covariate_encoding = covariate_encoding,
      status = "failed",
      reason = "Model did not produce finite HR confidence intervals.",
      ties = "efron",
      n_patients = nrow(data),
      n_events = n_events,
      information_diagnostics = information,
      penalized_sensitivity = penalized_sensitivity,
      warnings = as.list(unique(model_warnings))
    ))
  }
  information <- cox_information_diagnostics(
    n_events,
    parameter_count,
    warnings = model_warnings,
    hazard_ratio = hazard_ratio,
    hr_conf_low = hr_conf_low,
    hr_conf_high = hr_conf_high
  )
  penalized_sensitivity <- fit_firth_sensitivity(
    formula,
    data,
    information,
    term = coefficient_names[[row_index]],
    term_pattern = "^group",
    effect_label = paste(group_levels[[2]], "vs", group_levels[[1]])
  )
  information_warning <- cox_information_warning(information)
  if (!is.null(information_warning)) {
    model_warnings <- c(model_warnings, information_warning)
  }
  if (identical(penalized_sensitivity$status, "failed")) {
    model_warnings <- c(
      model_warnings,
      paste("Firth penalized sensitivity failed:", penalized_sensitivity$reason)
    )
  }
  ph_test <- tryCatch(cox.zph(fit), error = function(e) e)
  ph_p_value <- NA_real_
  ph_global_p_value <- NA_real_
  if (inherits(ph_test, "error")) {
    model_warnings <- c(model_warnings, paste("cox.zph failed:", conditionMessage(ph_test)))
  } else if (!is.null(ph_test$table) && "p" %in% colnames(ph_test$table)) {
    ph_table <- ph_test$table
    group_ph_rows <- grep("^group", rownames(ph_table))
    if (length(group_ph_rows) == 1) {
      ph_p_value <- unname(ph_table[group_ph_rows[[1]], "p"])
    }
    if ("GLOBAL" %in% rownames(ph_table)) {
      ph_global_p_value <- unname(ph_table["GLOBAL", "p"])
    }
    if (is.finite(ph_p_value) && ph_p_value < 0.05) {
      model_warnings <- c(
        model_warnings,
        paste(
          "Marker-specific proportional hazards test p < 0.05; interpret the",
          "average grouped HR with the prespecified two-year temporal diagnostic."
        )
      )
    } else if (is.finite(ph_global_p_value) && ph_global_p_value < 0.05) {
      model_warnings <- c(
        model_warnings,
        "Global proportional hazards test p < 0.05 while the grouped marker term was not flagged."
      )
    }
  }
  temporal_data <- data
  temporal_data$group_high_indicator <- as.numeric(
    temporal_data$group == group_levels[[2]]
  )
  time_varying_effect <- fit_prespecified_time_varying_effect(
    data = temporal_data,
    formula_terms = c("group_high_indicator", encoded_covariates),
    marker_formula_term = "group_high_indicator",
    marker_coefficient = "group_high_indicator",
    effect_label = paste(group_levels[[2]], "vs", group_levels[[1]]),
    ph_p_value = ph_p_value
  )
  if (length(model_warnings)) {
    cox_warning_messages <<- c(cox_warning_messages, paste(label, paste(unique(model_warnings), collapse = " | "), sep = ": "))
  }
  list(
    model = model_id,
    label = label,
    covariates = as.list(encoded_covariates),
    covariate_encoding = covariate_encoding,
    status = "completed",
    ties = "efron",
    term = coefficient_names[[row_index]],
    contrast = paste(group_levels[[2]], "vs", group_levels[[1]]),
    n_patients = nrow(data),
    n_events = n_events,
    information_diagnostics = information,
    penalized_sensitivity = penalized_sensitivity,
    log_hr = coefficient,
    standard_error = standard_error,
    hazard_ratio = hazard_ratio,
    hr_conf_low = hr_conf_low,
    hr_conf_high = hr_conf_high,
    p_value = p_value,
    ph_p_value = ph_p_value,
    ph_global_p_value = ph_global_p_value,
    time_varying_effect = time_varying_effect,
    warnings = as.list(unique(model_warnings))
  )
}

if (length(levels(records$group)) == 2) {
  cox_models <- list(
    fit_cox_model("univariable", "Univariable", character(0)),
    fit_cox_model("stage_adjusted", "Adjusted for ordinal stage", c("stage")),
    fit_cox_model("grade_adjusted", "Adjusted for ordinal grade", c("grade")),
    fit_cox_model("stage_grade_adjusted", "Adjusted for ordinal stage and grade", c("stage", "grade"))
  )
  if (adjustment_requested) {
    cox_models <- c(
      cox_models,
      list(fit_cox_model(
        "user_adjusted",
        paste(
          "User-adjusted for",
          clinical_adjustment_label(
            requested_adjustment_covariates,
            requested_external_adjustment_covariates,
            external_covariate_definitions
          )
        ),
        requested_adjustment_covariates,
        requested_external_adjustment_covariates
      ))
    )
  }
  univariable_model <- cox_models[[1]]
  if (!is.null(univariable_model$status) && univariable_model$status == "completed") {
    cox_metrics <- list(
      hazard_ratio = univariable_model$hazard_ratio,
      hr_conf_low = univariable_model$hr_conf_low,
      hr_conf_high = univariable_model$hr_conf_high,
      hr_p_value = univariable_model$p_value
    )
  }
}

numeric_or_na <- function(value) {
  value <- suppressWarnings(as.numeric(value))
  if (length(value) == 0 || !is.finite(value[[1]])) {
    return(NA_real_)
  }
  unname(value[[1]])
}

rmst_cell <- function(table, row_index, column_name) {
  if (is.null(table) || !column_name %in% colnames(table) || is.na(row_index)) {
    return(NA_real_)
  }
  numeric_or_na(table[[column_name]][row_index])
}

extract_rmst_group <- function(value) {
  if (is.null(value)) {
    return(list())
  }
  if (!is.null(value$rmst)) {
    rmst_values <- value$rmst
    return(list(
      rmst_days = numeric_or_na(rmst_values[["Est."]]),
      standard_error = numeric_or_na(rmst_values[["se"]]),
      conf_low = numeric_or_na(rmst_values[["lower .95"]]),
      conf_high = numeric_or_na(rmst_values[["upper .95"]])
    ))
  }
  table <- if (!is.null(value$result)) {
    as.data.frame(value$result, check.names = FALSE)
  } else {
    as.data.frame(value, check.names = FALSE)
  }
  row_index <- grep("^RMST", rownames(table))[1]
  if (is.na(row_index)) {
    row_index <- 1
  }
  list(
    rmst_days = rmst_cell(table, row_index, "Est."),
    standard_error = rmst_cell(table, row_index, "se"),
    conf_low = rmst_cell(table, row_index, "lower .95"),
    conf_high = rmst_cell(table, row_index, "upper .95")
  )
}

extract_rmst_result_row <- function(table, pattern) {
  if (is.null(table) || nrow(table) == 0) {
    return(list())
  }
  row_index <- grep(pattern, rownames(table))[1]
  if (is.na(row_index)) {
    return(list())
  }
  list(
    estimate = rmst_cell(table, row_index, "Est."),
    conf_low = rmst_cell(table, row_index, "lower .95"),
    conf_high = rmst_cell(table, row_index, "upper .95"),
    p_value = rmst_cell(table, row_index, "p")
  )
}

fit_rmst <- function() {
  data <- records[, c("time_days", "event", "group"), drop = FALSE]
  data <- data[is.finite(data$time_days) & data$time_days > 0 & !is.na(data$event) & !is.na(data$group), , drop = FALSE]
  data$group <- droplevels(factor(data$group, levels = group_levels))
  if (nrow(data) < 10) {
    return(list(status = "skipped", reason = "Fewer than 10 complete patients after filtering.", n_patients = nrow(data)))
  }
  if (length(levels(data$group)) != 2) {
    return(list(status = "skipped", reason = "RMST is reported only for two expression groups.", n_patients = nrow(data)))
  }
  if (sum(data$event, na.rm = TRUE) < MIN_MODEL_EVENTS) {
    return(list(
      status = "skipped",
      reason = paste0("Fewer than ", MIN_MODEL_EVENTS, " events after filtering."),
      n_patients = nrow(data),
      n_events = sum(data$event, na.rm = TRUE)
    ))
  }
  if (!requireNamespace("survRM2", quietly = TRUE)) {
    return(list(status = "skipped", reason = "R package survRM2 is not installed.", n_patients = nrow(data), n_events = sum(data$event, na.rm = TRUE)))
  }
  tau_spec <- payload$rmst_tau %||% list()
  if (!is.null(tau_spec$status) && tau_spec$status != "available") {
    return(list(
      status = "skipped",
      reason = tau_spec$reason %||% "A fixed RMST horizon was not available.",
      n_patients = nrow(data),
      n_events = sum(data$event, na.rm = TRUE),
      tau_definition = tau_spec
    ))
  }
  tau_days <- numeric_or_na(tau_spec$tau_days)
  if (!is.finite(tau_days)) {
    return(list(
      status = "skipped",
      reason = "A finite cutpoint-independent RMST horizon was not supplied.",
      n_patients = nrow(data),
      n_events = sum(data$event, na.rm = TRUE),
      tau_definition = tau_spec
    ))
  }
  if (!is.finite(tau_days) || tau_days <= 0) {
    return(list(status = "skipped", reason = "Could not determine a finite RMST truncation time.", n_patients = nrow(data), n_events = sum(data$event, na.rm = TRUE)))
  }
  max_followup_by_group <- tapply(data$time_days, data$group, max, na.rm = TRUE)
  unsupported_groups <- names(max_followup_by_group)[max_followup_by_group < tau_days]
  if (length(unsupported_groups)) {
    return(list(
      status = "skipped",
      reason = paste0(
        "The fixed RMST horizon exceeds observed follow-up in group(s): ",
        paste(unsupported_groups, collapse = ", "),
        "."
      ),
      n_patients = nrow(data),
      n_events = sum(data$event, na.rm = TRUE),
      tau_days = tau_days,
      tau_rule = tau_spec$rule,
      tau_definition = tau_spec,
      max_followup_by_group = as.list(max_followup_by_group)
    ))
  }
  at_risk_by_group <- tapply(data$time_days >= tau_days, data$group, sum, na.rm = TRUE)
  sparse_groups <- names(at_risk_by_group)[at_risk_by_group < MIN_RMST_AT_RISK_PER_GROUP]
  if (length(sparse_groups)) {
    return(list(
      status = "skipped",
      reason = paste0(
        "Fewer than ",
        MIN_RMST_AT_RISK_PER_GROUP,
        " patients remain under observation at the fixed RMST horizon in group(s): ",
        paste(sparse_groups, collapse = ", "),
        "."
      ),
      n_patients = nrow(data),
      n_events = sum(data$event, na.rm = TRUE),
      tau_days = tau_days,
      tau_rule = tau_spec$rule,
      tau_definition = tau_spec,
      at_risk_at_tau = as.list(at_risk_by_group)
    ))
  }
  reference_group <- levels(data$group)[[1]]
  comparison_group <- levels(data$group)[[2]]
  arm <- ifelse(data$group == comparison_group, 1, 0)
  fit <- tryCatch(
    survRM2::rmst2(time = data$time_days, status = data$event, arm = arm, tau = tau_days),
    error = function(e) e
  )
  if (inherits(fit, "error")) {
    return(list(
      status = "failed",
      reason = conditionMessage(fit),
      n_patients = nrow(data),
      n_events = sum(data$event, na.rm = TRUE),
      tau_days = tau_days
    ))
  }
  unadjusted <- if (is.null(fit$unadjusted.result)) data.frame() else as.data.frame(fit$unadjusted.result, check.names = FALSE)
  difference <- extract_rmst_result_row(unadjusted, "^RMST.*\\-")
  ratio <- extract_rmst_result_row(unadjusted, "^RMST.*\\/")
  rmtl_ratio <- extract_rmst_result_row(unadjusted, "^RMTL.*\\/")
  groups <- list()
  groups[[reference_group]] <- extract_rmst_group(fit$RMST.arm0)
  groups[[comparison_group]] <- extract_rmst_group(fit$RMST.arm1)
  rmst_at_tau <- function(fraction) {
    candidate_tau <- tau_days * fraction
    candidate_fit <- tryCatch(
      survRM2::rmst2(time = data$time_days, status = data$event, arm = arm, tau = candidate_tau),
      error = function(e) e
    )
    if (inherits(candidate_fit, "error")) {
      return(list(
        status = "failed",
        tau_fraction = fraction,
        tau_days = candidate_tau,
        reason = conditionMessage(candidate_fit)
      ))
    }
    candidate_unadjusted <- if (is.null(candidate_fit$unadjusted.result)) {
      data.frame()
    } else {
      as.data.frame(candidate_fit$unadjusted.result, check.names = FALSE)
    }
    candidate_difference <- extract_rmst_result_row(candidate_unadjusted, "^RMST.*\\-")
    list(
      status = "completed",
      tau_fraction = fraction,
      tau_days = candidate_tau,
      tau_time_unit = candidate_tau / time_divisor,
      estimate_days = candidate_difference$estimate,
      conf_low = candidate_difference$conf_low,
      conf_high = candidate_difference$conf_high,
      p_value = candidate_difference$p_value
    )
  }
  tau_sensitivity <- lapply(c(0.75, 0.9, 1.0), rmst_at_tau)
  list(
    status = "completed",
    method = "survRM2::rmst2",
    tau_days = tau_days,
    tau_time_unit = tau_days / time_divisor,
    time_unit = time_unit,
    tau_rule = tau_spec$rule,
    tau_definition = tau_spec,
    at_risk_at_tau = as.list(at_risk_by_group),
    minimum_at_risk_per_group = MIN_RMST_AT_RISK_PER_GROUP,
    reference_group = reference_group,
    comparison_group = comparison_group,
    n_patients = nrow(data),
    n_events = sum(data$event, na.rm = TRUE),
    groups = groups,
    difference = list(
      estimate_days = difference$estimate,
      conf_low = difference$conf_low,
      conf_high = difference$conf_high,
      p_value = difference$p_value
    ),
    ratio = list(
      estimate = ratio$estimate,
      conf_low = ratio$conf_low,
      conf_high = ratio$conf_high,
      p_value = ratio$p_value
    ),
    rmtl_ratio = list(
      estimate = rmtl_ratio$estimate,
      conf_low = rmtl_ratio$conf_low,
      conf_high = rmtl_ratio$conf_high,
      p_value = rmtl_ratio$p_value
    ),
    tau_sensitivity = tau_sensitivity
  )
}

if (length(levels(records$group)) == 2) {
  rmst <- fit_rmst()
}

interaction_cox_skip <- function(model_id, label, covariates, reason, data = records, covariate_encoding = list()) {
  list(
    model = model_id,
    label = label,
    covariates = as.list(covariates),
    covariate_encoding = covariate_encoding,
    status = "skipped",
    reason = reason,
    n_patients = nrow(data),
    n_events = sum(data$event, na.rm = TRUE)
  )
}

zscore_vector <- function(value) {
  value <- as.numeric(value)
  center <- mean(value, na.rm = TRUE)
  scale <- stats::sd(value, na.rm = TRUE)
  if (!is.finite(scale) || scale == 0) {
    return(rep(NA_real_, length(value)))
  }
  (value - center) / scale
}

extract_cox_term <- function(cox_summary, term, term_label) {
  coefficient_names <- rownames(cox_summary$coefficients)
  row_index <- match(term, coefficient_names)
  if (is.na(row_index)) {
    return(NULL)
  }
  hazard_ratio <- unname(cox_summary$conf.int[row_index, "exp(coef)"])
  hr_conf_low <- unname(cox_summary$conf.int[row_index, "lower .95"])
  hr_conf_high <- unname(cox_summary$conf.int[row_index, "upper .95"])
  p_value <- unname(cox_summary$coefficients[row_index, "Pr(>|z|)"])
  coefficient <- unname(cox_summary$coefficients[row_index, "coef"])
  standard_error <- unname(cox_summary$coefficients[row_index, "se(coef)"])
  list(
    term = term,
    label = term_label,
    log_hr = coefficient,
    standard_error = standard_error,
    hazard_ratio = hazard_ratio,
    hr_conf_low = hr_conf_low,
    hr_conf_high = hr_conf_high,
    p_value = p_value
  )
}

continuous_model_skip <- function(model_id, label, covariates, reason, data = continuous_records, covariate_encoding = list()) {
  list(
    model = model_id,
    label = label,
    covariates = as.list(covariates),
    covariate_encoding = covariate_encoding,
    status = "skipped",
    reason = reason,
    n_patients = nrow(data),
    n_events = if ("event" %in% names(data)) sum(data$event, na.rm = TRUE) else 0
  )
}

continuous_base <- continuous_records
continuous_center <- NA_real_
continuous_scale <- NA_real_
if (nrow(continuous_base) > 0) {
  continuous_base <- continuous_base[
    is.finite(continuous_base$time_days) &
      continuous_base$time_days > 0 &
      !is.na(continuous_base$event) &
      is.finite(continuous_base$expression_value),
    ,
    drop = FALSE
  ]
  continuous_center <- mean(continuous_base$expression_value, na.rm = TRUE)
  continuous_scale <- stats::sd(continuous_base$expression_value, na.rm = TRUE)
  if (is.finite(continuous_scale) && continuous_scale > 0) {
    continuous_base$expression_z <- (
      continuous_base$expression_value - continuous_center
    ) / continuous_scale
  } else {
    continuous_base$expression_z <- NA_real_
  }
}

fit_continuous_linear_model <- function(
  model_id,
  label,
  covariates,
  external_covariates = character()
) {
  if (nrow(continuous_base) == 0) {
    return(continuous_model_skip(
      model_id,
      label,
      covariates,
      "No complete expression and endpoint records were available.",
      continuous_base
    ))
  }
  if (!is.finite(continuous_scale) || continuous_scale <= 0) {
    return(continuous_model_skip(
      model_id,
      label,
      covariates,
      "Expression has zero or undefined standard deviation.",
      continuous_base
    ))
  }
  external_record_names <- vapply(
    external_covariates,
    external_covariate_record_name,
    character(1)
  )
  data <- continuous_base[
    ,
    c(
      "time_days",
      "event",
      "expression_z",
      covariates,
      external_record_names
    ),
    drop = FALSE
  ]
  prepared <- prepare_model_covariates(
    data,
    covariates,
    external_covariates,
    external_covariate_definitions
  )
  data <- prepared$data[, c("time_days", "event", "expression_z", prepared$covariates), drop = FALSE]
  encoded_covariates <- prepared$covariates
  covariate_encoding <- prepared$metadata
  data <- data[complete.cases(data), , drop = FALSE]
  data <- droplevels(data)
  if (nrow(data) < 10) {
    return(continuous_model_skip(
      model_id,
      label,
      encoded_covariates,
      "Fewer than 10 complete patients after clinical covariate filtering.",
      data,
      covariate_encoding
    ))
  }
  if (sum(data$event, na.rm = TRUE) < MIN_MODEL_EVENTS) {
    return(continuous_model_skip(
      model_id,
      label,
      encoded_covariates,
      paste0("Fewer than ", MIN_MODEL_EVENTS, " events after clinical covariate filtering."),
      data,
      covariate_encoding
    ))
  }
  if (length(unique(data$expression_z)) < 2) {
    return(continuous_model_skip(
      model_id,
      label,
      encoded_covariates,
      "Expression requires at least two distinct values.",
      data,
      covariate_encoding
    ))
  }
  for (covariate in encoded_covariates) {
    if (!model_covariate_has_variation(data[[covariate]])) {
      return(continuous_model_skip(
        model_id,
        label,
        encoded_covariates,
        paste0("Clinical covariate ", covariate, " has fewer than two observed values after filtering."),
        data,
        covariate_encoding
      ))
    }
  }

  formula_terms <- c("expression_z", encoded_covariates)
  formula <- as.formula(paste("Surv(time_days, event) ~", paste(formula_terms, collapse = " + ")))
  parameter_count <- cox_parameter_count(formula, data)
  n_events <- sum(data$event, na.rm = TRUE)
  model_warnings <- c()
  model_fit <- tryCatch(
    withCallingHandlers(
      coxph(formula, data = data, ties = "efron", x = TRUE),
      warning = function(w) {
        model_warnings <<- c(model_warnings, conditionMessage(w))
        invokeRestart("muffleWarning")
      }
    ),
    error = function(e) e
  )
  if (inherits(model_fit, "error")) {
    information <- cox_information_diagnostics(
      n_events,
      parameter_count,
      warnings = c(model_warnings, conditionMessage(model_fit)),
      standard_fit_failed = TRUE
    )
    penalized_sensitivity <- fit_firth_sensitivity(
      formula,
      data,
      information,
      term = "expression_z",
      effect_label = "Expression per +1 SD"
    )
    return(list(
      model = model_id,
      label = label,
      covariates = as.list(encoded_covariates),
      covariate_encoding = covariate_encoding,
      status = "failed",
      reason = conditionMessage(model_fit),
      ties = "efron",
      n_patients = nrow(data),
      n_events = n_events,
      information_diagnostics = information,
      penalized_sensitivity = penalized_sensitivity,
      warnings = as.list(unique(model_warnings))
    ))
  }

  model_summary <- summary(model_fit)
  marker <- extract_cox_term(model_summary, "expression_z", "Expression per +1 SD")
  if (is.null(marker) ||
      !is.finite(marker$hazard_ratio) ||
      !is.finite(marker$hr_conf_low) ||
      !is.finite(marker$hr_conf_high)) {
    information <- cox_information_diagnostics(
      n_events,
      parameter_count,
      warnings = model_warnings,
      standard_fit_failed = TRUE
    )
    penalized_sensitivity <- fit_firth_sensitivity(
      formula,
      data,
      information,
      term = "expression_z",
      effect_label = "Expression per +1 SD"
    )
    return(list(
      model = model_id,
      label = label,
      covariates = as.list(encoded_covariates),
      covariate_encoding = covariate_encoding,
      status = "failed",
      reason = "The continuous model did not produce a finite marker HR and confidence interval.",
      ties = "efron",
      n_patients = nrow(data),
      n_events = n_events,
      information_diagnostics = information,
      penalized_sensitivity = penalized_sensitivity,
      warnings = as.list(unique(model_warnings))
    ))
  }

  information <- cox_information_diagnostics(
    n_events,
    parameter_count,
    warnings = model_warnings,
    hazard_ratio = marker$hazard_ratio,
    hr_conf_low = marker$hr_conf_low,
    hr_conf_high = marker$hr_conf_high
  )
  penalized_sensitivity <- fit_firth_sensitivity(
    formula,
    data,
    information,
    term = "expression_z",
    effect_label = "Expression per +1 SD"
  )
  information_warning <- cox_information_warning(information)
  if (!is.null(information_warning)) {
    model_warnings <- c(model_warnings, information_warning)
  }
  if (identical(penalized_sensitivity$status, "failed")) {
    model_warnings <- c(
      model_warnings,
      paste("Firth penalized sensitivity failed:", penalized_sensitivity$reason)
    )
  }

  ph_test <- tryCatch(cox.zph(model_fit), error = function(e) e)
  ph_p_value <- NA_real_
  ph_global_p_value <- NA_real_
  if (inherits(ph_test, "error")) {
    model_warnings <- c(model_warnings, paste("cox.zph failed:", conditionMessage(ph_test)))
  } else if (!is.null(ph_test$table) && "p" %in% colnames(ph_test$table)) {
    if ("expression_z" %in% rownames(ph_test$table)) {
      ph_p_value <- unname(ph_test$table["expression_z", "p"])
    }
    if ("GLOBAL" %in% rownames(ph_test$table)) {
      ph_global_p_value <- unname(ph_test$table["GLOBAL", "p"])
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
    data = data,
    formula_terms = formula_terms,
    marker_formula_term = "expression_z",
    marker_coefficient = "expression_z",
    effect_label = "Expression per +1 SD",
    ph_p_value = ph_p_value
  )
  if (length(model_warnings)) {
    cox_warning_messages <<- c(
      cox_warning_messages,
      paste(label, paste(unique(model_warnings), collapse = " | "), sep = ": ")
    )
  }
  list(
    model = model_id,
    label = label,
    covariates = as.list(encoded_covariates),
    covariate_encoding = covariate_encoding,
    status = "completed",
    ties = "efron",
    term = marker$term,
    contrast = "per +1 SD expression",
    n_patients = nrow(data),
    n_events = n_events,
    information_diagnostics = information,
    penalized_sensitivity = penalized_sensitivity,
    effect_unit = "per +1 SD expression",
    expression_center = continuous_center,
    expression_sd = continuous_scale,
    log_hr = marker$log_hr,
    standard_error = marker$standard_error,
    hazard_ratio = marker$hazard_ratio,
    hr_conf_low = marker$hr_conf_low,
    hr_conf_high = marker$hr_conf_high,
    p_value = marker$p_value,
    ph_p_value = ph_p_value,
    ph_global_p_value = ph_global_p_value,
    time_varying_effect = time_varying_effect,
    warnings = as.list(unique(model_warnings))
  )
}

fit_continuous_spline <- function() {
  data <- continuous_base[, c("time_days", "event", "expression_value", "expression_z"), drop = FALSE]
  data <- data[complete.cases(data), , drop = FALSE]
  n_events <- sum(data$event, na.rm = TRUE)
  if (nrow(data) < 20) {
    return(list(
      status = "skipped",
      reason = "Fewer than 20 complete patients were available for the spline model.",
      n_patients = nrow(data),
      n_events = n_events
    ))
  }
  if (n_events < MIN_SPLINE_EVENTS) {
    return(list(
      status = "skipped",
      reason = paste0(
        "Fewer than ",
        MIN_SPLINE_EVENTS,
        " events were available for the three-degree-of-freedom spline model."
      ),
      n_patients = nrow(data),
      n_events = n_events
    ))
  }
  if (length(unique(data$expression_value)) < 5) {
    return(list(
      status = "skipped",
      reason = "Fewer than five distinct expression values were available for spline fitting.",
      n_patients = nrow(data),
      n_events = n_events
    ))
  }

  knot_probabilities <- c(0.05, 0.35, 0.65, 0.95)
  knots_raw <- as.numeric(
    stats::quantile(
      data$expression_value,
      probs = knot_probabilities,
      na.rm = TRUE,
      names = FALSE,
      type = 7
    )
  )
  if (length(unique(knots_raw)) < 4) {
    return(list(
      status = "skipped",
      reason = "Spline knot percentiles were not distinct.",
      n_patients = nrow(data),
      n_events = n_events
    ))
  }
  knots_z <- (knots_raw - continuous_center) / continuous_scale
  internal_knots <- knots_z[c(2, 3)]
  boundary_knots <- knots_z[c(1, 4)]
  spline_basis <- splines::ns(
    data$expression_z,
    knots = internal_knots,
    Boundary.knots = boundary_knots,
    intercept = FALSE
  )
  colnames(spline_basis) <- paste0("spline_", seq_len(ncol(spline_basis)))
  spline_data <- cbind(data, as.data.frame(spline_basis))
  spline_terms <- colnames(spline_basis)
  spline_formula <- as.formula(
    paste("Surv(time_days, event) ~", paste(spline_terms, collapse = " + "))
  )
  model_warnings <- c()
  linear_fit <- tryCatch(
    withCallingHandlers(
      coxph(
        Surv(time_days, event) ~ expression_z,
        data = data,
        ties = "efron",
        x = TRUE
      ),
      warning = function(w) {
        model_warnings <<- c(model_warnings, paste("Linear model:", conditionMessage(w)))
        invokeRestart("muffleWarning")
      }
    ),
    error = function(e) e
  )
  spline_fit <- tryCatch(
    withCallingHandlers(
      coxph(spline_formula, data = spline_data, ties = "efron", x = TRUE),
      warning = function(w) {
        model_warnings <<- c(model_warnings, paste("Spline model:", conditionMessage(w)))
        invokeRestart("muffleWarning")
      }
    ),
    error = function(e) e
  )
  if (inherits(linear_fit, "error") || inherits(spline_fit, "error")) {
    reason <- if (inherits(spline_fit, "error")) {
      conditionMessage(spline_fit)
    } else {
      conditionMessage(linear_fit)
    }
    return(list(
      status = "failed",
      reason = reason,
      n_patients = nrow(data),
      n_events = n_events
    ))
  }

  linear_loglik <- as.numeric(logLik(linear_fit))
  spline_loglik <- as.numeric(logLik(spline_fit))
  nonlinear_df <- attr(logLik(spline_fit), "df") - attr(logLik(linear_fit), "df")
  nonlinear_chisq <- max(0, 2 * (spline_loglik - linear_loglik))
  nonlinearity_p_value <- stats::pchisq(
    nonlinear_chisq,
    df = nonlinear_df,
    lower.tail = FALSE
  )
  spline_summary <- summary(spline_fit)
  overall_p_value <- numeric_or_na(spline_summary$logtest[["pvalue"]])

  profile_probabilities <- seq(0.05, 0.95, by = 0.05)
  profile_raw <- as.numeric(
    stats::quantile(
      data$expression_value,
      probs = profile_probabilities,
      na.rm = TRUE,
      names = FALSE,
      type = 7
    )
  )
  reference_raw <- as.numeric(
    stats::quantile(
      data$expression_value,
      probs = 0.50,
      na.rm = TRUE,
      names = FALSE,
      type = 7
    )
  )
  profile_z <- (profile_raw - continuous_center) / continuous_scale
  reference_z <- (reference_raw - continuous_center) / continuous_scale
  profile_basis <- splines::ns(
    profile_z,
    knots = internal_knots,
    Boundary.knots = boundary_knots,
    intercept = FALSE
  )
  reference_basis <- splines::ns(
    reference_z,
    knots = internal_knots,
    Boundary.knots = boundary_knots,
    intercept = FALSE
  )
  coefficient <- stats::coef(spline_fit)
  covariance <- stats::vcov(spline_fit)
  profile <- lapply(seq_along(profile_probabilities), function(index) {
    contrast <- as.numeric(profile_basis[index, ] - reference_basis[1, ])
    log_hr <- sum(contrast * coefficient)
    standard_error <- sqrt(max(0, as.numeric(t(contrast) %*% covariance %*% contrast)))
    list(
      percentile = profile_probabilities[[index]] * 100,
      expression_value = profile_raw[[index]],
      expression_z = profile_z[[index]],
      hazard_ratio = exp(log_hr),
      hr_conf_low = exp(log_hr - 1.96 * standard_error),
      hr_conf_high = exp(log_hr + 1.96 * standard_error)
    )
  })

  ph_test <- tryCatch(cox.zph(spline_fit), error = function(e) e)
  ph_global_p_value <- NA_real_
  if (inherits(ph_test, "error")) {
    model_warnings <- c(model_warnings, paste("Spline cox.zph failed:", conditionMessage(ph_test)))
  } else if (!is.null(ph_test$table) &&
             "p" %in% colnames(ph_test$table) &&
             "GLOBAL" %in% rownames(ph_test$table)) {
    ph_global_p_value <- unname(ph_test$table["GLOBAL", "p"])
    if (is.finite(ph_global_p_value) && ph_global_p_value < 0.05) {
      model_warnings <- c(
        model_warnings,
        "Spline-model global proportional hazards test p < 0.05; the displayed shape is averaged over follow-up."
      )
    }
  }
  if (length(model_warnings)) {
    cox_warning_messages <<- c(
      cox_warning_messages,
      paste(
        "Univariable restricted cubic spline",
        paste(unique(model_warnings), collapse = " | "),
        sep = ": "
      )
    )
  }
  spline_information <- cox_information_diagnostics(
    n_events = n_events,
    parameter_count = length(spline_terms),
    warnings = model_warnings
  )
  list(
    status = "completed",
    method = "restricted cubic spline",
    implementation = "splines::ns with linear tails",
    n_patients = nrow(data),
    n_events = n_events,
    degrees_freedom = length(spline_terms),
    events_per_parameter = spline_information$events_per_parameter,
    information_diagnostics = spline_information,
    nonlinear_degrees_freedom = nonlinear_df,
    knot_percentiles = as.list(knot_probabilities * 100),
    knots_expression = as.list(knots_raw),
    knots_z = as.list(knots_z),
    reference_percentile = 50,
    reference_expression = reference_raw,
    reference_z = reference_z,
    overall_p_value = overall_p_value,
    nonlinearity_chisq = nonlinear_chisq,
    nonlinearity_p_value = nonlinearity_p_value,
    aic_linear = stats::AIC(linear_fit),
    aic_spline = stats::AIC(spline_fit),
    ph_global_p_value = ph_global_p_value,
    profile = profile,
    warnings = as.list(unique(model_warnings))
  )
}

if (nrow(continuous_base) > 0) {
  continuous_linear_models <- list(
    fit_continuous_linear_model(
      "continuous_univariable",
      "Continuous expression",
      character(0)
    ),
    fit_continuous_linear_model(
      "continuous_stage_adjusted",
      "Continuous expression adjusted for ordinal stage",
      c("stage")
    ),
    fit_continuous_linear_model(
      "continuous_grade_adjusted",
      "Continuous expression adjusted for ordinal grade",
      c("grade")
    ),
    fit_continuous_linear_model(
      "continuous_stage_grade_adjusted",
      "Continuous expression adjusted for ordinal stage and grade",
      c("stage", "grade")
    )
  )
  if (adjustment_requested) {
    continuous_linear_models <- c(
      continuous_linear_models,
      list(fit_continuous_linear_model(
        "continuous_user_adjusted",
        paste(
          "Continuous expression user-adjusted for",
          clinical_adjustment_label(
            requested_adjustment_covariates,
            requested_external_adjustment_covariates,
            external_covariate_definitions
          )
        ),
        requested_adjustment_covariates,
        requested_external_adjustment_covariates
      ))
    )
  }
  completed_continuous_models <- Filter(
    function(model) identical(model$status, "completed"),
    continuous_linear_models
  )
  continuous_spline <- fit_continuous_spline()
  continuous_analysis <- list(
    status = if (length(completed_continuous_models)) "completed" else "skipped",
    reason = if (length(completed_continuous_models)) NULL else "No continuous Cox model was estimable.",
    population = "unstratified expression-complete eligible cohort",
    cutpoint_independent = TRUE,
    n_patients = nrow(continuous_base),
    n_events = sum(continuous_base$event, na.rm = TRUE),
    predictor = list(
      source = "expression_value",
      scale = "within-analysis z-score",
      center = continuous_center,
      standard_deviation = continuous_scale,
      effect_unit = "hazard ratio per +1 SD expression"
    ),
    linear_models = continuous_linear_models,
    spline = continuous_spline
  )
}

fit_signature_interaction_model <- function(
  model_id,
  label,
  covariates,
  external_covariates = character()
) {
  external_record_names <- vapply(
    external_covariates,
    external_covariate_record_name,
    character(1)
  )
  data <- records[
    ,
    c(
      "time_days",
      "event",
      "expression_value_a",
      "expression_value_b",
      covariates,
      external_record_names
    ),
    drop = FALSE
  ]
  data$score_a_z <- zscore_vector(data$expression_value_a)
  data$score_b_z <- zscore_vector(data$expression_value_b)
  data <- data[is.finite(data$time_days) & !is.na(data$event) & is.finite(data$score_a_z) & is.finite(data$score_b_z), , drop = FALSE]
  prepared <- prepare_model_covariates(
    data,
    covariates,
    external_covariates,
    external_covariate_definitions
  )
  data <- prepared$data[, c("time_days", "event", "score_a_z", "score_b_z", prepared$covariates), drop = FALSE]
  encoded_covariates <- prepared$covariates
  covariate_encoding <- prepared$metadata
  data <- data[complete.cases(data), , drop = FALSE]
  data <- droplevels(data)
  if (nrow(data) < 10) {
    return(interaction_cox_skip(model_id, label, encoded_covariates, "Fewer than 10 complete patients after clinical covariate filtering.", data, covariate_encoding))
  }
  if (sum(data$event, na.rm = TRUE) < MIN_MODEL_EVENTS) {
    return(interaction_cox_skip(
      model_id,
      label,
      encoded_covariates,
      paste0("Fewer than ", MIN_MODEL_EVENTS, " events after clinical covariate filtering."),
      data,
      covariate_encoding
    ))
  }
  if (length(unique(data$score_a_z)) < 2 || length(unique(data$score_b_z)) < 2) {
    return(interaction_cox_skip(model_id, label, encoded_covariates, "Both signature scores require variation after filtering.", data, covariate_encoding))
  }
  for (covariate in encoded_covariates) {
    if (!model_covariate_has_variation(data[[covariate]])) {
      return(interaction_cox_skip(model_id, label, encoded_covariates, paste0("Clinical covariate ", covariate, " has fewer than two observed values after filtering."), data, covariate_encoding))
    }
  }

  formula_terms <- c("score_a_z * score_b_z", encoded_covariates)
  formula <- as.formula(paste("Surv(time_days, event) ~", paste(formula_terms, collapse = " + ")))
  parameter_count <- cox_parameter_count(formula, data)
  n_events <- sum(data$event, na.rm = TRUE)
  model_warnings <- c()
  fit <- tryCatch(
    withCallingHandlers(
      coxph(formula, data = data, ties = "efron"),
      warning = function(w) {
        model_warnings <<- c(model_warnings, conditionMessage(w))
        invokeRestart("muffleWarning")
      }
    ),
    error = function(e) e
  )
  if (inherits(fit, "error")) {
    information <- cox_information_diagnostics(
      n_events,
      parameter_count,
      warnings = c(model_warnings, conditionMessage(fit)),
      standard_fit_failed = TRUE
    )
    penalized_sensitivity <- fit_firth_sensitivity(
      formula,
      data,
      information,
      term = "score_a_z:score_b_z",
      effect_label = "Signature A x Signature B"
    )
    return(list(
      model = model_id,
      label = label,
      covariates = as.list(encoded_covariates),
      covariate_encoding = covariate_encoding,
      status = "failed",
      reason = conditionMessage(fit),
      ties = "efron",
      n_patients = nrow(data),
      n_events = n_events,
      information_diagnostics = information,
      penalized_sensitivity = penalized_sensitivity,
      warnings = as.list(unique(model_warnings))
    ))
  }

  cox_summary <- summary(fit)
  terms <- Filter(Negate(is.null), list(
    extract_cox_term(cox_summary, "score_a_z", "Signature A score"),
    extract_cox_term(cox_summary, "score_b_z", "Signature B score"),
    extract_cox_term(cox_summary, "score_a_z:score_b_z", "Signature A x Signature B")
  ))
  interaction_indexes <- which(vapply(terms, function(item) item$term == "score_a_z:score_b_z", logical(1)))
  interaction_term <- if (length(interaction_indexes)) terms[[interaction_indexes[[1]]]] else NULL
  if (is.null(interaction_term)) {
    return(interaction_cox_skip(model_id, label, encoded_covariates, "Could not isolate the signature interaction coefficient.", data, covariate_encoding))
  }
  if (!is.finite(interaction_term$hazard_ratio) || !is.finite(interaction_term$hr_conf_low) || !is.finite(interaction_term$hr_conf_high)) {
    information <- cox_information_diagnostics(
      n_events,
      parameter_count,
      warnings = model_warnings,
      standard_fit_failed = TRUE
    )
    penalized_sensitivity <- fit_firth_sensitivity(
      formula,
      data,
      information,
      term = "score_a_z:score_b_z",
      effect_label = "Signature A x Signature B"
    )
    return(list(
      model = model_id,
      label = label,
      covariates = as.list(encoded_covariates),
      covariate_encoding = covariate_encoding,
      status = "failed",
      reason = "Interaction model did not produce finite HR confidence intervals.",
      ties = "efron",
      n_patients = nrow(data),
      n_events = n_events,
      information_diagnostics = information,
      penalized_sensitivity = penalized_sensitivity,
      warnings = as.list(unique(model_warnings))
    ))
  }

  information <- cox_information_diagnostics(
    n_events,
    parameter_count,
    warnings = model_warnings,
    hazard_ratio = interaction_term$hazard_ratio,
    hr_conf_low = interaction_term$hr_conf_low,
    hr_conf_high = interaction_term$hr_conf_high
  )
  penalized_sensitivity <- fit_firth_sensitivity(
    formula,
    data,
    information,
    term = "score_a_z:score_b_z",
    effect_label = "Signature A x Signature B"
  )
  information_warning <- cox_information_warning(information)
  if (!is.null(information_warning)) {
    model_warnings <- c(model_warnings, information_warning)
  }
  if (identical(penalized_sensitivity$status, "failed")) {
    model_warnings <- c(
      model_warnings,
      paste("Firth penalized sensitivity failed:", penalized_sensitivity$reason)
    )
  }

  ph_test <- tryCatch(cox.zph(fit), error = function(e) e)
  ph_p_value <- NA_real_
  ph_global_p_value <- NA_real_
  if (inherits(ph_test, "error")) {
    model_warnings <- c(model_warnings, paste("cox.zph failed:", conditionMessage(ph_test)))
  } else if (!is.null(ph_test$table) && "p" %in% colnames(ph_test$table)) {
    if ("score_a_z:score_b_z" %in% rownames(ph_test$table)) {
      ph_p_value <- unname(ph_test$table["score_a_z:score_b_z", "p"])
    }
    if ("GLOBAL" %in% rownames(ph_test$table)) {
      ph_global_p_value <- unname(ph_test$table["GLOBAL", "p"])
    }
    if (is.finite(ph_p_value) && ph_p_value < 0.05) {
      model_warnings <- c(
        model_warnings,
        paste(
          "Interaction-specific proportional hazards test p < 0.05; interpret",
          "the average interaction HR with the prespecified two-year temporal diagnostic."
        )
      )
    } else if (is.finite(ph_global_p_value) && ph_global_p_value < 0.05) {
      model_warnings <- c(
        model_warnings,
        "Global proportional hazards test p < 0.05 while the signature interaction term was not flagged."
      )
    }
  }
  time_varying_effect <- fit_prespecified_time_varying_effect(
    data = data,
    formula_terms = formula_terms,
    marker_formula_term = "score_a_z:score_b_z",
    marker_coefficient = "score_a_z:score_b_z",
    effect_label = "Signature A x Signature B",
    ph_p_value = ph_p_value
  )

  list(
    model = model_id,
    label = label,
    covariates = as.list(encoded_covariates),
    covariate_encoding = covariate_encoding,
    status = "completed",
    ties = "efron",
    n_patients = nrow(data),
    n_events = n_events,
    information_diagnostics = information,
    penalized_sensitivity = penalized_sensitivity,
    score_scale = "within-analysis z-score",
    interaction_term = interaction_term,
    terms = terms,
    ph_p_value = ph_p_value,
    ph_global_p_value = ph_global_p_value,
    time_varying_effect = time_varying_effect,
    warnings = as.list(unique(model_warnings))
  )
}

if (any(is.finite(records$expression_value_a)) && any(is.finite(records$expression_value_b))) {
  signature_interaction_cox_models <- list(
    fit_signature_interaction_model("signature_interaction", "Signature interaction", character(0)),
    fit_signature_interaction_model("signature_interaction_stage_adjusted", "Signature interaction adjusted for ordinal stage", c("stage")),
    fit_signature_interaction_model("signature_interaction_grade_adjusted", "Signature interaction adjusted for ordinal grade", c("grade")),
    fit_signature_interaction_model("signature_interaction_stage_grade_adjusted", "Signature interaction adjusted for ordinal stage and grade", c("stage", "grade"))
  )
  if (adjustment_requested) {
    signature_interaction_cox_models <- c(
      signature_interaction_cox_models,
      list(fit_signature_interaction_model(
        "signature_interaction_user_adjusted",
        paste(
          "Signature interaction user-adjusted for",
          clinical_adjustment_label(
            requested_adjustment_covariates,
            requested_external_adjustment_covariates,
            external_covariate_definitions
          )
        ),
        requested_adjustment_covariates,
        requested_external_adjustment_covariates
      ))
    )
  }
}

group_counts <- as.list(table(records$group))
event_counts <- as.list(tapply(records$event, records$group, sum))
median_table <- as.data.frame(summary(fit)$table)
median_survival <- list()
if (nrow(median_table) > 0 && "median" %in% colnames(median_table)) {
  for (row_name in rownames(median_table)) {
    group_name <- sub("^group=", "", row_name)
    median_value <- unname(median_table[row_name, "median"])
    if (!is.finite(median_value)) {
      median_value <- NA_real_
    }
    median_survival[[group_name]] <- median_value
  }
}

plot_style <- payload$plot_style %||% list()
fallback_palette <- c("#1f6f8b", "#c8842d", "#b94d48", "#5a6f9f", "#6c7a77", "#7b6aa8", "#3c8c5f", "#c46a42", "#4b5f5b")
requested_palette <- unlist(plot_style$palette %||% fallback_palette)
if (n_groups == 2 && length(requested_palette) >= 3) {
  requested_palette <- requested_palette[c(1, 3)]
}
palette <- requested_palette
palette <- unique(c(palette, fallback_palette))
if (length(palette) < length(levels(records$group))) {
  palette <- unique(c(palette, grDevices::hcl.colors(length(levels(records$group)), "Dark 3")))
}
palette <- unname(palette[seq_len(length(levels(records$group)))])

font_family <- plot_style$font_family %||% "sans"
base_font_size <- as.numeric(plot_style$base_font_size %||% 12)
if (is.na(base_font_size) || base_font_size < 8 || base_font_size > 20) {
  base_font_size <- 12
}
axis_text_size <- as.numeric(plot_style$axis_text_size %||% 11)
if (is.na(axis_text_size) || axis_text_size < 6 || axis_text_size > 24) {
  axis_text_size <- 11
}
axis_title_size <- as.numeric(plot_style$axis_title_size %||% 12)
if (is.na(axis_title_size) || axis_title_size < 6 || axis_title_size > 26) {
  axis_title_size <- 12
}
show_grid <- if (is.null(plot_style$show_grid)) FALSE else isTRUE(plot_style$show_grid)
plot_aspect <- plot_style$plot_aspect %||% "rectangular"
if (!plot_aspect %in% c("rectangular", "square")) {
  plot_aspect <- "rectangular"
}

safe_plot_color <- function(value, fallback) {
  candidates <- as.character(value %||% fallback)
  candidate <- if (length(candidates)) candidates[[1]] else fallback
  if (is.na(candidate) || !nzchar(trimws(candidate))) {
    return(fallback)
  }
  candidate <- trimws(candidate)
  tryCatch(
    {
      grDevices::col2rgb(candidate)
      candidate
    },
    error = function(...) fallback
  )
}

plot_label_or <- function(value, fallback) {
  candidates <- as.character(value %||% "")
  candidate <- if (length(candidates)) trimws(candidates[[1]]) else ""
  if (!is.na(candidate) && nzchar(candidate)) candidate else fallback
}

show_title <- isTRUE(plot_style$show_title)
custom_title <- plot_style$plot_title %||% ""
title <- NULL
if (show_title) {
  title <- if (nzchar(custom_title)) {
    custom_title
  } else {
    paste(payload$cohort, payload$gene_symbol, tolower(endpoint_label))
  }
}
expression_label <- payload$expression_scale_label %||% "Expression"
continuous_plot_style <- plot_style$continuous %||% list()
continuous_effect_color <- safe_plot_color(
  continuous_plot_style$effect_color,
  "#1f6f8b"
)
continuous_reference_color <- safe_plot_color(
  continuous_plot_style$reference_color,
  "#75817e"
)
continuous_show_title <- if (is.null(continuous_plot_style$show_title)) {
  TRUE
} else {
  isTRUE(continuous_plot_style$show_title)
}
continuous_plot_title <- plot_label_or(
  continuous_plot_style$plot_title,
  "Continuous expression effect"
)
continuous_x_axis_title <- plot_label_or(
  continuous_plot_style$x_axis_title,
  paste(payload$gene_symbol, expression_label)
)
continuous_y_axis_title <- plot_label_or(
  continuous_plot_style$y_axis_title,
  "Hazard ratio relative to median"
)
cox_forest_style <- plot_style$cox_forest %||% list()
cox_lower_hazard_color <- safe_plot_color(
  cox_forest_style$lower_hazard_color,
  "#1f6f8b"
)
cox_higher_hazard_color <- safe_plot_color(
  cox_forest_style$higher_hazard_color,
  "#b94d48"
)
cox_reference_color <- safe_plot_color(
  cox_forest_style$reference_color,
  "#7b8582"
)
cox_show_title <- if (is.null(cox_forest_style$show_title)) {
  TRUE
} else {
  isTRUE(cox_forest_style$show_title)
}
cox_plot_title <- plot_label_or(
  cox_forest_style$plot_title,
  "Cox proportional hazards models"
)
cox_x_axis_title <- plot_label_or(
  cox_forest_style$x_axis_title,
  "Hazard ratio (log scale)"
)
plot_theme <- theme_minimal(base_size = base_font_size, base_family = font_family) +
  theme(
    axis.text = element_text(size = axis_text_size),
    axis.title = element_text(size = axis_title_size),
    panel.grid.major = if (show_grid) element_line(color = "#e1e7e4", linewidth = 0.35) else element_blank(),
    panel.grid.minor = if (show_grid) element_line(color = "#edf1ef", linewidth = 0.2) else element_blank()
  )

competing_risks <- fit_competing_risks_analysis(
  records = records,
  continuous_records = continuous_records,
  endpoint = payload$endpoint %||% "OS",
  group_levels = group_levels,
  requested_adjustment_covariates = requested_adjustment_covariates,
  requested_external_adjustment_covariates = requested_external_adjustment_covariates,
  external_covariate_definitions = external_covariate_definitions,
  time_divisor = time_divisor,
  time_label = time_label,
  palette = palette,
  plot_theme = plot_theme,
  output_png = payload$cumulative_incidence_png_path %||% "",
  output_svg = payload$cumulative_incidence_svg_path %||% "",
  render_png = isTRUE(payload$render_png),
  render_svg = isTRUE(payload$render_svg),
  plot_aspect = plot_aspect
)

format_p_value <- function(value) {
  if (is.na(value)) {
    return("p = NA")
  }
  if (value < 0.001) {
    return("p < 0.001")
  }
  paste0("p = ", formatC(value, format = "f", digits = 3))
}
p_value_label <- format_p_value(p_value)
continuous_effect_plot <- NULL
continuous_spline <- continuous_analysis$spline %||% list()
if (identical(continuous_spline$status, "completed") &&
    length(continuous_spline$profile %||% list()) > 1) {
  continuous_profile_data <- do.call(
    rbind,
    lapply(continuous_spline$profile, function(point) {
      data.frame(
        percentile = as.numeric(point$percentile),
        expression_value = as.numeric(point$expression_value),
        hazard_ratio = as.numeric(point$hazard_ratio),
        hr_conf_low = as.numeric(point$hr_conf_low),
        hr_conf_high = as.numeric(point$hr_conf_high),
        stringsAsFactors = FALSE
      )
    })
  )
  continuous_profile_data <- continuous_profile_data[
    is.finite(continuous_profile_data$expression_value) &
      is.finite(continuous_profile_data$hazard_ratio) &
      is.finite(continuous_profile_data$hr_conf_low) &
      is.finite(continuous_profile_data$hr_conf_high) &
      continuous_profile_data$hazard_ratio > 0 &
      continuous_profile_data$hr_conf_low > 0 &
      continuous_profile_data$hr_conf_high > 0,
    ,
    drop = FALSE
  ]
  if (nrow(continuous_profile_data) > 1) {
    nonlinearity_label <- paste(
      "Spline vs linear",
      format_p_value(as.numeric(continuous_spline$nonlinearity_p_value))
    )
    continuous_effect_plot <- ggplot(
      continuous_profile_data,
      aes(x = expression_value, y = hazard_ratio)
    ) +
      geom_ribbon(
        aes(ymin = hr_conf_low, ymax = hr_conf_high),
        fill = continuous_effect_color,
        alpha = 0.16,
        linewidth = 0
      ) +
      geom_hline(
        yintercept = 1,
        color = continuous_reference_color,
        linewidth = 0.5,
        linetype = "dashed"
      ) +
      geom_vline(
        xintercept = as.numeric(continuous_spline$reference_expression),
        color = continuous_reference_color,
        linewidth = 0.45,
        linetype = "dotted"
      ) +
      geom_line(color = continuous_effect_color, linewidth = 1.15, lineend = "round") +
      scale_y_log10() +
      labs(
        title = if (continuous_show_title) continuous_plot_title else NULL,
        subtitle = paste(
          "Restricted cubic spline HR relative to median;",
          nonlinearity_label
        ),
        x = continuous_x_axis_title,
        y = continuous_y_axis_title
      ) +
      plot_theme +
      theme(
        plot.title = element_text(face = "bold", size = base_font_size + 3),
        plot.subtitle = element_text(
          color = "#586864",
          size = base_font_size,
          margin = margin(b = 10)
        ),
        panel.grid.minor = element_blank()
      )
  }
}
risk_table_height <- if (isTRUE(payload$show_risk_table)) {
  ifelse(n_groups <= 4, 0.25, min(0.45, 0.25 + (n_groups - 4) * 0.04))
} else {
  0
}

plot_obj <- ggsurvplot(
  plot_fit,
  data = records,
  conf.int = isTRUE(payload$show_confidence_interval),
  risk.table = isTRUE(payload$show_risk_table),
  risk.table.height = risk_table_height,
  pval = FALSE,
  pval.method = FALSE,
  censor = TRUE,
  xlab = time_label,
  ylab = paste(endpoint_label, "probability"),
  title = title,
  legend.title = "Expression group",
  legend.labs = group_levels,
  palette = palette,
  ggtheme = plot_theme
)

if (plot_aspect == "square") {
  plot_obj$plot <- plot_obj$plot + theme(aspect.ratio = 1)
}
if (isTRUE(payload$show_risk_table) && !is.null(plot_obj$table)) {
  plot_obj$table <- plot_obj$table +
    scale_y_discrete(labels = function(value) sub("^group=", "", value))
}

plot_obj$plot <- plot_obj$plot +
  annotate(
    "text",
    x = Inf,
    y = Inf,
    label = p_value_label,
    hjust = 1.05,
    vjust = 1.35,
    size = base_font_size / ggplot2::.pt,
    family = font_family,
    fontface = "bold"
  )

completed_cox_models <- Filter(function(model) {
  !is.null(model$status) && identical(model$status, "completed")
}, cox_models)

cox_forest_plot <- NULL
if (length(completed_cox_models) > 0) {
  cox_plot_data <- do.call(rbind, lapply(seq_along(completed_cox_models), function(index) {
    model <- completed_cox_models[[index]]
    data.frame(
      order = index,
      label = model$label,
      n_patients = model$n_patients,
      n_events = model$n_events,
      hazard_ratio = model$hazard_ratio,
      hr_conf_low = model$hr_conf_low,
      hr_conf_high = model$hr_conf_high,
      p_value = model$p_value,
      stringsAsFactors = FALSE
    )
  }))
  cox_plot_data$label <- factor(cox_plot_data$label, levels = rev(cox_plot_data$label))
  cox_plot_data$direction <- ifelse(cox_plot_data$hazard_ratio >= 1, "Higher hazard", "Lower hazard")
  cox_plot_data$estimate_label <- paste0(
    sprintf("%.2f", cox_plot_data$hazard_ratio),
    " (",
    sprintf("%.2f", cox_plot_data$hr_conf_low),
    "-",
    sprintf("%.2f", cox_plot_data$hr_conf_high),
    ")"
  )
  cox_plot_data$p_label <- vapply(cox_plot_data$p_value, format_p_value, character(1))
  cox_x_values <- c(cox_plot_data$hr_conf_low, cox_plot_data$hazard_ratio, cox_plot_data$hr_conf_high)
  cox_x_values <- cox_x_values[is.finite(cox_x_values) & cox_x_values > 0]
  cox_x_min <- min(0.25, min(cox_x_values, na.rm = TRUE) * 0.82)
  cox_x_max <- max(4, max(cox_x_values, na.rm = TRUE) * 1.18)
  cox_forest_panel <- ggplot(cox_plot_data, aes(x = hazard_ratio, y = label)) +
    geom_vline(xintercept = 1, color = cox_reference_color, linewidth = 0.45, linetype = "dashed") +
    geom_segment(aes(x = hr_conf_low, xend = hr_conf_high, yend = label, color = direction), linewidth = 1.0) +
    geom_point(aes(color = direction), size = 3.4) +
    scale_x_log10(limits = c(cox_x_min, cox_x_max)) +
    scale_color_manual(
      values = c(
        "Higher hazard" = cox_higher_hazard_color,
        "Lower hazard" = cox_lower_hazard_color
      ),
      guide = "none"
    ) +
    labs(
      x = cox_x_axis_title,
      y = NULL
    ) +
    plot_theme +
    theme(
      panel.grid.minor = element_blank()
    )
  cox_table_panel <- ggplot(cox_plot_data, aes(y = label)) +
    geom_text(
      aes(x = 0, label = estimate_label),
      hjust = 0,
      size = base_font_size / ggplot2::.pt,
      family = font_family,
      color = "#18221f"
    ) +
    geom_text(
      aes(x = 1, label = p_label),
      hjust = 1,
      size = base_font_size / ggplot2::.pt,
      family = font_family,
      color = "#18221f"
    ) +
    scale_x_continuous(limits = c(0, 1), expand = expansion(mult = c(0, 0))) +
    scale_y_discrete(drop = FALSE) +
    labs(x = NULL, y = NULL) +
    theme_void(base_size = base_font_size, base_family = font_family) +
    theme(
      plot.margin = margin(5.5, 12, 5.5, 8)
    )
  cox_forest_header <- cowplot::ggdraw() +
    cowplot::draw_label(
      "Model",
      x = 0.02,
      hjust = 0,
      size = base_font_size,
      fontfamily = font_family,
      fontface = "bold"
    )
  cox_table_header <- cowplot::ggdraw() +
    cowplot::draw_label(
      "Estimate (95% CI)",
      x = 0,
      hjust = 0,
      size = base_font_size,
      fontfamily = font_family,
      fontface = "bold"
    ) +
    cowplot::draw_label(
      "p-value",
      x = 1,
      hjust = 1,
      size = base_font_size,
      fontfamily = font_family,
      fontface = "bold"
    )
  cox_forest_column <- cowplot::plot_grid(
    cox_forest_header,
    cox_forest_panel,
    ncol = 1,
    rel_heights = c(0.12, 1)
  )
  cox_table_column <- cowplot::plot_grid(
    cox_table_header,
    cox_table_panel,
    ncol = 1,
    rel_heights = c(0.12, 1)
  )
  cox_body <- cowplot::plot_grid(
    cox_forest_column,
    cox_table_column,
    nrow = 1,
    rel_widths = c(1.7, 1.15),
    align = "h",
    axis = "tb"
  )
  cox_body_height <- if (cox_show_title) 0.82 else 0.88
  cox_subtitle_y <- if (cox_show_title) 0.90 else 0.97
  cox_forest_plot <- cowplot::ggdraw()
  if (cox_show_title) {
    cox_forest_plot <- cox_forest_plot + cowplot::draw_label(
      cox_plot_title,
      x = 0.03,
      y = 0.98,
      hjust = 0,
      vjust = 1,
      size = base_font_size + 4,
      fontfamily = font_family,
      fontface = "bold"
    )
  }
  cox_forest_plot <- cox_forest_plot +
    cowplot::draw_label(
      paste(group_levels[[2]], "vs", group_levels[[1]], "expression group"),
      x = 0.03,
      y = cox_subtitle_y,
      hjust = 0,
      vjust = 1,
      size = base_font_size + 1,
      fontfamily = font_family,
      color = "#586864"
    ) +
    cowplot::draw_plot(cox_body, x = 0, y = 0, width = 1, height = cox_body_height)
}

render_png <- isTRUE(payload$render_png %||% TRUE)
render_svg <- isTRUE(payload$render_svg %||% TRUE)
png_width <- 1600
base_rectangular_height <- 950
png_height_with_table <- max(1250, ceiling(base_rectangular_height / (1 - risk_table_height)))
png_height <- if (plot_aspect == "square") {
  ifelse(isTRUE(payload$show_risk_table), ceiling(png_width / (1 - risk_table_height)), 1600)
} else {
  ifelse(isTRUE(payload$show_risk_table), png_height_with_table, base_rectangular_height)
}
svg_width <- 10
base_rectangular_svg_height <- 6.0
svg_height_with_table <- max(7.8, base_rectangular_svg_height / (1 - risk_table_height))
svg_height <- if (plot_aspect == "square") {
  ifelse(isTRUE(payload$show_risk_table), svg_width / (1 - risk_table_height), 10)
} else {
  ifelse(isTRUE(payload$show_risk_table), svg_height_with_table, base_rectangular_svg_height)
}

if (render_png) {
  png(payload$png_path, width = png_width, height = png_height, res = 180)
  print(plot_obj)
  dev.off()
  if (!is.null(cox_forest_plot) && !is.null(payload$cox_forest_png_path)) {
    png(payload$cox_forest_png_path, width = 1500, height = max(620, 260 + length(completed_cox_models) * 90), res = 180)
    print(cox_forest_plot)
    dev.off()
  }
  if (!is.null(continuous_effect_plot) && !is.null(payload$continuous_effect_png_path)) {
    continuous_png_height <- if (plot_aspect == "square") 1500 else 900
    png(payload$continuous_effect_png_path, width = 1500, height = continuous_png_height, res = 180)
    print(continuous_effect_plot)
    dev.off()
  }
}

if (render_svg) {
  svglite(payload$svg_path, width = svg_width, height = svg_height)
  print(plot_obj)
  dev.off()
  if (!is.null(cox_forest_plot) && !is.null(payload$cox_forest_svg_path)) {
    svglite(payload$cox_forest_svg_path, width = 9.5, height = max(3.8, 1.8 + length(completed_cox_models) * 0.55))
    print(cox_forest_plot)
    dev.off()
  }
  if (!is.null(continuous_effect_plot) && !is.null(payload$continuous_effect_svg_path)) {
    continuous_svg_height <- if (plot_aspect == "square") 9.5 else 5.7
    svglite(payload$continuous_effect_svg_path, width = 9.5, height = continuous_svg_height)
    print(continuous_effect_plot)
    dev.off()
  }
}

warnings <- list()
if (length(cox_warning_messages)) {
  warnings <- as.list(paste("Cox model warning:", unique(cox_warning_messages)))
}

software_versions <- list(
  R = R.version.string,
  jsonlite = as.character(packageVersion("jsonlite")),
  survival = as.character(packageVersion("survival")),
  survminer = as.character(packageVersion("survminer")),
  maxstat = if (requireNamespace("maxstat", quietly = TRUE)) as.character(packageVersion("maxstat")) else "not available",
  ggplot2 = as.character(packageVersion("ggplot2")),
  svglite = as.character(packageVersion("svglite")),
  survRM2 = if (requireNamespace("survRM2", quietly = TRUE)) as.character(packageVersion("survRM2")) else "not available",
  coxphf = if (requireNamespace("coxphf", quietly = TRUE)) as.character(packageVersion("coxphf")) else "not available",
  cmprsk = if (requireNamespace("cmprsk", quietly = TRUE)) as.character(packageVersion("cmprsk")) else "not available"
)

clinical_adjustment_output <- list(
  status = if (adjustment_requested) "requested" else "not_requested",
  requested_covariates = as.list(requested_adjustment_covariates),
  label = if (adjustment_requested) {
    clinical_adjustment_label(
      requested_adjustment_covariates,
      requested_external_adjustment_covariates,
      external_covariate_definitions
    )
  } else {
    NULL
  },
  grouped_model = if (adjustment_requested) "user_adjusted" else NULL,
  continuous_model = if (adjustment_requested) "continuous_user_adjusted" else NULL,
  interaction_model = if (adjustment_requested) "signature_interaction_user_adjusted" else NULL
)
if (length(requested_external_adjustment_covariates)) {
  clinical_adjustment_output$requested_external_covariates <- as.list(
    requested_external_adjustment_covariates
  )
  clinical_adjustment_output$external_covariate_definitions <- external_covariate_definitions
  clinical_adjustment_output$external_covariate_qc <- payload$external_covariate_qc %||% list()
}

metrics <- c(
  list(
    n_patients = nrow(records),
    n_events = sum(records$event),
    endpoint = payload$endpoint %||% "OS",
    endpoint_label = endpoint_label,
    time_unit = time_unit,
    time_axis_label = time_label,
    expression_scale = payload$expression_scale,
    expression_scale_label = expression_label,
    logrank_p_value = p_value,
    group_counts = group_counts,
    event_counts = event_counts,
    median_survival_days = median_survival,
    rmst = rmst,
    competing_risks = competing_risks,
    clinical_adjustment = clinical_adjustment_output,
    continuous_analysis = continuous_analysis,
    cox_models = cox_models,
    signature_interaction_cox_models = signature_interaction_cox_models,
    cutpoint_details = payload$cutpoint_details,
    warnings = warnings,
    software_versions = software_versions
  ),
  cox_metrics
)

write_json(metrics, payload$output_path, pretty = TRUE, auto_unbox = TRUE, null = "null", na = "null", digits = 16)
