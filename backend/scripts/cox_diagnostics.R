MODEL_EPV_CAUTION_THRESHOLD <- 10
MODEL_EPV_SEVERE_THRESHOLD <- 5
FIRTH_PENALTY <- 0.5
TIME_VARYING_PH_ALPHA <- 0.05
TIME_VARYING_SPLIT_YEARS <- 2
TIME_VARYING_SPLIT_DAYS <- TIME_VARYING_SPLIT_YEARS * 365.25
TIME_VARYING_MIN_EVENTS_PER_PERIOD <- 5L
TIME_VARYING_MIN_AT_RISK_AT_SPLIT <- 10L

time_varying_effect_contract <- function(ph_p_value) {
  list(
    method = "Prespecified two-period Cox marker effect",
    estimand = paste(
      "Marker hazard ratio before and after a fixed two-year follow-up split,",
      "plus the late-to-early hazard-ratio ratio."
    ),
    trigger = "Marker-specific cox.zph p < 0.05",
    trigger_alpha = TIME_VARYING_PH_ALPHA,
    trigger_ph_p_value = if (
      length(ph_p_value) &&
        is.finite(suppressWarnings(as.numeric(ph_p_value[[1]])))
    ) {
      unname(as.numeric(ph_p_value[[1]]))
    } else {
      NA_real_
    },
    split_rule = paste(
      "The follow-up split is fixed at 2 years (730.5 days) for every analysis",
      "and is not selected from marker values, event times or effect estimates."
    ),
    split_years = TIME_VARYING_SPLIT_YEARS,
    split_days = TIME_VARYING_SPLIT_DAYS,
    min_events_per_period = TIME_VARYING_MIN_EVENTS_PER_PERIOD,
    min_at_risk_at_split = TIME_VARYING_MIN_AT_RISK_AT_SPLIT,
    ties = "efron",
    variance = "participant-clustered robust sandwich"
  )
}

time_varying_period_effect <- function(
  label,
  start_days,
  end_days,
  n_at_risk_start,
  n_events,
  log_hr,
  standard_error
) {
  critical_value <- stats::qnorm(0.975)
  list(
    label = label,
    start_days = start_days,
    end_days = end_days,
    n_at_risk_start = as.integer(n_at_risk_start),
    n_events = as.integer(n_events),
    log_hr = unname(log_hr),
    standard_error = unname(standard_error),
    hazard_ratio = unname(exp(log_hr)),
    hr_conf_low = unname(exp(log_hr - critical_value * standard_error)),
    hr_conf_high = unname(exp(log_hr + critical_value * standard_error)),
    p_value = unname(
      2 * stats::pnorm(abs(log_hr / standard_error), lower.tail = FALSE)
    )
  )
}

