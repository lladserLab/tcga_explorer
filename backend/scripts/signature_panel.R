#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(jsonlite)
  library(survival)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L) {
  stop("Usage: signature_panel.R input.json")
}

# R 4.4 may encode spaces in its --file argument as ~+~ on macOS.
resolve_script_path <- function(argument) {
  candidate <- sub("^--file=", "", argument)
  if (!file.exists(candidate)) candidate <- gsub("~+~", " ", candidate, fixed = TRUE)
  normalizePath(candidate, mustWork = TRUE)
}

script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_path <- resolve_script_path(script_arg[[1]])
script_dir <- dirname(script_path)
source(file.path(script_dir, "clinical_covariates.R"))
source(file.path(script_dir, "cox_diagnostics.R"))

`%||%` <- function(left, right) {
  if (is.null(left) || length(left) == 0L) right else left
}

plot_font_face <- function(bold, italic) {
  if (isTRUE(bold) && isTRUE(italic)) {
    return("bold.italic")
  }
  if (isTRUE(bold)) {
    return("bold")
  }
  if (isTRUE(italic)) {
    return("italic")
  }
  "plain"
}

MIN_PANEL_PATIENTS <- 10L
MIN_PANEL_EVENTS <- 5L
MULTIPLICITY_METHODS <- c("BH", "bonferroni")

payload <- fromJSON(args[[1]], simplifyVector = FALSE)
records <- fromJSON(
  toJSON(payload$records, auto_unbox = TRUE, null = "null", digits = NA),
  simplifyDataFrame = TRUE
)
panel <- payload$signatures %||% list()
score_columns <- vapply(
  seq_along(panel),
  function(index) paste0("signature_", index),
  character(1)
)
signature_names <- vapply(
  panel,
  function(item) as.character(item$name %||% "Signature"),
  character(1)
)
names(signature_names) <- score_columns
requested_adjustment_covariates <- normalize_requested_covariates(
  payload$adjustment_covariates %||% list()
)
external_covariate_definitions <- payload$external_covariates$definitions %||%
  list()
requested_external_adjustment_covariates <-
  normalize_requested_external_covariates(
    payload$external_adjustment_covariates %||% list(),
    external_covariate_definitions
  )
adjustment_requested <- length(requested_adjustment_covariates) > 0L ||
  length(requested_external_adjustment_covariates) > 0L

required_fields <- c(
  "patient_id",
  "sample_barcode",
  "time_days",
  "event",
  score_columns
)
missing_fields <- setdiff(required_fields, names(records))
if (length(missing_fields)) {
  stop(
    "Signature-panel records are missing fields: ",
    paste(missing_fields, collapse = ", ")
  )
}
records$time_days <- suppressWarnings(as.numeric(records$time_days))
records$event <- suppressWarnings(as.integer(records$event))
for (column in score_columns) {
  records[[column]] <- suppressWarnings(as.numeric(records[[column]]))
}
records <- records[
  is.finite(records$time_days) &
    records$time_days > 0 &
    !is.na(records$event) &
    records$event %in% c(0L, 1L) &
    Reduce(`&`, lapply(score_columns, function(column) {
      is.finite(records[[column]])
    })),
  ,
  drop = FALSE
]
if (nrow(records) < MIN_PANEL_PATIENTS) {
  stop("The signature panel requires at least 10 complete patients.")
}
if (sum(records$event, na.rm = TRUE) < MIN_PANEL_EVENTS) {
  stop("The signature panel requires at least 5 endpoint events.")
}

model_skip <- function(
  model_id,
  label,
  family,
  marker_columns,
  reason,
  data = data.frame(),
  covariates = character(),
  covariate_encoding = list(),
  status = "skipped"
) {
  list(
    model = model_id,
    label = label,
    family = family,
    status = status,
    reason = reason,
    marker_columns = as.list(marker_columns),
    covariates = as.list(covariates),
    covariate_encoding = covariate_encoding,
    n_patients = nrow(data),
    n_events = if ("event" %in% names(data)) {
      sum(data$event, na.rm = TRUE)
    } else {
      0L
    },
    marker_terms = list(),
    warnings = list()
  )
}

cox_term <- function(model_summary, term, label) {
  coefficient_names <- rownames(model_summary$coefficients)
  index <- match(term, coefficient_names)
  if (is.na(index)) {
    return(NULL)
  }
  coefficient <- unname(model_summary$coefficients[index, "coef"])
  standard_error <- unname(model_summary$coefficients[index, "se(coef)"])
  hazard_ratio <- unname(model_summary$conf.int[index, "exp(coef)"])
  hr_conf_low <- unname(model_summary$conf.int[index, "lower .95"])
  hr_conf_high <- unname(model_summary$conf.int[index, "upper .95"])
  p_value <- unname(model_summary$coefficients[index, "Pr(>|z|)"])
  list(
    term = term,
    signature = label,
    contrast = "+1 within-panel score SD",
    log_hr = coefficient,
    standard_error = standard_error,
    hazard_ratio = hazard_ratio,
    hr_conf_low = hr_conf_low,
    hr_conf_high = hr_conf_high,
    p_value = p_value
  )
}

