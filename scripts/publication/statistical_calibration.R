suppressPackageStartupMessages({
  library(jsonlite)
  library(maxstat)
  library(survival)
  library(survRM2)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1) {
  stop("Usage: Rscript statistical_calibration.R <design.json>")
}

design <- fromJSON(args[[1]], simplifyVector = TRUE)

`%||%` <- function(left, right) {
  if (is.null(left) || length(left) == 0) {
    return(right)
  }
  left
}

alpha <- as.numeric(design$alpha %||% 0.05)
seed <- as.integer(design$seed %||% 20260725L)
permutation_replicates <- as.integer(design$permutation_replicates %||% 2000L)
simulation_replicates <- as.integer(design$simulation_replicates %||% 2000L)
simulation_n <- as.integer(design$simulation_n %||% 300L)
methods <- as.character(
  design$methods %||% c(
    "maxstat",
    "median",
    "upper_quartile",
    "upper_lower_quartile",
    "percentile"
  )
)
workers <- max(1L, as.integer(design$workers %||% 1L))

supported_methods <- c(
  "maxstat",
  "median",
  "upper_quartile",
  "upper_lower_quartile",
  "percentile"
)
if (!all(methods %in% supported_methods)) {
  stop("Unsupported cutpoint method in calibration design.")
}
if (permutation_replicates < 1 || simulation_replicates < 1) {
  stop("Calibration requires at least one permutation and one simulation replicate.")
}
if (simulation_n < 50) {
  stop("Simulation sample size must be at least 50.")
}

scalar_number <- function(value) {
  if (is.null(value) || length(value) == 0) {
    return(NA_real_)
  }
  suppressWarnings(as.numeric(unlist(value, use.names = FALSE)[[1]]))
}

finite_p <- function(value) {
  value <- scalar_number(value)
  if (!is.finite(value)) {
    return(NA_real_)
  }
  min(1, max(0, value))
}

safe_try <- function(expression) {
  tryCatch(
    withCallingHandlers(
      expression,
      warning = function(warning) {
        invokeRestart("muffleWarning")
      }
    ),
    error = function(error) error
  )
}

audit <- fromJSON(design$audit_report, simplifyVector = FALSE)
audit_records <- audit$cohort_selection$continuous_patient_records %||% list()
if (!length(audit_records)) {
  stop("The audit report has no continuous patient records.")
}

record_value <- function(record, field) {
  scalar_number(record[[field]])
}

observed_data <- do.call(
  rbind,
  lapply(audit_records, function(record) {
    data.frame(
      time = record_value(record, "time_days"),
      event = record_value(record, "event"),
      x = record_value(record, "expression_value"),
      stringsAsFactors = FALSE
    )
  })
)
observed_data <- observed_data[
  is.finite(observed_data$time) &
    observed_data$time > 0 &
    observed_data$event %in% c(0, 1) &
    is.finite(observed_data$x),
  ,
  drop = FALSE
]
observed_data$event <- as.integer(observed_data$event)
if (nrow(observed_data) < 50 || sum(observed_data$event) < 20) {
  stop("The observed calibration cohort has insufficient complete records or events.")
}

cohort_tau <- function(data, maximum) {
  min(
    as.numeric(maximum),
    as.numeric(quantile(data$time, probs = 0.75, names = FALSE, type = 7))
  )
}

fit_continuous <- function(data) {
  expression_sd <- sd(data$x)
  if (!is.finite(expression_sd) || expression_sd <= 0) {
    return(list(
      cox_p = NA_real_,
      ph_p = NA_real_,
      spline_overall_p = NA_real_,
      spline_nonlinearity_p = NA_real_
    ))
  }
  data$x_z <- as.numeric(scale(data$x))
  linear_fit <- safe_try(
    coxph(Surv(time, event) ~ x_z, data = data, ties = "efron", x = TRUE)
  )
  if (inherits(linear_fit, "error")) {
    return(list(
      cox_p = NA_real_,
      ph_p = NA_real_,
      spline_overall_p = NA_real_,
      spline_nonlinearity_p = NA_real_
    ))
  }
  linear_summary <- summary(linear_fit)
  cox_p <- finite_p(linear_summary$coefficients[1, "Pr(>|z|)"])
  ph_fit <- safe_try(cox.zph(linear_fit))
  ph_p <- NA_real_
  if (!inherits(ph_fit, "error") &&
      !is.null(ph_fit$table) &&
      "x_z" %in% rownames(ph_fit$table)) {
    ph_p <- finite_p(ph_fit$table["x_z", "p"])
  }

  knot_probabilities <- c(0.05, 0.35, 0.65, 0.95)
  knots_raw <- as.numeric(
    quantile(
      data$x,
      probs = knot_probabilities,
      names = FALSE,
      type = 7
    )
  )
  if (length(unique(knots_raw)) < 4 || sum(data$event) < 15) {
    return(list(
      cox_p = cox_p,
      ph_p = ph_p,
      spline_overall_p = NA_real_,
      spline_nonlinearity_p = NA_real_
    ))
  }
  center <- mean(data$x)
  knots_z <- (knots_raw - center) / expression_sd
  basis <- splines::ns(
    data$x_z,
    knots = knots_z[c(2, 3)],
    Boundary.knots = knots_z[c(1, 4)],
    intercept = FALSE
  )
  colnames(basis) <- paste0("spline_", seq_len(ncol(basis)))
  spline_data <- cbind(data, as.data.frame(basis))
  spline_formula <- as.formula(
    paste("Surv(time, event) ~", paste(colnames(basis), collapse = " + "))
  )
  spline_fit <- safe_try(
    coxph(spline_formula, data = spline_data, ties = "efron", x = TRUE)
  )
  if (inherits(spline_fit, "error")) {
    return(list(
      cox_p = cox_p,
      ph_p = ph_p,
      spline_overall_p = NA_real_,
      spline_nonlinearity_p = NA_real_
    ))
  }
  linear_loglik <- as.numeric(logLik(linear_fit))
  spline_loglik <- as.numeric(logLik(spline_fit))
  nonlinear_df <- attr(logLik(spline_fit), "df") - attr(logLik(linear_fit), "df")
  nonlinear_chisq <- max(0, 2 * (spline_loglik - linear_loglik))
  spline_summary <- summary(spline_fit)
  list(
    cox_p = cox_p,
    ph_p = ph_p,
    spline_overall_p = finite_p(spline_summary$logtest[["pvalue"]]),
    spline_nonlinearity_p = finite_p(
      pchisq(nonlinear_chisq, df = nonlinear_df, lower.tail = FALSE)
    )
  )
}

assign_group <- function(data, method) {
  x <- data$x
  corrected_p <- NA_real_
  threshold <- NA_real_
  labels <- rep(NA_character_, length(x))

  if (method == "maxstat") {
    maxstat_fit <- safe_try(
      maxstat.test(
        Surv(time, event) ~ x,
        data = data,
        smethod = "LogRank",
        pmethod = "Lau94",
        minprop = 0.15,
        maxprop = 0.85
      )
    )
    if (inherits(maxstat_fit, "error")) {
      return(list(data = data[FALSE, , drop = FALSE], corrected_p = NA_real_))
    }
    threshold <- scalar_number(maxstat_fit$estimate)
    corrected_p <- finite_p(maxstat_fit$p.value)
    if (is.finite(corrected_p)) {
      corrected_p <- min(1, max(0, corrected_p))
    }
    labels <- ifelse(x <= threshold, "Low", "High")
  } else if (method == "median") {
    threshold <- median(x)
    labels <- ifelse(x <= threshold, "Low", "High")
  } else if (method == "upper_quartile") {
    threshold <- as.numeric(quantile(x, probs = 0.75, names = FALSE, type = 7))
    labels <- ifelse(x >= threshold, "High", "Low")
  } else if (method == "upper_lower_quartile") {
    lower <- as.numeric(quantile(x, probs = 0.25, names = FALSE, type = 7))
    upper <- as.numeric(quantile(x, probs = 0.75, names = FALSE, type = 7))
    labels <- ifelse(x <= lower, "Low", ifelse(x >= upper, "High", NA_character_))
  }

  grouped <- data[!is.na(labels), , drop = FALSE]
  grouped$group <- factor(labels[!is.na(labels)], levels = c("Low", "High"))
  list(data = grouped, corrected_p = corrected_p)
}

fit_grouped <- function(data, method, tau) {
  assigned <- assign_group(data, method)
  grouped <- assigned$data
  empty <- list(
    n = nrow(grouped),
    events = sum(grouped$event),
    logrank_p = NA_real_,
    cox_p = NA_real_,
    ph_p = NA_real_,
    rmst_p = NA_real_,
    maxstat_corrected_p = assigned$corrected_p
  )
  if (nrow(grouped) < 20 ||
      sum(grouped$event) < 5 ||
      length(unique(grouped$group)) != 2) {
    return(empty)
  }

  logrank_fit <- safe_try(survdiff(Surv(time, event) ~ group, data = grouped))
  logrank_p <- if (inherits(logrank_fit, "error")) {
    NA_real_
  } else {
    finite_p(
      pchisq(
        logrank_fit$chisq,
        df = length(logrank_fit$n) - 1,
        lower.tail = FALSE
      )
    )
  }

  cox_fit <- safe_try(
    coxph(Surv(time, event) ~ group, data = grouped, ties = "efron", x = TRUE)
  )
  cox_p <- NA_real_
  ph_p <- NA_real_
  if (!inherits(cox_fit, "error")) {
    cox_p <- finite_p(summary(cox_fit)$coefficients[1, "Pr(>|z|)"])
    ph_fit <- safe_try(cox.zph(cox_fit))
    if (!inherits(ph_fit, "error") && !is.null(ph_fit$table)) {
      ph_rows <- setdiff(rownames(ph_fit$table), "GLOBAL")
      if (length(ph_rows)) {
        ph_p <- finite_p(ph_fit$table[ph_rows[[1]], "p"])
      }
    }
  }

  rmst_p <- NA_real_
  at_risk <- tapply(grouped$time >= tau, grouped$group, sum)
  supports_tau <- tapply(grouped$time, grouped$group, max) >= tau
  if (length(at_risk) == 2 &&
      all(at_risk >= 5) &&
      all(supports_tau)) {
    arm <- as.integer(grouped$group == "High")
    rmst_fit <- safe_try(
      rmst2(
        time = grouped$time,
        status = grouped$event,
        arm = arm,
        tau = tau
      )
    )
    if (!inherits(rmst_fit, "error")) {
      rmst_p <- finite_p(
        rmst_fit$unadjusted.result["RMST (arm=1)-(arm=0)", "p"]
      )
    }
  }

  list(
    n = nrow(grouped),
    events = sum(grouped$event),
    logrank_p = logrank_p,
    cox_p = cox_p,
    ph_p = ph_p,
    rmst_p = rmst_p,
    maxstat_corrected_p = assigned$corrected_p
  )
}

analyse_data <- function(data, tau) {
  continuous <- fit_continuous(data)
  grouped <- setNames(
    lapply(methods, function(method) fit_grouped(data, method, tau)),
    methods
  )
  family_p <- vapply(methods, function(method) {
    if (method == "maxstat") {
      grouped[[method]]$maxstat_corrected_p
    } else {
      grouped[[method]]$logrank_p
    }
  }, numeric(1))
  family_adjusted_p <- rep(NA_real_, length(family_p))
  evaluable <- is.finite(family_p)
  if (any(evaluable)) {
    family_adjusted_p[evaluable] <- p.adjust(
      family_p[evaluable],
      method = "holm"
    )
  }
  names(family_adjusted_p) <- methods
  list(
    continuous = continuous,
    grouped = grouped,
    family_any_holm = any(family_adjusted_p <= alpha, na.rm = TRUE),
    family_any_naive = any(
      vapply(grouped, function(item) item$logrank_p, numeric(1)) <= alpha,
      na.rm = TRUE
    ),
    family_min_adjusted_p = if (any(is.finite(family_adjusted_p))) {
      min(family_adjusted_p, na.rm = TRUE)
    } else {
      NA_real_
    }
  )
}

flatten_analysis <- function(
  analysis,
  analysis_type,
  scenario,
  replicate,
  n,
  events,
  tau
) {
  row <- list(
    analysis_type = analysis_type,
    scenario = scenario,
    replicate = replicate,
    n = n,
    events = events,
    event_fraction = events / n,
    tau = tau,
    continuous_cox_p = analysis$continuous$cox_p,
    continuous_ph_p = analysis$continuous$ph_p,
    spline_overall_p = analysis$continuous$spline_overall_p,
    spline_nonlinearity_p = analysis$continuous$spline_nonlinearity_p,
    grouped_family_any_holm = as.integer(analysis$family_any_holm),
    grouped_family_any_naive = as.integer(analysis$family_any_naive),
    grouped_family_min_adjusted_p = analysis$family_min_adjusted_p
  )
  for (method in methods) {
    item <- analysis$grouped[[method]]
    row[[paste0(method, "_n")]] <- item$n
    row[[paste0(method, "_events")]] <- item$events
    row[[paste0(method, "_logrank_p")]] <- item$logrank_p
    row[[paste0(method, "_cox_p")]] <- item$cox_p
    row[[paste0(method, "_ph_p")]] <- item$ph_p
    row[[paste0(method, "_rmst_p")]] <- item$rmst_p
    row[[paste0(method, "_maxstat_corrected_p")]] <- item$maxstat_corrected_p
  }
  row
}

run_parallel <- function(index, function_body) {
  if (.Platform$OS.type == "unix" && workers > 1) {
    return(
      parallel::mclapply(
        index,
        function_body,
        mc.cores = workers,
        mc.preschedule = TRUE
      )
    )
  }
  lapply(index, function_body)
}

observed_tau <- cohort_tau(
  observed_data,
  as.numeric(design$observed_max_tau %||% 1826.25)
)
permutation_rows <- run_parallel(
  seq_len(permutation_replicates),
  function(index) {
    set.seed(seed + index)
    permuted <- observed_data
    permuted$x <- sample(permuted$x, replace = FALSE)
    analysis <- analyse_data(permuted, observed_tau)
    flatten_analysis(
      analysis,
      analysis_type = "observed_expression_permutation",
      scenario = "observed_null_permutation",
      replicate = index,
      n = nrow(permuted),
      events = sum(permuted$event),
      tau = observed_tau
    )
  }
)
permutation_frame <- do.call(
  rbind,
  lapply(permutation_rows, function(row) {
    as.data.frame(row, stringsAsFactors = FALSE, check.names = FALSE)
  })
)

piecewise_event_time <- function(
  x,
  baseline_rate,
  change_time,
  beta_before,
  beta_after
) {
  exponential_draw <- rexp(length(x))
  rate_before <- baseline_rate * exp(beta_before * x)
  rate_after <- baseline_rate * exp(beta_after * x)
  cumulative_before <- rate_before * change_time
  ifelse(
    exponential_draw <= cumulative_before,
    exponential_draw / rate_before,
    change_time + (exponential_draw - cumulative_before) / rate_after
  )
}

simulate_dataset <- function(scenario, n) {
  x <- rnorm(n)
  baseline_rate <- 0.08
  if (scenario == "null") {
    event_time <- rexp(n, rate = baseline_rate)
  } else if (scenario == "linear_ph") {
    event_time <- rexp(n, rate = baseline_rate * exp(log(1.5) * x))
  } else if (scenario == "delayed_non_ph") {
    event_time <- piecewise_event_time(
      x,
      baseline_rate = baseline_rate,
      change_time = 2.5,
      beta_before = 0,
      beta_after = log(2)
    )
  } else if (scenario == "u_shaped_nonlinear") {
    log_hazard <- log(1.8) * (x^2 - 1)
    event_time <- rexp(n, rate = baseline_rate * exp(log_hazard))
  } else {
    stop("Unknown simulation scenario.")
  }
  censor_time <- rexp(n, rate = 0.04)
  administrative_time <- 8
  observed_time <- pmin(event_time, censor_time, administrative_time)
  event <- as.integer(
    event_time <= censor_time & event_time <= administrative_time
  )
  data.frame(time = observed_time, event = event, x = x)
}

simulation_scenarios <- c(
  "null",
  "linear_ph",
  "delayed_non_ph",
  "u_shaped_nonlinear"
)
simulation_rows <- unlist(
  lapply(seq_along(simulation_scenarios), function(scenario_index) {
    scenario <- simulation_scenarios[[scenario_index]]
    run_parallel(
      seq_len(simulation_replicates),
      function(index) {
        set.seed(seed + scenario_index * 1000000L + index)
        simulated <- simulate_dataset(scenario, simulation_n)
        tau <- cohort_tau(
          simulated,
          as.numeric(design$simulation_max_tau %||% 5)
        )
        analysis <- analyse_data(simulated, tau)
        flatten_analysis(
          analysis,
          analysis_type = "known_truth_simulation",
          scenario = scenario,
          replicate = index,
          n = nrow(simulated),
          events = sum(simulated$event),
          tau = tau
        )
      }
    )
  }),
  recursive = FALSE
)
simulation_frame <- do.call(
  rbind,
  lapply(simulation_rows, function(row) {
    as.data.frame(row, stringsAsFactors = FALSE, check.names = FALSE)
  })
)

wilson_interval <- function(successes, total, confidence = 0.95) {
  if (total < 1) {
    return(c(NA_real_, NA_real_))
  }
  z <- qnorm(1 - (1 - confidence) / 2)
  proportion <- successes / total
  denominator <- 1 + z^2 / total
  center <- (proportion + z^2 / (2 * total)) / denominator
  radius <- (
    z *
      sqrt(
        proportion * (1 - proportion) / total +
          z^2 / (4 * total^2)
      ) /
      denominator
  )
  c(max(0, center - radius), min(1, center + radius))
}

metric_columns <- c(
  continuous_linear = "continuous_cox_p",
  spline_nonlinearity = "spline_nonlinearity_p",
  marker_ph = "continuous_ph_p",
  grouped_family_holm = "grouped_family_min_adjusted_p",
  maxstat_naive = "maxstat_logrank_p",
  maxstat_lau94 = "maxstat_maxstat_corrected_p",
  median_logrank = "median_logrank_p",
  median_cox = "median_cox_p",
  median_rmst = "median_rmst_p"
)

summarize_rejection <- function(frame) {
  scenarios <- unique(frame$scenario)
  summaries <- list()
  cursor <- 1L
  for (scenario in scenarios) {
    scenario_frame <- frame[frame$scenario == scenario, , drop = FALSE]
    for (metric in names(metric_columns)) {
      column <- metric_columns[[metric]]
      values <- suppressWarnings(as.numeric(scenario_frame[[column]]))
      evaluable <- sum(is.finite(values))
      rejected <- sum(values <= alpha, na.rm = TRUE)
      interval <- wilson_interval(rejected, evaluable)
      summaries[[cursor]] <- list(
        scenario = scenario,
        metric = metric,
        rejected = rejected,
        evaluable = evaluable,
        rate = if (evaluable) rejected / evaluable else NA_real_,
        confidence_low = interval[[1]],
        confidence_high = interval[[2]]
      )
      cursor <- cursor + 1L
    }
  }
  summaries
}

negative_log_p <- function(values) {
  -log10(pmax(as.numeric(values), .Machine$double.xmin))
}

pairwise_p_correlation <- function(frame, left, right) {
  left_values <- suppressWarnings(as.numeric(frame[[left]]))
  right_values <- suppressWarnings(as.numeric(frame[[right]]))
  complete <- is.finite(left_values) & is.finite(right_values)
  if (sum(complete) < 3) {
    return(NA_real_)
  }
  cor(
    negative_log_p(left_values[complete]),
    negative_log_p(right_values[complete]),
    method = "spearman"
  )
}

median_logrank <- as.numeric(permutation_frame$median_logrank_p)
median_cox <- as.numeric(permutation_frame$median_cox_p)
median_rmst <- as.numeric(permutation_frame$median_rmst_p)
all_evaluable <- is.finite(median_logrank) &
  is.finite(median_cox) &
  is.finite(median_rmst)
all_three_rejected <- sum(
  median_logrank[all_evaluable] <= alpha &
    median_cox[all_evaluable] <= alpha &
    median_rmst[all_evaluable] <= alpha
)
all_three_interval <- wilson_interval(
  all_three_rejected,
  sum(all_evaluable)
)

result <- list(
  schema_version = "tcga-trace-statistical-calibration-v2",
  design = list(
    alpha = alpha,
    seed = seed,
    permutation_replicates = permutation_replicates,
    simulation_replicates_per_scenario = simulation_replicates,
    simulation_n = simulation_n,
    methods = as.list(methods),
    observed_tau_definition = "minimum of 1826.25 days and the observed cohort 75th percentile, fixed before permutation",
    simulation_tau_definition = "minimum of 5 time units and each generated cohort 75th percentile, fixed before grouping",
    maxstat_inference = "Lau94 corrected p-value, bounded to [0,1], enters the grouped Holm family; the selected-group log-rank p-value is retained only as a naive post-selection diagnostic",
    multiplicity = "Holm adjustment across the four prespecified grouped methods within each replicate",
    monte_carlo_interval = "Wilson 95% interval for each rejection proportion"
  ),
  source = list(
    analysis_id = audit$analysis_id,
    audit_schema_version = audit$schema_version,
    audit_reproducibility_hash = audit$reproducibility_hash,
    continuous_patient_records_sha256 = audit$cohort_selection$continuous_patient_records_sha256,
    patients = nrow(observed_data),
    events = sum(observed_data$event),
    tau = observed_tau
  ),
  scenario_truth = list(
    null = "No expression effect; exponential baseline event time.",
    linear_ph = "Constant log HR log(1.5) per one-SD expression increase.",
    delayed_non_ph = "No expression effect before time 2.5; log HR log(2) per SD thereafter.",
    u_shaped_nonlinear = "Log hazard log(1.8) times (x squared minus 1), with no linear monotone truth."
  ),
  permutation_summary = summarize_rejection(permutation_frame),
  simulation_summary = summarize_rejection(simulation_frame),
  dependence = list(
    scenario = "observed_null_permutation",
    method = "median",
    spearman_logrank_vs_cox = pairwise_p_correlation(
      permutation_frame,
      "median_logrank_p",
      "median_cox_p"
    ),
    spearman_logrank_vs_rmst = pairwise_p_correlation(
      permutation_frame,
      "median_logrank_p",
      "median_rmst_p"
    ),
    spearman_cox_vs_rmst = pairwise_p_correlation(
      permutation_frame,
      "median_cox_p",
      "median_rmst_p"
    ),
    all_three_nominal = list(
      rejected = all_three_rejected,
      evaluable = sum(all_evaluable),
      rate = if (sum(all_evaluable)) {
        all_three_rejected / sum(all_evaluable)
      } else {
        NA_real_
      },
      confidence_low = all_three_interval[[1]],
      confidence_high = all_three_interval[[2]]
    ),
    interpretation = "Log-rank, grouped Cox and RMST are correlated summaries and are not treated as independent evidence barriers."
  ),
  software_versions = list(
    R = R.version.string,
    survival = as.character(packageVersion("survival")),
    maxstat = as.character(packageVersion("maxstat")),
    survRM2 = as.character(packageVersion("survRM2")),
    jsonlite = as.character(packageVersion("jsonlite"))
  )
)

dir.create(dirname(design$output_json), recursive = TRUE, showWarnings = FALSE)
write.csv(
  permutation_frame,
  design$permutation_csv,
  row.names = FALSE,
  na = ""
)
write.csv(
  simulation_frame,
  design$simulation_csv,
  row.names = FALSE,
  na = ""
)
write_json(
  result,
  design$output_json,
  pretty = TRUE,
  auto_unbox = TRUE,
  null = "null",
  na = "null",
  digits = 16
)