fit_prespecified_time_varying_effect <- function(
  data,
  formula_terms,
  marker_formula_term,
  marker_coefficient,
  effect_label,
  ph_p_value
) {
  result <- time_varying_effect_contract(ph_p_value)
  result$effect_label <- effect_label

  ph_value <- suppressWarnings(as.numeric(ph_p_value))
  if (!length(ph_value) || !is.finite(ph_value[[1]])) {
    result$status <- "not_evaluable"
    result$reason <- paste(
      "The marker-specific proportional-hazards diagnostic was not evaluable,",
      "so the prespecified temporal follow-up model was not triggered."
    )
    return(result)
  }
  if (ph_value[[1]] >= TIME_VARYING_PH_ALPHA) {
    result$status <- "not_triggered"
    result$reason <- paste(
      "The marker-specific proportional-hazards diagnostic was not below the",
      "prespecified 0.05 trigger."
    )
    return(result)
  }

  required_fields <- c("time_days", "event")
  if (!all(required_fields %in% names(data))) {
    result$status <- "failed"
    result$reason <- "The temporal diagnostic did not receive time_days and event fields."
    return(result)
  }
  data <- data[
    is.finite(data$time_days) &
      data$time_days > 0 &
      !is.na(data$event) &
      data$event %in% c(0, 1),
    ,
    drop = FALSE
  ]
  data$split_id <- seq_len(nrow(data))
  early_events <- sum(
    data$event == 1 & data$time_days <= TIME_VARYING_SPLIT_DAYS,
    na.rm = TRUE
  )
  late_events <- sum(
    data$event == 1 & data$time_days > TIME_VARYING_SPLIT_DAYS,
    na.rm = TRUE
  )
  at_risk_at_split <- sum(
    data$time_days > TIME_VARYING_SPLIT_DAYS,
    na.rm = TRUE
  )
  result$n_patients <- nrow(data)
  result$n_events <- sum(data$event, na.rm = TRUE)
  result$support <- list(
    early_events = as.integer(early_events),
    late_events = as.integer(late_events),
    at_risk_at_split = as.integer(at_risk_at_split)
  )

  support_reasons <- character()
  if (early_events < TIME_VARYING_MIN_EVENTS_PER_PERIOD) {
    support_reasons <- c(
      support_reasons,
      sprintf(
        "The early period had %d events; at least %d are required.",
        early_events,
        TIME_VARYING_MIN_EVENTS_PER_PERIOD
      )
    )
  }
  if (late_events < TIME_VARYING_MIN_EVENTS_PER_PERIOD) {
    support_reasons <- c(
      support_reasons,
      sprintf(
        "The late period had %d events; at least %d are required.",
        late_events,
        TIME_VARYING_MIN_EVENTS_PER_PERIOD
      )
    )
  }
  if (at_risk_at_split < TIME_VARYING_MIN_AT_RISK_AT_SPLIT) {
    support_reasons <- c(
      support_reasons,
      sprintf(
        "Only %d patients entered the late period; at least %d are required.",
        at_risk_at_split,
        TIME_VARYING_MIN_AT_RISK_AT_SPLIT
      )
    )
  }
  if (length(support_reasons)) {
    result$status <- "skipped"
    result$reason <- paste(support_reasons, collapse = " ")
    return(result)
  }

  early_data <- data
  early_data$tstart <- 0
  early_data$tstop <- pmin(
    early_data$time_days,
    TIME_VARYING_SPLIT_DAYS
  )
  early_data$interval_event <- as.integer(
    early_data$event == 1 &
      early_data$time_days <= TIME_VARYING_SPLIT_DAYS
  )
  early_data$late_period <- 0
  early_data <- early_data[
    early_data$tstop > early_data$tstart,
    ,
    drop = FALSE
  ]

  late_data <- data[data$time_days > TIME_VARYING_SPLIT_DAYS, , drop = FALSE]
  late_data$tstart <- TIME_VARYING_SPLIT_DAYS
  late_data$tstop <- late_data$time_days
  late_data$interval_event <- late_data$event
  late_data$late_period <- 1
  split_data <- rbind(early_data, late_data)

  time_interaction_term <- paste(marker_formula_term, "late_period", sep = ":")
  time_formula <- stats::as.formula(
    paste(
      "survival::Surv(tstart, tstop, interval_event) ~",
      paste(
        unique(c(
          formula_terms,
          time_interaction_term,
          "cluster(split_id)"
        )),
        collapse = " + "
      )
    )
  )
  fit_warnings <- character()
  fit <- tryCatch(
    withCallingHandlers(
      survival::coxph(
        time_formula,
        data = split_data,
        ties = "efron",
        x = TRUE,
        robust = TRUE
      ),
      warning = function(warning) {
        fit_warnings <<- c(fit_warnings, conditionMessage(warning))
        invokeRestart("muffleWarning")
      }
    ),
    error = function(error) error
  )
  if (inherits(fit, "error")) {
    result$status <- "failed"
    result$reason <- conditionMessage(fit)
    result$warnings <- as.list(unique(fit_warnings))
    return(result)
  }

  coefficients <- stats::coef(fit)
  coefficient_names <- names(coefficients)
  early_index <- match(marker_coefficient, coefficient_names)
  target_parts <- sort(c(
    strsplit(marker_coefficient, ":", fixed = TRUE)[[1]],
    "late_period"
  ))
  time_indexes <- which(vapply(
    coefficient_names,
    function(coefficient_name) {
      identical(
        sort(strsplit(coefficient_name, ":", fixed = TRUE)[[1]]),
        target_parts
      )
    },
    logical(1)
  ))
  if (is.na(early_index) || length(time_indexes) != 1) {
    result$status <- "failed"
    result$reason <- paste(
      "The temporal Cox model could not isolate the marker and marker-by-period",
      "coefficients."
    )
    result$coefficient_names <- as.list(coefficient_names)
    result$warnings <- as.list(unique(fit_warnings))
    return(result)
  }

  time_index <- time_indexes[[1]]
  variance <- stats::vcov(fit)
  early_log_hr <- unname(coefficients[[early_index]])
  change_log_hr <- unname(coefficients[[time_index]])
  early_variance <- unname(variance[early_index, early_index])
  change_variance <- unname(variance[time_index, time_index])
  covariance <- unname(variance[early_index, time_index])
  late_log_hr <- early_log_hr + change_log_hr
  late_variance <- early_variance + change_variance + (2 * covariance)
  numeric_values <- c(
    early_log_hr,
    change_log_hr,
    early_variance,
    change_variance,
    late_log_hr,
    late_variance
  )
  if (!all(is.finite(numeric_values)) ||
      early_variance <= 0 ||
      change_variance <= 0 ||
      late_variance <= 0) {
    result$status <- "failed"
    result$reason <- "The temporal Cox model returned non-finite effect variances."
    result$warnings <- as.list(unique(fit_warnings))
    return(result)
  }

  early_standard_error <- sqrt(early_variance)
  late_standard_error <- sqrt(late_variance)
  change_standard_error <- sqrt(change_variance)
  critical_value <- stats::qnorm(0.975)
  result$status <- "completed"
  result$formula <- paste(deparse(time_formula), collapse = "")
  result$parameter_count <- length(coefficients)
  result$events_per_parameter <- unname(
    sum(data$event, na.rm = TRUE) / length(coefficients)
  )
  result$periods <- list(
    early = time_varying_period_effect(
      "0 to 2 years",
      0,
      TIME_VARYING_SPLIT_DAYS,
      nrow(data),
      early_events,
      early_log_hr,
      early_standard_error
    ),
    late = time_varying_period_effect(
      "After 2 years",
      TIME_VARYING_SPLIT_DAYS,
      NULL,
      at_risk_at_split,
      late_events,
      late_log_hr,
      late_standard_error
    )
  )
  result$change <- list(
    label = "Late HR / early HR",
    log_hr_difference = change_log_hr,
    standard_error = change_standard_error,
    hazard_ratio_ratio = unname(exp(change_log_hr)),
    hr_ratio_conf_low = unname(
      exp(change_log_hr - critical_value * change_standard_error)
    ),
    hr_ratio_conf_high = unname(
      exp(change_log_hr + critical_value * change_standard_error)
    ),
    p_value = unname(
      2 * stats::pnorm(
        abs(change_log_hr / change_standard_error),
        lower.tail = FALSE
      )
    )
  )
  result$warnings <- as.list(unique(fit_warnings))
  result
}

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
