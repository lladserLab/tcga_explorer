COMPETING_RISK_ENDPOINTS <- c("DSS", "DFI", "PFI")
MIN_COMPETING_RISK_EVENTS <- 5L
MIN_COMPETING_EVENTS <- 1L

`%||cr%` <- function(left, right) {
  if (is.null(left) || length(left) == 0) right else left
}

competing_risk_endpoint_spec <- function(endpoint) {
  endpoint <- toupper(trimws(as.character(endpoint %||cr% "")))
  specs <- list(
    DSS = list(
      endpoint = "DSS",
      event_label = "death from the index cancer",
      competing_label = "death from another cause",
      status_column = "DSS_cr",
      time_column = "DSS.time.cr"
    ),
    DFI = list(
      endpoint = "DFI",
      event_label = "disease recurrence after a disease-free interval",
      competing_label = "death before documented recurrence",
      status_column = "DFI.cr",
      time_column = "DFI.time.cr"
    ),
    PFI = list(
      endpoint = "PFI",
      event_label = "progression or death with tumor",
      competing_label = "death without a preceding progression event",
      status_column = "PFI.cr",
      time_column = "PFI.time.cr"
    )
  )
  specs[[endpoint]]
}

competing_risk_model_skip <- function(
  model_id,
  label,
  reason,
  data = data.frame(),
  covariates = character(),
  covariate_encoding = list()
) {
  list(
    model = model_id,
    label = label,
    status = "skipped",
    reason = reason,
    covariates = as.list(covariates),
    covariate_encoding = covariate_encoding,
    n_patients = nrow(data),
    n_events_of_interest = if ("competing_risk_status" %in% names(data)) {
      sum(data$competing_risk_status == 1, na.rm = TRUE)
    } else {
      0L
    },
    n_competing_events = if ("competing_risk_status" %in% names(data)) {
      sum(data$competing_risk_status == 2, na.rm = TRUE)
    } else {
      0L
    }
  )
}

fine_gray_term_rows <- function(
  fit,
  marker_columns,
  marker,
  group_levels = character()
) {
  coefficients <- as.numeric(fit$coef)
  names(coefficients) <- names(fit$coef)
  variances <- as.numeric(diag(fit$var))
  standard_errors <- vapply(variances, function(variance) {
    if (is.finite(variance) && variance >= 0) sqrt(variance) else NA_real_
  }, numeric(1))
  critical_value <- stats::qnorm(0.975)
  lapply(seq_along(coefficients), function(index) {
    coefficient <- coefficients[[index]]
    standard_error <- standard_errors[[index]]
    term <- names(coefficients)[[index]]
    is_marker <- term %in% marker_columns
    comparison_level <- NULL
    reference_level <- NULL
    contrast <- NULL
    if (is_marker && identical(marker, "group")) {
      encoded_levels <- paste0("group", make.names(group_levels))
      matched_index <- match(term, encoded_levels)
      if (!is.na(matched_index)) {
        comparison_level <- group_levels[[matched_index]]
      }
      if (length(group_levels)) {
        reference_level <- group_levels[[1]]
      }
      if (!is.null(comparison_level) && !is.null(reference_level)) {
        contrast <- paste(comparison_level, "vs", reference_level)
      }
    } else if (is_marker) {
      contrast <- "+1 SD expression"
    }
    z_value <- if (
      is.finite(coefficient) &&
        is.finite(standard_error) &&
        standard_error > 0
    ) {
      coefficient / standard_error
    } else {
      NA_real_
    }
    confidence_limits <- if (
      is.finite(coefficient) &&
        is.finite(standard_error)
    ) {
      coefficient + c(-1, 1) * critical_value * standard_error
    } else {
      c(NA_real_, NA_real_)
    }
    list(
      term = term,
      marker_term = is_marker,
      contrast = contrast,
      comparison_level = comparison_level,
      reference_level = reference_level,
      log_subdistribution_hazard_ratio = unname(coefficient),
      standard_error = unname(standard_error),
      subdistribution_hazard_ratio = if (is.finite(coefficient)) {
        unname(exp(coefficient))
      } else {
        NA_real_
      },
      shr_conf_low = unname(exp(confidence_limits[[1]])),
      shr_conf_high = unname(exp(confidence_limits[[2]])),
      p_value = if (is.finite(z_value)) {
        unname(2 * stats::pnorm(abs(z_value), lower.tail = FALSE))
      } else {
        NA_real_
      }
    )
  })
}

