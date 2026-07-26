MODEL_EPV_CAUTION_THRESHOLD <- 10
MODEL_EPV_SEVERE_THRESHOLD <- 5
FIRTH_PENALTY <- 0.5

cox_parameter_count <- function(formula, data) {
  matrix <- tryCatch(
    stats::model.matrix(formula, data = data),
    error = function(e) NULL
  )
  if (is.null(matrix)) {
    return(NA_integer_)
  }
  keep <- colnames(matrix) != "(Intercept)"
  as.integer(sum(keep))
}

cox_warning_indicates_instability <- function(warnings) {
  if (!length(warnings)) {
    return(FALSE)
  }
  any(grepl(
    "converg|infinite|singular|overflow|failed",
    paste(warnings, collapse = " "),
    ignore.case = TRUE
  ))
}

cox_information_diagnostics <- function(
  n_events,
  parameter_count,
  warnings = character(),
  hazard_ratio = NA_real_,
  hr_conf_low = NA_real_,
  hr_conf_high = NA_real_,
  standard_fit_failed = FALSE
) {
  n_events <- suppressWarnings(as.numeric(n_events))
  parameter_count <- suppressWarnings(as.integer(parameter_count))
  events_per_parameter <- if (
    length(n_events) &&
      is.finite(n_events[[1]]) &&
      length(parameter_count) &&
      !is.na(parameter_count[[1]]) &&
      parameter_count[[1]] > 0
  ) {
    unname(n_events[[1]] / parameter_count[[1]])
  } else {
    NA_real_
  }
  status <- if (!is.finite(events_per_parameter)) {
    "not_evaluable"
  } else if (events_per_parameter < MODEL_EPV_SEVERE_THRESHOLD) {
    "severe"
  } else if (events_per_parameter < MODEL_EPV_CAUTION_THRESHOLD) {
    "caution"
  } else {
    "adequate"
  }

  standard_fit_instability <- standard_fit_failed ||
    cox_warning_indicates_instability(warnings)
  finite_effect <- all(is.finite(c(hazard_ratio, hr_conf_low, hr_conf_high)))
  extreme_marker_estimate <- finite_effect && (
    hazard_ratio < 0.1 ||
      hazard_ratio > 10 ||
      hr_conf_high / hr_conf_low > 100
  )

  trigger_reasons <- character()
  if (is.finite(events_per_parameter) &&
      events_per_parameter < MODEL_EPV_CAUTION_THRESHOLD) {
    trigger_reasons <- c(
      trigger_reasons,
      sprintf(
        "%.2f events per fitted parameter is below the prespecified threshold of %d.",
        events_per_parameter,
        MODEL_EPV_CAUTION_THRESHOLD
      )
    )
  }
  if (standard_fit_instability) {
    trigger_reasons <- c(
      trigger_reasons,
      "The standard Cox fit reported a convergence, singularity or infinite-coefficient concern."
    )
  }
  if (extreme_marker_estimate) {
    trigger_reasons <- c(
      trigger_reasons,
      "The standard Cox marker estimate or confidence interval was extreme."
    )
  }

  list(
    parameter_count = if (length(parameter_count)) parameter_count[[1]] else NA_integer_,
    n_events = if (length(n_events)) n_events[[1]] else NA_real_,
    events_per_parameter = events_per_parameter,
    caution_threshold = MODEL_EPV_CAUTION_THRESHOLD,
    severe_threshold = MODEL_EPV_SEVERE_THRESHOLD,
    status = status,
    low_information = status %in% c("caution", "severe"),
    severe_low_information = identical(status, "severe"),
    standard_fit_instability = standard_fit_instability,
    extreme_marker_estimate = extreme_marker_estimate,
    penalized_sensitivity_recommended = length(trigger_reasons) > 0,
    trigger_reasons = as.list(unique(trigger_reasons))
  )
}

cox_information_warning <- function(information) {
  events_per_parameter <- suppressWarnings(as.numeric(
    information$events_per_parameter
  ))
  if (!length(events_per_parameter) || !is.finite(events_per_parameter[[1]])) {
    return(NULL)
  }
  if (identical(information$status, "severe")) {
    return(sprintf(
      paste(
        "Severe low-information Cox model: %.2f events per fitted parameter",
        "(< %d). Maximum-likelihood estimates may be unstable; inspect the",
        "Firth penalized sensitivity."
      ),
      events_per_parameter[[1]],
      MODEL_EPV_SEVERE_THRESHOLD
    ))
  }
  if (identical(information$status, "caution")) {
    return(sprintf(
      paste(
        "Low-information Cox model: %.2f events per fitted parameter",
        "(< %d). Interpret maximum-likelihood estimates cautiously and compare",
        "the Firth penalized sensitivity."
      ),
      events_per_parameter[[1]],
      MODEL_EPV_CAUTION_THRESHOLD
    ))
  }
  NULL
}