fit_panel_cox <- function(
  model_id,
  label,
  family,
  marker_columns,
  covariates = character(),
  external_covariates = character()
) {
  external_record_names <- vapply(
    external_covariates,
    external_covariate_record_name,
    character(1)
  )
  fields <- unique(c(
    "time_days",
    "event",
    marker_columns,
    covariates,
    external_record_names
  ))
  missing <- setdiff(fields, names(records))
  if (length(missing)) {
    return(model_skip(
      model_id,
      label,
      family,
      marker_columns,
      paste("Missing model fields:", paste(missing, collapse = ", "))
    ))
  }
  data <- records[, fields, drop = FALSE]
  prepared <- tryCatch(
    prepare_model_covariates(
      data,
      covariates,
      external_covariates,
      external_covariate_definitions
    ),
    error = function(error) error
  )
  if (inherits(prepared, "error")) {
    return(model_skip(
      model_id,
      label,
      family,
      marker_columns,
      conditionMessage(prepared),
      data
    ))
  }
  encoded_covariates <- prepared$covariates
  covariate_encoding <- prepared$metadata
  data <- prepared$data[
    ,
    c("time_days", "event", marker_columns, encoded_covariates),
    drop = FALSE
  ]
  data <- droplevels(data[complete.cases(data), , drop = FALSE])
  if (nrow(data) < MIN_PANEL_PATIENTS) {
    return(model_skip(
      model_id,
      label,
      family,
      marker_columns,
      "Fewer than 10 complete patients after model-specific filtering.",
      data,
      encoded_covariates,
      covariate_encoding
    ))
  }
  n_events <- sum(data$event, na.rm = TRUE)
  if (n_events < MIN_PANEL_EVENTS) {
    return(model_skip(
      model_id,
      label,
      family,
      marker_columns,
      "Fewer than 5 events after model-specific filtering.",
      data,
      encoded_covariates,
      covariate_encoding
    ))
  }
  for (column in c(marker_columns, encoded_covariates)) {
    if (!model_covariate_has_variation(data[[column]])) {
      return(model_skip(
        model_id,
        label,
        family,
        marker_columns,
        paste0(column, " has fewer than two observed values."),
        data,
        encoded_covariates,
        covariate_encoding
      ))
    }
  }

  formula_terms <- c(marker_columns, encoded_covariates)
  formula <- stats::as.formula(
    paste(
      "survival::Surv(time_days, event) ~",
      paste(formula_terms, collapse = " + ")
    )
  )
  parameter_count <- cox_parameter_count(formula, data)
  fit_warnings <- character()
  fit <- tryCatch(
    withCallingHandlers(
      survival::coxph(
        formula,
        data = data,
        ties = "efron",
        x = TRUE
      ),
      warning = function(warning) {
        fit_warnings <<- c(fit_warnings, conditionMessage(warning))
        invokeRestart("muffleWarning")
      }
    ),
    error = function(error) error
  )
  if (inherits(fit, "error")) {
    information <- cox_information_diagnostics(
      n_events,
      parameter_count,
      warnings = c(fit_warnings, conditionMessage(fit)),
      standard_fit_failed = TRUE
    )
    return(list(
      model = model_id,
      label = label,
      family = family,
      status = "failed",
      reason = conditionMessage(fit),
      marker_columns = as.list(marker_columns),
      covariates = as.list(encoded_covariates),
      covariate_encoding = covariate_encoding,
      n_patients = nrow(data),
      n_events = n_events,
      information_diagnostics = information,
      marker_terms = list(),
      warnings = as.list(unique(fit_warnings))
    ))
  }

  model_summary <- summary(fit)
  terms <- lapply(marker_columns, function(column) {
    cox_term(model_summary, column, signature_names[[column]])
  })
  if (any(vapply(terms, is.null, logical(1)))) {
    return(model_skip(
      model_id,
      label,
      family,
      marker_columns,
      "The fitted model did not return every requested signature term.",
      data,
      encoded_covariates,
      covariate_encoding,
      status = "failed"
    ))
  }
  finite_terms <- vapply(
    terms,
    function(term) all(is.finite(c(
      term$hazard_ratio,
      term$hr_conf_low,
      term$hr_conf_high,
      term$p_value
    ))),
    logical(1)
  )
  if (!all(finite_terms)) {
    return(model_skip(
      model_id,
      label,
      family,
      marker_columns,
      "The fitted model returned a non-finite signature estimate.",
      data,
      encoded_covariates,
      covariate_encoding,
      status = "failed"
    ))
  }

  extremity <- vapply(
    terms,
    function(term) {
      values <- c(
        term$hazard_ratio,
        term$hr_conf_low,
        term$hr_conf_high
      )
      max(abs(log(values)), na.rm = TRUE)
    },
    numeric(1)
  )
  representative <- terms[[which.max(extremity)]]
  information <- cox_information_diagnostics(
    n_events,
    parameter_count,
    warnings = fit_warnings,
    hazard_ratio = representative$hazard_ratio,
    hr_conf_low = representative$hr_conf_low,
    hr_conf_high = representative$hr_conf_high
  )
  information_warning <- cox_information_warning(information)
  model_warnings <- unique(c(
    fit_warnings,
    if (is.null(information_warning)) character() else information_warning
  ))
  ph_test <- tryCatch(
    survival::cox.zph(fit),
    error = function(error) error
  )
  global_ph_p <- NA_real_
  ph_by_term <- setNames(rep(NA_real_, length(marker_columns)), marker_columns)
  if (inherits(ph_test, "error")) {
    model_warnings <- c(
      model_warnings,
      paste("cox.zph failed:", conditionMessage(ph_test))
    )
  } else if (!is.null(ph_test$table) &&
      "p" %in% colnames(ph_test$table)) {
    for (column in marker_columns) {
      if (column %in% rownames(ph_test$table)) {
        ph_by_term[[column]] <- unname(ph_test$table[column, "p"])
      }
    }
    if ("GLOBAL" %in% rownames(ph_test$table)) {
      global_ph_p <- unname(ph_test$table["GLOBAL", "p"])
    }
    if (is.finite(global_ph_p) && global_ph_p < 0.05) {
      model_warnings <- c(
        model_warnings,
        "Global proportional-hazards test p < 0.05."
      )
    }
  }

  terms <- lapply(seq_along(terms), function(index) {
    term <- terms[[index]]
    column <- marker_columns[[index]]
    term_warnings <- character()
    if (is.finite(ph_by_term[[column]]) &&
        ph_by_term[[column]] < TIME_VARYING_PH_ALPHA) {
      term_warnings <- c(
        term_warnings,
        paste(
          "Signature-specific proportional-hazards test p < 0.05;",
          "inspect the prespecified temporal diagnostic."
        )
      )
    }
    firth <- fit_firth_sensitivity(
      formula,
      data,
      information,
      term = column,
      effect_label = paste0(signature_names[[column]], " per +1 SD")
    )
    if (identical(firth$status, "failed")) {
      term_warnings <- c(
        term_warnings,
        paste("Firth penalized sensitivity failed:", firth$reason)
      )
    }
    time_varying <- fit_prespecified_time_varying_effect(
      data = data,
      formula_terms = formula_terms,
      marker_formula_term = column,
      marker_coefficient = column,
      effect_label = paste0(signature_names[[column]], " per +1 SD"),
      ph_p_value = ph_by_term[[column]]
    )
    c(
      term,
      list(
        ph_p_value = ph_by_term[[column]],
        ph_global_p_value = global_ph_p,
        penalized_sensitivity = firth,
        time_varying_effect = time_varying,
        warnings = as.list(unique(term_warnings))
      )
    )
  })

  list(
    model = model_id,
    label = label,
    family = family,
    status = "completed",
    ties = "efron",
    marker_columns = as.list(marker_columns),
    covariates = as.list(encoded_covariates),
    covariate_encoding = covariate_encoding,
    n_patients = nrow(data),
    n_events = n_events,
    information_diagnostics = information,
    ph_global_p_value = global_ph_p,
    marker_terms = terms,
    warnings = as.list(unique(model_warnings))
  )
}