fit_fine_gray_model <- function(
  data,
  model_id,
  label,
  marker,
  covariates = character(),
  external_covariates = character(),
  external_definitions = list(),
  group_levels = character()
) {
  external_record_names <- vapply(
    external_covariates,
    external_covariate_record_name,
    character(1)
  )
  required <- unique(c(
    "time_days",
    "competing_risk_status",
    marker,
    covariates,
    external_record_names
  ))
  missing <- setdiff(required, names(data))
  if (length(missing)) {
    return(competing_risk_model_skip(
      model_id,
      label,
      paste("Missing competing-risk model fields:", paste(missing, collapse = ", ")),
      data,
      covariates
    ))
  }

  data <- data[, required, drop = FALSE]
  data <- data[
    is.finite(data$time_days) &
      data$time_days > 0 &
      !is.na(data$competing_risk_status) &
      data$competing_risk_status %in% 0:2,
    ,
    drop = FALSE
  ]
  if (marker == "group") {
    data$group <- droplevels(factor(data$group, levels = group_levels))
  }
  prepared <- tryCatch(
    prepare_model_covariates(
      data,
      covariates,
      external_covariates,
      external_definitions
    ),
    error = function(error) error
  )
  if (inherits(prepared, "error")) {
    return(competing_risk_model_skip(
      model_id,
      label,
      conditionMessage(prepared),
      data,
      covariates
    ))
  }
  encoded_covariates <- prepared$covariates
  covariate_encoding <- prepared$metadata
  model_fields <- c(
    "time_days",
    "competing_risk_status",
    marker,
    encoded_covariates
  )
  data <- prepared$data[, model_fields, drop = FALSE]
  data <- data[complete.cases(data), , drop = FALSE]
  data <- droplevels(data)

  if (nrow(data) < 10) {
    return(competing_risk_model_skip(
      model_id,
      label,
      "Fewer than 10 complete patients after model-specific filtering.",
      data,
      encoded_covariates,
      covariate_encoding
    ))
  }
  n_events <- sum(data$competing_risk_status == 1)
  n_competing <- sum(data$competing_risk_status == 2)
  if (n_events < MIN_COMPETING_RISK_EVENTS) {
    return(competing_risk_model_skip(
      model_id,
      label,
      paste0(
        "Fewer than ",
        MIN_COMPETING_RISK_EVENTS,
        " events of interest after model-specific filtering."
      ),
      data,
      encoded_covariates,
      covariate_encoding
    ))
  }
  if (n_competing < MIN_COMPETING_EVENTS) {
    return(competing_risk_model_skip(
      model_id,
      label,
      "No competing deaths remained after model-specific filtering.",
      data,
      encoded_covariates,
      covariate_encoding
    ))
  }
  if (marker == "group" && length(levels(data$group)) < 2) {
    return(competing_risk_model_skip(
      model_id,
      label,
      "Fewer than two expression groups remained after filtering.",
      data,
      encoded_covariates,
      covariate_encoding
    ))
  }
  if (marker != "group" && !model_covariate_has_variation(data[[marker]])) {
    return(competing_risk_model_skip(
      model_id,
      label,
      "The continuous marker had fewer than two observed values.",
      data,
      encoded_covariates,
      covariate_encoding
    ))
  }
  for (covariate in encoded_covariates) {
    if (!model_covariate_has_variation(data[[covariate]])) {
      return(competing_risk_model_skip(
        model_id,
        label,
        paste0(
          "Clinical covariate ",
          covariate,
          " had fewer than two observed values after filtering."
        ),
        data,
        encoded_covariates,
        covariate_encoding
      ))
    }
  }

  formula <- stats::reformulate(c(marker, encoded_covariates))
  design <- stats::model.matrix(formula, data = data)
  design <- design[, colnames(design) != "(Intercept)", drop = FALSE]
  if (!ncol(design)) {
    return(competing_risk_model_skip(
      model_id,
      label,
      "The Fine-Gray design matrix contained no estimable terms.",
      data,
      encoded_covariates,
      covariate_encoding
    ))
  }
  if (qr(design)$rank < ncol(design)) {
    return(competing_risk_model_skip(
      model_id,
      label,
      "The Fine-Gray design matrix was rank deficient.",
      data,
      encoded_covariates,
      covariate_encoding
    ))
  }
  marker_columns <- if (marker == "group") {
    grep("^group", colnames(design), value = TRUE)
  } else {
    intersect(marker, colnames(design))
  }
  if (!length(marker_columns)) {
    return(competing_risk_model_skip(
      model_id,
      label,
      "The marker term could not be isolated in the Fine-Gray design matrix.",
      data,
      encoded_covariates,
      covariate_encoding
    ))
  }

  model_warnings <- character()
  censoring_group <- if (marker == "group") {
    as.character(data$group)
  } else {
    rep("all", nrow(data))
  }
  fit <- tryCatch(
    withCallingHandlers(
      cmprsk::crr(
        ftime = data$time_days,
        fstatus = data$competing_risk_status,
        cov1 = design,
        cengroup = censoring_group,
        failcode = 1,
        cencode = 0,
        maxiter = 50
      ),
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
      status = "failed",
      reason = conditionMessage(fit),
      covariates = as.list(encoded_covariates),
      covariate_encoding = covariate_encoding,
      n_patients = nrow(data),
      n_events_of_interest = n_events,
      n_competing_events = n_competing,
      warnings = as.list(unique(model_warnings))
    ))
  }
  if (!isTRUE(fit$converged)) {
    model_warnings <- c(
      model_warnings,
      "The Fine-Gray Newton iteration did not report convergence."
    )
  }
  terms <- fine_gray_term_rows(
    fit,
    marker_columns,
    marker,
    group_levels
  )
  marker_rows <- Filter(function(term) isTRUE(term$marker_term), terms)
  parameter_count <- ncol(design)
  events_per_parameter <- n_events / parameter_count
  if (events_per_parameter < 5) {
    model_warnings <- c(
      model_warnings,
      sprintf(
        "Only %.1f events of interest per fitted parameter; interpret as severe low-information evidence.",
        events_per_parameter
      )
    )
  } else if (events_per_parameter < 10) {
    model_warnings <- c(
      model_warnings,
      sprintf(
        "Only %.1f events of interest per fitted parameter; interpret as low-information evidence.",
        events_per_parameter
      )
    )
  }
  list(
    model = model_id,
    label = label,
    status = if (isTRUE(fit$converged)) "completed" else "failed",
    reason = if (isTRUE(fit$converged)) NULL else "Fine-Gray model did not converge.",
    method = "cmprsk::crr proportional subdistribution hazards",
    estimand = "subdistribution hazard ratio for the event-of-interest cumulative incidence",
    variance = "cmprsk weighted estimating-equation variance",
    censoring_distribution = if (marker == "group") {
      "estimated separately by expression group"
    } else {
      "estimated across the complete model population"
    },
    failcode = 1,
    cencode = 0,
    marker = marker,
    marker_reference = if (
      identical(marker, "group") && length(group_levels)
    ) {
      group_levels[[1]]
    } else {
      NULL
    },
    marker_effect_unit = if (identical(marker, "group")) {
      "group contrast against the first declared group"
    } else {
      "+1 within-analysis expression SD"
    },
    n_patients = nrow(data),
    n_events_of_interest = n_events,
    n_competing_events = n_competing,
    parameter_count = parameter_count,
    events_per_parameter = events_per_parameter,
    covariates = as.list(encoded_covariates),
    covariate_encoding = covariate_encoding,
    marker_terms = marker_rows,
    terms = terms,
    warnings = as.list(unique(model_warnings))
  )
}