firth_sensitivity_not_triggered <- function(information) {
  list(
    status = "not_triggered",
    reason = paste(
      "The standard Cox fit had at least",
      MODEL_EPV_CAUTION_THRESHOLD,
      "events per fitted parameter and no instability trigger."
    ),
    method = "Firth penalized partial likelihood",
    package = "coxphf",
    penalty = FIRTH_PENALTY,
    trigger_reasons = information$trigger_reasons
  )
}

fit_firth_sensitivity <- function(
  formula,
  data,
  information,
  term = NULL,
  term_pattern = NULL,
  effect_label = NULL
) {
  if (!isTRUE(information$penalized_sensitivity_recommended)) {
    return(firth_sensitivity_not_triggered(information))
  }
  if (!requireNamespace("coxphf", quietly = TRUE)) {
    return(list(
      status = "failed",
      reason = "The coxphf package is not installed.",
      method = "Firth penalized partial likelihood",
      package = "coxphf",
      penalty = FIRTH_PENALTY,
      trigger_reasons = information$trigger_reasons
    ))
  }

  fit_warnings <- character()
  run_fit <- function(maxit, maxstep) {
    tryCatch(
      withCallingHandlers(
        coxphf::coxphf(
          formula = formula,
          data = data,
          pl = TRUE,
          maxit = maxit,
          maxstep = maxstep,
          firth = TRUE,
          penalty = FIRTH_PENALTY
        ),
        warning = function(w) {
          fit_warnings <<- c(fit_warnings, conditionMessage(w))
          invokeRestart("muffleWarning")
        }
      ),
      error = function(e) e
    )
  }

  fit <- run_fit(maxit = 200, maxstep = 0.5)
  if (inherits(fit, "error") || cox_warning_indicates_instability(fit_warnings)) {
    if (inherits(fit, "error")) {
      fit_warnings <- c(
        fit_warnings,
        paste("Initial Firth fit failed:", conditionMessage(fit))
      )
    }
    fit_warnings <- c(fit_warnings, "Retried with maxit=500 and maxstep=0.1.")
    fit <- run_fit(maxit = 500, maxstep = 0.1)
  }
  if (inherits(fit, "error")) {
    return(list(
      status = "failed",
      reason = conditionMessage(fit),
      method = "Firth penalized partial likelihood",
      package = "coxphf",
      package_version = as.character(utils::packageVersion("coxphf")),
      penalty = FIRTH_PENALTY,
      trigger_reasons = information$trigger_reasons,
      warnings = as.list(unique(fit_warnings))
    ))
  }

  coefficient_names <- names(fit$coefficients)
  row_index <- if (!is.null(term)) match(term, coefficient_names) else NA_integer_
  if (is.na(row_index) && !is.null(term_pattern)) {
    matches <- grep(term_pattern, coefficient_names)
    if (length(matches) == 1) {
      row_index <- matches[[1]]
    }
  }
  if (is.na(row_index)) {
    return(list(
      status = "failed",
      reason = "Could not isolate the requested marker term in the Firth model.",
      method = "Firth penalized partial likelihood",
      package = "coxphf",
      package_version = as.character(utils::packageVersion("coxphf")),
      penalty = FIRTH_PENALTY,
      available_terms = as.list(coefficient_names),
      trigger_reasons = information$trigger_reasons,
      warnings = as.list(unique(fit_warnings))
    ))
  }

  coefficient <- unname(fit$coefficients[[row_index]])
  hazard_ratio <- exp(coefficient)
  hr_conf_low <- unname(fit$ci.lower[[row_index]])
  hr_conf_high <- unname(fit$ci.upper[[row_index]])
  p_value <- unname(fit$prob[[row_index]])
  if (!all(is.finite(c(
    coefficient,
    hazard_ratio,
    hr_conf_low,
    hr_conf_high,
    p_value
  )))) {
    return(list(
      status = "failed",
      reason = "The Firth model did not produce finite marker estimates.",
      method = "Firth penalized partial likelihood",
      package = "coxphf",
      package_version = as.character(utils::packageVersion("coxphf")),
      penalty = FIRTH_PENALTY,
      term = coefficient_names[[row_index]],
      trigger_reasons = information$trigger_reasons,
      warnings = as.list(unique(fit_warnings))
    ))
  }

  list(
    status = "completed",
    method = "Firth penalized partial likelihood",
    package = "coxphf",
    package_version = as.character(utils::packageVersion("coxphf")),
    confidence_interval_method = "profile penalized likelihood",
    p_value_method = "penalized likelihood ratio",
    ties = fit$method.ties,
    penalty = FIRTH_PENALTY,
    term = coefficient_names[[row_index]],
    label = effect_label,
    n_patients = nrow(data),
    n_events = sum(data$event, na.rm = TRUE),
    parameter_count = information$parameter_count,
    events_per_parameter = information$events_per_parameter,
    log_hr = coefficient,
    hazard_ratio = hazard_ratio,
    hr_conf_low = hr_conf_low,
    hr_conf_high = hr_conf_high,
    p_value = p_value,
    iterations = unname(fit$iter),
    trigger_reasons = information$trigger_reasons,
    warnings = as.list(unique(fit_warnings))
  )
}