univariable_models <- lapply(seq_along(score_columns), function(index) {
  fit_panel_cox(
    paste0("panel_univariable_", index),
    paste(signature_names[[score_columns[[index]]]], "univariable"),
    "univariable",
    score_columns[[index]]
  )
})
joint_model <- fit_panel_cox(
  "panel_joint_unadjusted",
  "Joint unadjusted",
  "joint",
  score_columns
)
adjusted_model <- if (adjustment_requested) {
  fit_panel_cox(
    "panel_joint_adjusted",
    paste(
      "Joint adjusted for",
      clinical_adjustment_label(
        requested_adjustment_covariates,
        requested_external_adjustment_covariates,
        external_covariate_definitions
      )
    ),
    "adjusted",
    score_columns,
    requested_adjustment_covariates,
    requested_external_adjustment_covariates
  )
} else {
  model_skip(
    "panel_joint_adjusted",
    "Joint adjusted",
    "adjusted",
    score_columns,
    "No clinical adjustment covariates were requested.",
    records,
    status = "not_requested"
  )
}

apply_multiplicity <- function(models, family) {
  locations <- list()
  p_values <- numeric()
  for (model_index in seq_along(models)) {
    model <- models[[model_index]]
    if (!identical(model$status, "completed")) next
    for (term_index in seq_along(model$marker_terms %||% list())) {
      value <- suppressWarnings(as.numeric(
        model$marker_terms[[term_index]]$p_value
      ))
      if (length(value) && is.finite(value[[1]])) {
        p_values <- c(p_values, value[[1]])
        locations[[length(locations) + 1L]] <- c(
          model_index,
          term_index
        )
      }
    }
  }
  if (!length(p_values)) {
    return(list(
      models = models,
      summary = list(
        family = family,
        evaluable_terms = 0L,
        methods = as.list(MULTIPLICITY_METHODS)
      )
    ))
  }
  bh <- stats::p.adjust(p_values, method = "BH")
  bonferroni <- stats::p.adjust(p_values, method = "bonferroni")
  for (index in seq_along(locations)) {
    location <- locations[[index]]
    models[[location[[1]]]]$marker_terms[[location[[2]]]]$multiplicity <-
      list(
        family = family,
        family_size = length(p_values),
        bh_q_value = unname(bh[[index]]),
        bonferroni_p_value = unname(bonferroni[[index]])
      )
  }
  list(
    models = models,
    summary = list(
      family = family,
      evaluable_terms = length(p_values),
      methods = as.list(MULTIPLICITY_METHODS)
    )
  )
}