step_estimate_at <- function(curve, time_days, n_at_risk) {
  critical_value <- stats::qnorm(0.975)
  indices <- which(as.numeric(curve$time) <= time_days)
  if (!length(indices)) {
    return(list(
      estimate = 0,
      standard_error = 0,
      confidence_level = 0.95,
      confidence_method = "pointwise normal interval from Aalen variance",
      conf_low = 0,
      conf_high = 0,
      n_at_risk = n_at_risk,
      support_threshold = 5L,
      supported = n_at_risk >= 5L
    ))
  }
  index <- max(indices)
  variance <- as.numeric(curve$var[[index]])
  standard_error <- if (is.finite(variance) && variance >= 0) {
    sqrt(variance)
  } else {
    NA_real_
  }
  estimate <- as.numeric(curve$est[[index]])
  list(
    estimate = estimate,
    standard_error = standard_error,
    confidence_level = 0.95,
    confidence_method = "pointwise normal interval from Aalen variance",
    conf_low = if (is.finite(standard_error)) {
      max(0, estimate - critical_value * standard_error)
    } else {
      NA_real_
    },
    conf_high = if (is.finite(standard_error)) {
      min(1, estimate + critical_value * standard_error)
    } else {
      NA_real_
    },
    n_at_risk = n_at_risk,
    support_threshold = 5L,
    supported = n_at_risk >= 5L
  )
}