adjusted_univariable <- apply_multiplicity(
  univariable_models,
  "signature_panel_univariable_terms"
)
univariable_models <- adjusted_univariable$models
adjusted_joint <- apply_multiplicity(
  list(joint_model),
  "signature_panel_joint_terms"
)
joint_model <- adjusted_joint$models[[1]]
adjusted_adjusted <- apply_multiplicity(
  list(adjusted_model),
  "signature_panel_adjusted_terms"
)
adjusted_model <- adjusted_adjusted$models[[1]]

fit_panel_fine_gray <- function(
  model_id,
  label,
  family,
  marker_columns,
  covariates = character(),
  external_covariates = character()
) {
  if (!requireNamespace("cmprsk", quietly = TRUE)) {
    return(model_skip(
      model_id,
      label,
      family,
      marker_columns,
      "The cmprsk package is not installed."
    ))
  }
  if (!"competing_risk_status" %in% names(records)) {
    return(model_skip(
      model_id,
      label,
      family,
      marker_columns,
      "Competing-event status was not supplied."
    ))
  }
  external_record_names <- vapply(
    external_covariates,
    external_covariate_record_name,
    character(1)
  )
  fields <- unique(c(
    "time_days",
    "competing_risk_status",
    marker_columns,
    covariates,
    external_record_names
  ))
  missing <- setdiff(fields, names(records))
  if (length(missing)) {
    return(model_skip(
      model_id,
      label,
      family,
      marker_columns,
      paste("Missing Fine-Gray fields:", paste(missing, collapse = ", "))
    ))
  }
  data <- records[, fields, drop = FALSE]
  data$competing_risk_status <- suppressWarnings(
    as.integer(data$competing_risk_status)
  )
  prepared <- tryCatch(
    prepare_model_covariates(
      data,
      covariates,
      external_covariates,
      external_covariate_definitions
    ),
    error = function(error) error
  )
  if (inherits(prepared, "error")) {
    return(model_skip(
      model_id,
      label,
      family,
      marker_columns,
      conditionMessage(prepared),
      data
    ))
  }
  encoded_covariates <- prepared$covariates
  covariate_encoding <- prepared$metadata
  data <- prepared$data[
    ,
    c(
      "time_days",
      "competing_risk_status",
      marker_columns,
      encoded_covariates
    ),
    drop = FALSE
  ]
  data <- droplevels(data[complete.cases(data), , drop = FALSE])
  n_events <- sum(data$competing_risk_status == 1L)
  n_competing <- sum(data$competing_risk_status == 2L)
  if (nrow(data) < MIN_PANEL_PATIENTS ||
      n_events < MIN_PANEL_EVENTS ||
      n_competing < 1L) {
    return(list(
      model = model_id,
      label = label,
      family = family,
      status = "skipped",
      reason = "Fine-Gray requires 10 complete patients, 5 target events and at least 1 competing event.",
      marker_columns = as.list(marker_columns),
      covariates = as.list(encoded_covariates),
      covariate_encoding = covariate_encoding,
      n_patients = nrow(data),
      n_events_of_interest = n_events,
      n_competing_events = n_competing,
      marker_terms = list(),
      warnings = list()
    ))
  }
  for (column in c(marker_columns, encoded_covariates)) {
    if (!model_covariate_has_variation(data[[column]])) {
      return(list(
        model = model_id,
        label = label,
        family = family,
        status = "skipped",
        reason = paste0(column, " has fewer than two observed values."),
        marker_columns = as.list(marker_columns),
        covariates = as.list(encoded_covariates),
        covariate_encoding = covariate_encoding,
        n_patients = nrow(data),
        n_events_of_interest = n_events,
        n_competing_events = n_competing,
        marker_terms = list(),
        warnings = list()
      ))
    }
  }
  formula <- stats::as.formula(
    paste("~", paste(c(marker_columns, encoded_covariates), collapse = " + "))
  )
  matrix <- stats::model.matrix(formula, data = data)
  matrix <- matrix[, colnames(matrix) != "(Intercept)", drop = FALSE]
  fit_warnings <- character()
  fit <- tryCatch(
    withCallingHandlers(
      cmprsk::crr(
        ftime = data$time_days,
        fstatus = data$competing_risk_status,
        cov1 = matrix,
        failcode = 1,
        cencode = 0
      ),
      warning = function(warning) {
        fit_warnings <<- c(fit_warnings, conditionMessage(warning))
        invokeRestart("muffleWarning")
      }
    ),
    error = function(error) error
  )
  if (inherits(fit, "error")) {
    return(list(
      model = model_id,
      label = label,
      family = family,
      status = "failed",
      reason = conditionMessage(fit),
      marker_columns = as.list(marker_columns),
      covariates = as.list(encoded_covariates),
      covariate_encoding = covariate_encoding,
      n_patients = nrow(data),
      n_events_of_interest = n_events,
      n_competing_events = n_competing,
      marker_terms = list(),
      warnings = as.list(unique(fit_warnings))
    ))
  }
  coefficients <- as.numeric(fit$coef)
  names(coefficients) <- names(fit$coef)
  standard_errors <- sqrt(diag(fit$var))
  critical <- stats::qnorm(0.975)
  terms <- lapply(marker_columns, function(column) {
    index <- match(column, names(coefficients))
    if (is.na(index)) return(NULL)
    coefficient <- coefficients[[index]]
    standard_error <- standard_errors[[index]]
    z_value <- coefficient / standard_error
    list(
      term = column,
      signature = signature_names[[column]],
      contrast = "+1 within-panel score SD",
      log_subdistribution_hazard_ratio = unname(coefficient),
      standard_error = unname(standard_error),
      subdistribution_hazard_ratio = unname(exp(coefficient)),
      shr_conf_low = unname(exp(coefficient - critical * standard_error)),
      shr_conf_high = unname(exp(coefficient + critical * standard_error)),
      p_value = unname(
        2 * stats::pnorm(abs(z_value), lower.tail = FALSE)
      ),
      warnings = list()
    )
  })
  terms <- Filter(Negate(is.null), terms)
  finite_terms <- vapply(
    terms,
    function(term) all(is.finite(c(
      term$subdistribution_hazard_ratio,
      term$shr_conf_low,
      term$shr_conf_high,
      term$p_value
    ))),
    logical(1)
  )
  if (length(terms) != length(marker_columns) || !all(finite_terms)) {
    return(list(
      model = model_id,
      label = label,
      family = family,
      status = "failed",
      reason = "The Fine-Gray fit returned an incomplete or non-finite signature estimate.",
      marker_columns = as.list(marker_columns),
      covariates = as.list(encoded_covariates),
      covariate_encoding = covariate_encoding,
      n_patients = nrow(data),
      n_events_of_interest = n_events,
      n_competing_events = n_competing,
      marker_terms = list(),
      warnings = as.list(unique(fit_warnings))
    ))
  }
  parameter_count <- ncol(matrix)
  information <- cox_information_diagnostics(
    n_events,
    parameter_count
  )
  warning <- cox_information_warning(information)
  list(
    model = model_id,
    label = label,
    family = family,
    status = "completed",
    marker_columns = as.list(marker_columns),
    covariates = as.list(encoded_covariates),
    covariate_encoding = covariate_encoding,
    n_patients = nrow(data),
    n_events_of_interest = n_events,
    n_competing_events = n_competing,
    information_diagnostics = information,
    marker_terms = terms,
    warnings = as.list(unique(c(
      fit_warnings,
      if (is.null(warning)) character() else warning
    )))
  )
}

competing_endpoint <- toupper(as.character(payload$endpoint %||% ""))
competing_applicable <- competing_endpoint %in% c("DSS", "DFI", "PFI")
fine_gray_models <- list()
fine_gray_multiplicity <- list()
if (competing_applicable) {
  fg_univariable <- lapply(seq_along(score_columns), function(index) {
    fit_panel_fine_gray(
      paste0("panel_fg_univariable_", index),
      paste(signature_names[[score_columns[[index]]]], "Fine-Gray univariable"),
      "univariable",
      score_columns[[index]]
    )
  })
  fg_joint <- fit_panel_fine_gray(
    "panel_fg_joint_unadjusted",
    "Fine-Gray joint unadjusted",
    "joint",
    score_columns
  )
  fg_adjusted <- if (adjustment_requested) {
    fit_panel_fine_gray(
      "panel_fg_joint_adjusted",
      "Fine-Gray joint adjusted",
      "adjusted",
      score_columns,
      requested_adjustment_covariates,
      requested_external_adjustment_covariates
    )
  } else {
    model_skip(
      "panel_fg_joint_adjusted",
      "Fine-Gray joint adjusted",
      "adjusted",
      score_columns,
      "No clinical adjustment covariates were requested.",
      records,
      status = "not_requested"
    )
  }
  fg_univariable_result <- apply_multiplicity(
    fg_univariable,
    "signature_panel_fine_gray_univariable_terms"
  )
  fg_joint_result <- apply_multiplicity(
    list(fg_joint),
    "signature_panel_fine_gray_joint_terms"
  )
  fg_adjusted_result <- apply_multiplicity(
    list(fg_adjusted),
    "signature_panel_fine_gray_adjusted_terms"
  )
  fine_gray_models <- c(
    fg_univariable_result$models,
    fg_joint_result$models,
    fg_adjusted_result$models
  )
  fine_gray_multiplicity <- list(
    univariable = fg_univariable_result$summary,
    joint = fg_joint_result$summary,
    adjusted = fg_adjusted_result$summary
  )
}

correlation_rows <- list()
for (left in seq_along(score_columns)) {
  for (right in left:length(score_columns)) {
    left_column <- score_columns[[left]]
    right_column <- score_columns[[right]]
    correlation_rows[[length(correlation_rows) + 1L]] <- list(
      signature_a = signature_names[[left_column]],
      signature_b = signature_names[[right_column]],
      pearson = unname(stats::cor(
        records[[left_column]],
        records[[right_column]],
        method = "pearson"
      )),
      spearman = unname(stats::cor(
        records[[left_column]],
        records[[right_column]],
        method = "spearman"
      )),
      n = nrow(records)
    )
  }
}

all_cox_models <- c(
  univariable_models,
  list(joint_model, adjusted_model)
)