fit_cumulative_incidence <- function(
  records,
  group_levels,
  spec,
  time_divisor,
  time_label,
  palette,
  plot_theme,
  output_png,
  output_svg,
  render_png,
  render_svg,
  plot_aspect
) {
  data <- records[
    is.finite(records$time_days) &
      records$time_days > 0 &
      !is.na(records$competing_risk_status) &
      records$competing_risk_status %in% 0:2 &
      !is.na(records$group),
    c("time_days", "competing_risk_status", "group"),
    drop = FALSE
  ]
  data$group <- droplevels(factor(data$group, levels = group_levels))
  if (nrow(data) < 10) {
    return(list(
      status = "skipped",
      reason = "Fewer than 10 complete grouped competing-risk records.",
      n_patients = nrow(data)
    ))
  }
  if (length(levels(data$group)) < 2) {
    return(list(
      status = "skipped",
      reason = "Fewer than two expression groups remained.",
      n_patients = nrow(data)
    ))
  }
  n_events <- sum(data$competing_risk_status == 1)
  n_competing <- sum(data$competing_risk_status == 2)
  if (n_events < MIN_COMPETING_RISK_EVENTS) {
    return(list(
      status = "skipped",
      reason = paste0(
        "Fewer than ",
        MIN_COMPETING_RISK_EVENTS,
        " events of interest remained."
      ),
      n_patients = nrow(data),
      n_events_of_interest = n_events,
      n_competing_events = n_competing
    ))
  }
  if (n_competing < MIN_COMPETING_EVENTS) {
    return(list(
      status = "skipped",
      reason = "No competing deaths remained.",
      n_patients = nrow(data),
      n_events_of_interest = n_events,
      n_competing_events = n_competing
    ))
  }

  fit <- tryCatch(
    cmprsk::cuminc(
      ftime = data$time_days,
      fstatus = data$competing_risk_status,
      group = data$group,
      rho = 0,
      cencode = 0
    ),
    error = function(error) error
  )
  if (inherits(fit, "error")) {
    return(list(
      status = "failed",
      reason = conditionMessage(fit),
      n_patients = nrow(data),
      n_events_of_interest = n_events,
      n_competing_events = n_competing
    ))
  }

  curve_names <- paste(levels(data$group), "1")
  curve_names <- curve_names[curve_names %in% names(fit)]
  curve_payload <- lapply(curve_names, function(name) {
    curve <- fit[[name]]
    group <- sub(" 1$", "", name)
    variance <- as.numeric(curve$var)
    standard_error <- vapply(variance, function(value) {
      if (is.finite(value) && value >= 0) sqrt(value) else NA_real_
    }, numeric(1))
    estimate <- as.numeric(curve$est)
    critical_value <- stats::qnorm(0.975)
    list(
      group = group,
      cause_code = 1,
      cause = spec$event_label,
      time_days = as.list(as.numeric(curve$time)),
      estimate = as.list(estimate),
      variance = as.list(variance),
      conf_low = as.list(pmax(0, estimate - critical_value * standard_error)),
      conf_high = as.list(pmin(1, estimate + critical_value * standard_error)),
      confidence_level = 0.95,
      confidence_method = "pointwise normal interval from Aalen variance"
    )
  })

  horizons <- c(365.25, 3 * 365.25, 5 * 365.25)
  horizon_payload <- lapply(horizons, function(horizon) {
    by_group <- list()
    for (name in curve_names) {
      group <- sub(" 1$", "", name)
      group_data <- data[data$group == group, , drop = FALSE]
      n_at_risk <- sum(group_data$time_days >= horizon)
      by_group[[group]] <- step_estimate_at(
        fit[[name]],
        horizon,
        n_at_risk
      )
    }
    at_risk_counts <- vapply(
      by_group,
      function(group_result) group_result$n_at_risk,
      integer(1)
    )
    list(
      time_days = horizon,
      time_years = horizon / 365.25,
      minimum_at_risk = min(at_risk_counts),
      support_threshold = 5L,
      supported_all_groups = all(at_risk_counts >= 5L),
      groups = by_group
    )
  })

  gray_test <- list(status = "not_evaluable")
  tests <- fit$Tests
  if (!is.null(tests) && nrow(as.data.frame(tests)) > 0) {
    tests <- as.data.frame(tests)
    row_index <- match("1", rownames(tests))
    if (is.na(row_index)) {
      row_index <- 1L
    }
    gray_test <- list(
      status = "completed",
      method = "Gray K-sample test (rho=0)",
      statistic = as.numeric(tests[row_index, "stat"]),
      degrees_of_freedom = as.numeric(tests[row_index, "df"]),
      p_value = as.numeric(tests[row_index, "pv"])
    )
  }

  plot_rows <- lapply(curve_names, function(name) {
    curve <- fit[[name]]
    data.frame(
      group = sub(" 1$", "", name),
      time = as.numeric(curve$time) / time_divisor,
      estimate = as.numeric(curve$est),
      stringsAsFactors = FALSE
    )
  })
  if (length(plot_rows)) {
    plot_data <- do.call(rbind, plot_rows)
    plot_data$group <- factor(plot_data$group, levels = levels(data$group))
    color_values <- stats::setNames(
      palette[seq_along(levels(data$group))],
      levels(data$group)
    )
    subtitle_text <- paste(
      "Event of interest:",
      spec$event_label,
      "| competing event:",
      spec$competing_label
    )
    subtitle_text <- paste(
      strwrap(
        subtitle_text,
        width = if (identical(plot_aspect, "square")) 68L else 94L
      ),
      collapse = "\n"
    )
    plot <- ggplot2::ggplot(
      plot_data,
      ggplot2::aes(x = time, y = estimate, color = group)
    ) +
      ggplot2::geom_step(linewidth = 1.05, direction = "hv") +
      ggplot2::scale_color_manual(values = color_values, drop = FALSE) +
      ggplot2::scale_y_continuous(
        limits = c(0, 1),
        labels = scales::label_percent(accuracy = 1),
        expand = ggplot2::expansion(mult = c(0, 0.03))
      ) +
      ggplot2::labs(
        title = paste("Cumulative incidence:", spec$endpoint),
        subtitle = subtitle_text,
        x = time_label,
        y = "Cumulative incidence",
        color = "Expression group"
      ) +
      plot_theme +
      ggplot2::theme(
        plot.title = ggplot2::element_text(face = "bold"),
        plot.subtitle = ggplot2::element_text(color = "#586864"),
        legend.position = "bottom"
      )
    width <- if (identical(plot_aspect, "square")) 7.2 else 8.8
    height <- if (identical(plot_aspect, "square")) 7.2 else 6.2
    if (isTRUE(render_png) && nzchar(output_png %||cr% "")) {
      ggplot2::ggsave(
        output_png,
        plot = plot,
        width = width,
        height = height,
        units = "in",
        dpi = 220,
        bg = "white"
      )
    }
    if (isTRUE(render_svg) && nzchar(output_svg %||cr% "")) {
      ggplot2::ggsave(
        output_svg,
        plot = plot,
        width = width,
        height = height,
        units = "in",
        bg = "white"
      )
    }
  }

  group_summary <- lapply(levels(data$group), function(group) {
    selected <- data[data$group == group, , drop = FALSE]
    list(
      group = group,
      patients = nrow(selected),
      events_of_interest = sum(selected$competing_risk_status == 1),
      competing_events = sum(selected$competing_risk_status == 2),
      censored = sum(selected$competing_risk_status == 0)
    )
  })
  names(group_summary) <- levels(data$group)

  list(
    status = "completed",
    method = "cmprsk::cuminc nonparametric cumulative incidence",
    variance = "Aalen asymptotic variance",
    n_patients = nrow(data),
    n_events_of_interest = n_events,
    n_competing_events = n_competing,
    n_censored = sum(data$competing_risk_status == 0),
    confidence_intervals = list(
      level = 0.95,
      method = "pointwise normal interval from Aalen variance",
      truncated_to_probability_range = TRUE
    ),
    horizon_support = list(
      at_risk_definition = "observed endpoint time greater than or equal to the horizon",
      minimum_per_group = 5L
    ),
    group_summary = group_summary,
    gray_test = gray_test,
    horizons = horizon_payload,
    curves = curve_payload
  )
}