flatten_model_rows <- function(models, estimand = "cause_specific") {
  rows <- list()
  for (model in models) {
    if (!identical(model$status, "completed")) next
    for (term in model$marker_terms %||% list()) {
      multiplicity <- term$multiplicity %||% list()
      is_fine_gray <- identical(estimand, "subdistribution")
      rows[[length(rows) + 1L]] <- data.frame(
        estimand = estimand,
        model = as.character(model$model),
        model_label = as.character(model$label),
        family = as.character(model$family),
        signature = as.character(term$signature),
        n_patients = as.integer(model$n_patients),
        n_events = as.integer(
          if (is_fine_gray) model$n_events_of_interest else model$n_events
        ),
        effect = as.numeric(
          if (is_fine_gray) {
            term$subdistribution_hazard_ratio
          } else {
            term$hazard_ratio
          }
        ),
        conf_low = as.numeric(
          if (is_fine_gray) term$shr_conf_low else term$hr_conf_low
        ),
        conf_high = as.numeric(
          if (is_fine_gray) term$shr_conf_high else term$hr_conf_high
        ),
        p_value = as.numeric(term$p_value),
        bh_q_value = as.numeric(
          multiplicity$bh_q_value %||% NA_real_
        ),
        bonferroni_p_value = as.numeric(
          multiplicity$bonferroni_p_value %||% NA_real_
        ),
        stringsAsFactors = FALSE
      )
    }
  }
  if (!length(rows)) {
    return(data.frame())
  }
  do.call(rbind, rows)
}

cox_rows <- flatten_model_rows(all_cox_models)
fine_gray_rows <- flatten_model_rows(
  fine_gray_models,
  estimand = "subdistribution"
)
model_rows <- if (nrow(cox_rows) && nrow(fine_gray_rows)) {
  rbind(cox_rows, fine_gray_rows)
} else if (nrow(cox_rows)) {
  cox_rows
} else {
  fine_gray_rows
}
utils::write.csv(
  model_rows,
  payload$model_results_path,
  row.names = FALSE,
  na = ""
)
correlation_frame <- do.call(
  rbind,
  lapply(correlation_rows, as.data.frame)
)
utils::write.csv(
  correlation_frame,
  payload$correlations_path,
  row.names = FALSE,
  na = ""
)

plot_family_label <- c(
  univariable = "Univariable",
  joint = "Joint",
  adjusted = "Joint + clinical"
)

panel_forest_axis_limits <- function(rows) {
  values <- c(rows$conf_low, rows$effect, rows$conf_high)
  values <- values[is.finite(values) & values > 0]
  if (!length(values)) {
    return(c(0.25, 4))
  }
  c(
    min(0.25, min(values) * 0.82),
    max(4, max(values) * 1.18)
  )
}

shared_panel_forest_axis_limits <- panel_forest_axis_limits(cox_rows)
panel_forest_signature_slots <- length(unique(signature_names))
panel_forest_export_width <- if (
  identical(payload$plot_style$plot_aspect, "square")
) {
  7.5
} else {
  9.4
}