fit_competing_risks_analysis <- function(
  records,
  continuous_records,
  endpoint,
  group_levels,
  requested_adjustment_covariates,
  requested_external_adjustment_covariates,
  external_covariate_definitions,
  time_divisor,
  time_label,
  palette,
  plot_theme,
  output_png,
  output_svg,
  render_png,
  render_svg,
  plot_aspect
) {
  spec <- competing_risk_endpoint_spec(endpoint)
  if (is.null(spec)) {
    return(list(
      applicable = FALSE,
      status = "not_applicable",
      reason = "The selected endpoint has no linked competing-event status."
    ))
  }
  coding <- list(
    source = "TCGA-CDR Supplemental Table S1, ExtraEndpoints",
    source_status_column = spec$status_column,
    source_time_column = spec$time_column,
    status_field = "competing_risk_status",
    status_codes = list(
      `0` = "censored",
      `1` = spec$event_label,
      `2` = spec$competing_label
    ),
    cause_specific_contract = paste(
      "Kaplan-Meier and Cox outputs use event == 1 and censor status 2 at",
      "the recorded competing-event time."
    ),
    cumulative_incidence_contract = paste(
      "Cumulative incidence retains status 2 as a competing event and compares",
      "event-of-interest subdistributions with Gray's test."
    ),
    fine_gray_contract = paste(
      "Fine-Gray models estimate proportional subdistribution hazard ratios",
      "for status 1 while retaining status 2 in the risk-set construction."
    )
  )
  if (!requireNamespace("cmprsk", quietly = TRUE)) {
    return(list(
      applicable = TRUE,
      status = "skipped",
      reason = "R package cmprsk is not installed.",
      coding = coding
    ))
  }

  grouped <- records[
    is.finite(records$time_days) &
      records$time_days > 0 &
      !is.na(records$competing_risk_status) &
      records$competing_risk_status %in% 0:2,
    ,
    drop = FALSE
  ]
  continuous <- continuous_records[
    is.finite(continuous_records$time_days) &
      continuous_records$time_days > 0 &
      !is.na(continuous_records$competing_risk_status) &
      continuous_records$competing_risk_status %in% 0:2 &
      is.finite(continuous_records$expression_value),
    ,
    drop = FALSE
  ]
  if (nrow(continuous)) {
    expression_center <- mean(continuous$expression_value)
    expression_sd <- stats::sd(continuous$expression_value)
    continuous$expression_z <- if (
      is.finite(expression_sd) && expression_sd > 0
    ) {
      (continuous$expression_value - expression_center) / expression_sd
    } else {
      NA_real_
    }
  } else {
    expression_center <- NA_real_
    expression_sd <- NA_real_
    continuous$expression_z <- numeric()
  }

  cumulative_incidence <- fit_cumulative_incidence(
    grouped,
    group_levels,
    spec,
    time_divisor,
    time_label,
    palette,
    plot_theme,
    output_png,
    output_svg,
    render_png,
    render_svg,
    plot_aspect
  )

  grouped_models <- list(
    fit_fine_gray_model(
      grouped,
      "fine_gray_grouped_univariable",
      "Grouped Fine-Gray",
      "group",
      group_levels = group_levels
    ),
    fit_fine_gray_model(
      grouped,
      "fine_gray_grouped_stage_adjusted",
      "Grouped Fine-Gray adjusted for ordinal stage",
      "group",
      c("stage"),
      group_levels = group_levels
    ),
    fit_fine_gray_model(
      grouped,
      "fine_gray_grouped_grade_adjusted",
      "Grouped Fine-Gray adjusted for ordinal grade",
      "group",
      c("grade"),
      group_levels = group_levels
    ),
    fit_fine_gray_model(
      grouped,
      "fine_gray_grouped_stage_grade_adjusted",
      "Grouped Fine-Gray adjusted for ordinal stage and grade",
      "group",
      c("stage", "grade"),
      group_levels = group_levels
    )
  )
  continuous_models <- list(
    fit_fine_gray_model(
      continuous,
      "fine_gray_continuous_univariable",
      "Continuous Fine-Gray per +1 SD expression",
      "expression_z"
    ),
    fit_fine_gray_model(
      continuous,
      "fine_gray_continuous_stage_adjusted",
      "Continuous Fine-Gray adjusted for ordinal stage",
      "expression_z",
      c("stage")
    ),
    fit_fine_gray_model(
      continuous,
      "fine_gray_continuous_grade_adjusted",
      "Continuous Fine-Gray adjusted for ordinal grade",
      "expression_z",
      c("grade")
    ),
    fit_fine_gray_model(
      continuous,
      "fine_gray_continuous_stage_grade_adjusted",
      "Continuous Fine-Gray adjusted for ordinal stage and grade",
      "expression_z",
      c("stage", "grade")
    )
  )
  if (
    length(requested_adjustment_covariates) ||
      length(requested_external_adjustment_covariates)
  ) {
    adjustment_label <- clinical_adjustment_label(
      requested_adjustment_covariates,
      requested_external_adjustment_covariates,
      external_covariate_definitions
    )
    grouped_models <- c(
      grouped_models,
      list(fit_fine_gray_model(
        grouped,
        "fine_gray_grouped_user_adjusted",
        paste("Grouped Fine-Gray user-adjusted for", adjustment_label),
        "group",
        requested_adjustment_covariates,
        requested_external_adjustment_covariates,
        external_covariate_definitions,
        group_levels
      ))
    )
    continuous_models <- c(
      continuous_models,
      list(fit_fine_gray_model(
        continuous,
        "fine_gray_continuous_user_adjusted",
        paste("Continuous Fine-Gray user-adjusted for", adjustment_label),
        "expression_z",
        requested_adjustment_covariates,
        requested_external_adjustment_covariates,
        external_covariate_definitions
      ))
    )
  }
  completed_models <- Filter(
    function(model) identical(model$status, "completed"),
    c(grouped_models, continuous_models)
  )

  list(
    applicable = TRUE,
    status = if (
      identical(cumulative_incidence$status, "completed") ||
        length(completed_models)
    ) {
      "completed"
    } else {
      "skipped"
    },
    reason = if (
      identical(cumulative_incidence$status, "completed") ||
        length(completed_models)
    ) {
      NULL
    } else {
      "Neither cumulative incidence nor a Fine-Gray model was estimable."
    },
    endpoint = spec$endpoint,
    coding = coding,
    population_note = paste(
      "Grouped outputs use the post-cutpoint cohort; continuous outputs use the",
      "unstratified expression-complete eligible cohort."
    ),
    continuous_predictor = list(
      scale = "within-analysis z-score",
      center = expression_center,
      standard_deviation = expression_sd,
      effect_unit = "subdistribution hazard ratio per +1 SD expression"
    ),
    cumulative_incidence = cumulative_incidence,
    grouped_fine_gray_models = grouped_models,
    continuous_fine_gray_models = continuous_models
  )
}