plot_panel_forest <- function(
  rows,
  path,
  title,
  x_limits = shared_panel_forest_axis_limits,
  signature_slots = panel_forest_signature_slots
) {
  if (!nrow(rows)) return(FALSE)
  if (!requireNamespace("ggplot2", quietly = TRUE)) {
    stop("The ggplot2 package is required for signature-panel plots.")
  }
  rows <- rows[
    is.finite(rows$effect) &
      is.finite(rows$conf_low) &
      is.finite(rows$conf_high) &
      rows$effect > 0 &
      rows$conf_low > 0 &
      rows$conf_high > 0,
    ,
    drop = FALSE
  ]
  if (!nrow(rows)) return(FALSE)
  rows$family_label <- unname(plot_family_label[rows$family])
  rows$family_label[is.na(rows$family_label)] <- rows$family[
    is.na(rows$family_label)
  ]
  rows$signature <- factor(
    rows$signature,
    levels = rev(unique(signature_names))
  )
  rows$direction <- ifelse(
    rows$effect < 1,
    "Lower hazard",
    "Higher hazard"
  )
  style <- payload$plot_style$cox_forest %||% list()
  font_family <- as.character(payload$plot_style$font_family %||% "sans")
  base_font_size <- as.numeric(payload$plot_style$base_font_size %||% 12)
  axis_text_size <- as.numeric(payload$plot_style$axis_text_size %||% 11)
  axis_text_face <- plot_font_face(
    payload$plot_style$axis_text_bold %||% FALSE,
    payload$plot_style$axis_text_italic %||% FALSE
  )
  axis_title_size <- as.numeric(payload$plot_style$axis_title_size %||% 12)
  axis_title_face <- plot_font_face(
    payload$plot_style$axis_title_bold %||% FALSE,
    payload$plot_style$axis_title_italic %||% FALSE
  )
  plot_frame_values <- as.character(
    payload$plot_style$plot_frame %||% "open"
  )
  plot_frame <- if (length(plot_frame_values)) {
    trimws(tolower(plot_frame_values[[1]]))
  } else {
    "open"
  }
  if (!plot_frame %in% c("open", "axes", "box")) {
    plot_frame <- "open"
  }
  show_grid <- isTRUE(payload$plot_style$show_grid %||% FALSE)
  colors <- c(
    "Lower hazard" = as.character(
      style$lower_hazard_color %||% "#1f6f8b"
    ),
    "Higher hazard" = as.character(
      style$higher_hazard_color %||% "#b94d48"
    )
  )
  shapes <- c(
    "Univariable" = 16,
    "Joint" = 17,
    "Joint + clinical" = 15
  )
  position <- ggplot2::position_dodge(width = 0.55)
  plot <- ggplot2::ggplot(
    rows,
    ggplot2::aes(
      x = effect,
      y = signature,
      color = direction,
      shape = family_label
    )
  ) +
    ggplot2::geom_vline(
      xintercept = 1,
      linewidth = 0.55,
      color = as.character(style$reference_color %||% "#7b8582")
    ) +
    ggplot2::geom_errorbar(
      ggplot2::aes(xmin = conf_low, xmax = conf_high),
      width = 0,
      linewidth = 0.72,
      position = position
    ) +
    ggplot2::geom_point(size = 2.5, position = position) +
    ggplot2::scale_x_log10(limits = x_limits) +
    ggplot2::scale_y_discrete(drop = FALSE) +
    ggplot2::scale_color_manual(values = colors) +
    ggplot2::scale_shape_manual(values = shapes) +
    ggplot2::labs(
      title = title,
      subtitle = paste0(
        "Cause-specific Cox main effects, HR per +1 within-panel score SD; ",
        nrow(records),
        " common patients"
      ),
      x = as.character(
        style$x_axis_title %||% "Hazard ratio (log scale)"
      ),
      y = NULL,
      color = NULL,
      shape = NULL
    ) +
    ggplot2::theme_minimal(
      base_size = base_font_size,
      base_family = font_family
    ) +
    ggplot2::theme(
      plot.title = ggplot2::element_text(face = "bold"),
      axis.text = ggplot2::element_text(
        size = axis_text_size,
        face = axis_text_face
      ),
      axis.title = ggplot2::element_text(
        size = axis_title_size,
        face = axis_title_face
      ),
      axis.line = ggplot2::element_blank(),
      axis.line.x.bottom = if (identical(plot_frame, "axes")) {
        ggplot2::element_line(color = "#33423e", linewidth = 0.48)
      } else {
        ggplot2::element_blank()
      },
      axis.line.y.left = if (identical(plot_frame, "axes")) {
        ggplot2::element_line(color = "#33423e", linewidth = 0.48)
      } else {
        ggplot2::element_blank()
      },
      axis.ticks = if (identical(plot_frame, "open")) {
        ggplot2::element_blank()
      } else {
        ggplot2::element_line(color = "#33423e", linewidth = 0.42)
      },
      axis.ticks.length = if (identical(plot_frame, "open")) {
        grid::unit(0, "pt")
      } else {
        grid::unit(2.5, "pt")
      },
      panel.border = if (identical(plot_frame, "box")) {
        ggplot2::element_rect(
          color = "#33423e",
          fill = NA,
          linewidth = 0.48
        )
      } else {
        ggplot2::element_blank()
      },
      panel.grid.major.x = if (show_grid) {
        ggplot2::element_line(color = "#e1e7e4", linewidth = 0.35)
      } else {
        ggplot2::element_blank()
      },
      panel.grid.minor.x = if (show_grid) {
        ggplot2::element_line(color = "#edf1ef", linewidth = 0.2)
      } else {
        ggplot2::element_blank()
      },
      panel.grid.minor.y = ggplot2::element_blank(),
      panel.grid.major.y = ggplot2::element_blank(),
      legend.position = "bottom",
      legend.box = "vertical",
      axis.text.y = ggplot2::element_text(face = axis_text_face),
      plot.margin = ggplot2::margin(12, 18, 12, 12)
    )
  width <- panel_forest_export_width
  height <- max(4.2, 2.9 + 0.42 * max(1, signature_slots))
  if (grepl("\\.svg$", path, ignore.case = TRUE)) {
    if (requireNamespace("svglite", quietly = TRUE)) {
      svglite::svglite(path, width = width, height = height)
    } else {
      grDevices::svg(path, width = width, height = height)
    }
    print(plot)
    grDevices::dev.off()
  } else {
    ggplot2::ggsave(
      path,
      plot,
      width = width,
      height = height,
      units = "in",
      dpi = 180,
      bg = "#fbfcfc"
    )
  }
  TRUE
}

style <- payload$plot_style$cox_forest %||% list()
combined_title <- if (isTRUE(style$show_title %||% TRUE)) {
  as.character(
    style$plot_title %||%
      paste(payload$panel_name %||% "Signature panel", "Cox models")
  )
} else {
  ""
}
plot_panel_forest(cox_rows, payload$plot_path, combined_title)
plot_panel_forest(cox_rows, payload$plot_svg_path, combined_title)
plot_panel_forest(cox_rows, payload$cox_forest_path, combined_title)
plot_panel_forest(cox_rows, payload$cox_forest_svg_path, combined_title)

model_layout <- as.character(style$model_layout %||% "combined")
if (identical(model_layout, "separate")) {
  show_titles <- isTRUE(style$show_title %||% TRUE)
  univariable_rows <- cox_rows[cox_rows$family == "univariable", , drop = FALSE]
  joint_rows <- cox_rows[cox_rows$family == "joint", , drop = FALSE]
  adjusted_rows <- cox_rows[cox_rows$family == "adjusted", , drop = FALSE]
  multivariable_rows <- cox_rows[
    cox_rows$family %in% c("joint", "adjusted"),
    ,
    drop = FALSE
  ]
  univariable_title <- if (show_titles) {
    as.character(
      style$univariable_plot_title %||% "Signature panel: univariable Cox"
    )
  } else {
    ""
  }
  multivariable_title <- if (show_titles) {
    as.character(
      style$multivariable_plot_title %||% "Signature panel: joint Cox"
    )
  } else {
    ""
  }
  joint_title <- if (show_titles) {
    as.character(
      style$multivariable_plot_title %||%
        "Signature panel: joint unadjusted Cox"
    )
  } else {
    ""
  }
  adjusted_title <- if (show_titles) {
    as.character(
      style$multivariable_plot_title %||%
        "Signature panel: joint clinically adjusted Cox"
    )
  } else {
    ""
  }
  plot_panel_forest(
    univariable_rows,
    payload$univariable_plot_path,
    univariable_title
  )
  plot_panel_forest(
    univariable_rows,
    payload$univariable_plot_svg_path,
    univariable_title
  )
  plot_panel_forest(
    joint_rows,
    payload$joint_plot_path,
    joint_title
  )
  plot_panel_forest(
    joint_rows,
    payload$joint_plot_svg_path,
    joint_title
  )
  plot_panel_forest(
    adjusted_rows,
    payload$adjusted_plot_path,
    adjusted_title
  )
  plot_panel_forest(
    adjusted_rows,
    payload$adjusted_plot_svg_path,
    adjusted_title
  )
  plot_panel_forest(
    multivariable_rows,
    payload$multivariable_plot_path,
    multivariable_title
  )
  plot_panel_forest(
    multivariable_rows,
    payload$multivariable_plot_svg_path,
    multivariable_title
  )
}

all_warnings <- unique(unlist(lapply(
  c(all_cox_models, fine_gray_models),
  function(model) {
    c(
      unlist(model$warnings %||% list()),
      unlist(lapply(
        model$marker_terms %||% list(),
        function(term) term$warnings %||% list()
      ))
    )
  }
)))
all_warnings <- all_warnings[nzchar(all_warnings)]

clinical_adjustment <- list(
  status = if (adjustment_requested) "requested" else "not_requested",
  requested_covariates = as.list(requested_adjustment_covariates),
  requested_external_covariates = as.list(
    requested_external_adjustment_covariates
  ),
  selected_model = if (adjustment_requested) adjusted_model$model else NULL,
  selected_model_status = adjusted_model$status,
  selected_model_n_patients = adjusted_model$n_patients,
  selected_model_n_events = adjusted_model$n_events
)

output <- list(
  schema_version = "tcga-trace-signature-panel-result-v1",
  analysis_type = "signature_panel",
  n_patients = nrow(records),
  n_events = sum(records$event, na.rm = TRUE),
  endpoint = payload$endpoint,
  panel_name = payload$panel_name,
  signature_panel_cox_models = all_cox_models,
  model_families = list(
    univariable = univariable_models,
    joint = joint_model,
    adjusted = adjusted_model
  ),
  multiplicity = list(
    univariable = adjusted_univariable$summary,
    joint = adjusted_joint$summary,
    adjusted = adjusted_adjusted$summary,
    policy = paste(
      "BH and Bonferroni are applied separately to signature terms within",
      "each model family; clinical covariate terms are excluded."
    )
  ),
  score_correlations = list(
    status = "reported",
    interpretation = paste(
      "Pearson and Spearman correlations are descriptive context and do not",
      "trigger a warning threshold."
    ),
    pairs = correlation_rows
  ),
  competing_risks = list(
    applicable = competing_applicable,
    status = if (!competing_applicable) {
      "not_applicable"
    } else if (any(vapply(
      fine_gray_models,
      function(model) identical(model$status, "completed"),
      logical(1)
    ))) {
      "completed"
    } else {
      "not_evaluable"
    },
    estimand = "Fine-Gray subdistribution hazard ratio per +1 within-panel score SD",
    continuous_fine_gray_models = fine_gray_models,
    multiplicity = fine_gray_multiplicity
  ),
  clinical_adjustment = clinical_adjustment,
  cox_forest_output = list(
    model_layout = model_layout,
    shared_log10_axis_limits = as.list(shared_panel_forest_axis_limits),
    shared_axis_across_model_families = TRUE,
    export_width_inches = panel_forest_export_width,
    signature_row_slots = panel_forest_signature_slots,
    row_spacing_inches = 0.42
  ),
  warnings = as.list(all_warnings),
  software_versions = list(
    R = R.version.string,
    survival = as.character(utils::packageVersion("survival")),
    jsonlite = as.character(utils::packageVersion("jsonlite")),
    ggplot2 = if (requireNamespace("ggplot2", quietly = TRUE)) {
      as.character(utils::packageVersion("ggplot2"))
    } else {
      "not available"
    },
    coxphf = if (requireNamespace("coxphf", quietly = TRUE)) {
      as.character(utils::packageVersion("coxphf"))
    } else {
      "not available"
    },
    cmprsk = if (requireNamespace("cmprsk", quietly = TRUE)) {
      as.character(utils::packageVersion("cmprsk"))
    } else {
      "not available"
    }
  )
)
write_json(
  output,
  payload$output_path,
  auto_unbox = TRUE,
  pretty = TRUE,
  null = "null",
  na = "null",
  digits = NA
)
