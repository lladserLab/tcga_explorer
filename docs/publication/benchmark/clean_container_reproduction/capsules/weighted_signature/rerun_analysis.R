#!/usr/bin/env Rscript
suppressPackageStartupMessages(library(jsonlite))

`%||%` <- function(left, right) {
  if (is.null(left) || length(left) == 0) right else left
}

script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_path <- normalizePath(sub("^--file=", "", script_arg[[1]]))
capsule_dir <- dirname(script_path)
args <- commandArgs(trailingOnly = TRUE)
output_dir <- if (length(args) >= 1) normalizePath(args[[1]], mustWork = FALSE) else file.path(capsule_dir, "rerun_output")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

input_path <- file.path(capsule_dir, "input.json")
engine_path <- file.path(capsule_dir, "km_analysis.R")
expected_path <- file.path(capsule_dir, "metrics.json")
required <- c(input_path, engine_path, file.path(capsule_dir, "clinical_covariates.R"), file.path(capsule_dir, "cox_diagnostics.R"))
missing <- required[!file.exists(required)]
if (length(missing)) stop("Missing reproduction files: ", paste(basename(missing), collapse = ", "))

payload <- fromJSON(input_path, simplifyVector = FALSE)
payload$output_path <- file.path(output_dir, "metrics.json")
payload$png_path <- file.path(output_dir, "plot.png")
payload$svg_path <- file.path(output_dir, "plot.svg")
payload$cox_forest_png_path <- file.path(output_dir, "cox_forest.png")
payload$cox_forest_svg_path <- file.path(output_dir, "cox_forest.svg")
payload$continuous_effect_png_path <- file.path(output_dir, "continuous_effect.png")
payload$continuous_effect_svg_path <- file.path(output_dir, "continuous_effect.svg")
payload$render_png <- FALSE
payload$render_svg <- FALSE
rerun_input <- file.path(output_dir, "input.json")
write_json(payload, rerun_input, auto_unbox = TRUE, null = "null", digits = NA)

command <- file.path(R.home("bin"), "Rscript")
process_output <- system2(command, c(shQuote(engine_path), shQuote(rerun_input)), stdout = TRUE, stderr = TRUE)
status <- attr(process_output, "status") %||% 0L
if (status != 0L || !file.exists(payload$output_path)) {
  writeLines(process_output, file.path(output_dir, "rscript.log"))
  stop("Frozen R analysis failed with status ", status)
}

core_keys <- fromJSON('["n_patients", "n_events", "group_counts", "event_counts", "median_survival_days", "rmst", "logrank_p_value", "hazard_ratio", "hr_conf_low", "hr_conf_high", "hr_p_value", "cox_models", "signature_interaction_cox_models"]')
tolerance_policy <- fromJSON('{"exact": {"absolute": 0.0, "relative": 0.0}, "probability": {"absolute": 1e-12, "relative": 1e-06}, "effect": {"absolute": 1e-08, "relative": 1e-08}, "time": {"absolute": 1e-06, "relative": 1e-09}, "generic": {"absolute": 1e-10, "relative": 1e-08}}', simplifyVector = FALSE)
observed <- fromJSON(payload$output_path, simplifyVector = FALSE)
expected <- if (file.exists(expected_path)) fromJSON(expected_path, simplifyVector = FALSE) else NULL

numeric_scalar <- function(value) {
  is.numeric(value) && length(value) == 1L && !is.na(value)
}

metric_class <- function(path) {
  if (grepl("(\\.n_patients$|\\.n_events$|\\.parameter_count$|\\.group_counts\\.|\\.event_counts\\.|\\.degrees_of_freedom$)", path)) return("exact")
  if (grepl("(p_value|q_value|fdr|probability|alpha)", path, ignore.case = TRUE)) return("probability")
  if (grepl("(time|days|tau|rmst|median_survival)", path, ignore.case = TRUE)) return("time")
  if (grepl("(hazard_ratio|hr_conf|log_hr|standard_error|coefficient|estimate|expression|score|center|deviation|threshold)", path, ignore.case = TRUE)) return("effect")
  "generic"
}

numeric_stats <- setNames(
  lapply(names(tolerance_policy), function(class_name) list(
    comparisons = 0L,
    max_absolute_error = 0,
    max_relative_error = 0,
    max_absolute_path = NULL,
    max_relative_path = NULL
  )),
  names(tolerance_policy)
)

record_numeric_error <- function(class_name, absolute_error, relative_error, path) {
  stats <- numeric_stats[[class_name]]
  stats$comparisons <- stats$comparisons + 1L
  if (absolute_error >= stats$max_absolute_error) {
    stats$max_absolute_error <- absolute_error
    stats$max_absolute_path <- path
  }
  if (relative_error >= stats$max_relative_error) {
    stats$max_relative_error <- relative_error
    stats$max_relative_path <- path
  }
  numeric_stats[[class_name]] <<- stats
}

compare_values <- function(left, right, path = "$") {
  if (is.null(left) && is.null(right)) return(character())
  if (is.list(left) && is.list(right) && !is.null(names(left)) && !is.null(names(right))) {
    keys <- sort(unique(c(names(left), names(right))))
    return(unlist(lapply(keys, function(key) compare_values(left[[key]], right[[key]], paste0(path, ".", key))), use.names = FALSE))
  }
  if (is.list(left) && is.list(right) && is.null(names(left)) && is.null(names(right))) {
    if (length(left) != length(right)) return(sprintf("%s: length %d != %d", path, length(left), length(right)))
    return(unlist(lapply(seq_along(left), function(index) compare_values(left[[index]], right[[index]], sprintf("%s[%d]", path, index - 1L))), use.names = FALSE))
  }
  if (numeric_scalar(left) && numeric_scalar(right)) {
    left_number <- as.numeric(left)
    right_number <- as.numeric(right)
    if (!is.finite(left_number) || !is.finite(right_number)) return(sprintf("%s: %.17g != %.17g", path, left_number, right_number))
    class_name <- metric_class(path)
    policy <- tolerance_policy[[class_name]]
    absolute_error <- abs(left_number - right_number)
    scale <- max(abs(left_number), abs(right_number))
    relative_error <- if (scale == 0) 0 else absolute_error / scale
    limit <- as.numeric(policy$absolute) + as.numeric(policy$relative) * scale
    record_numeric_error(class_name, absolute_error, relative_error, path)
    if (absolute_error <= limit) return(character())
    return(sprintf(
      "%s [%s]: %.17g != %.17g (abs %.3g > %.3g)",
      path, class_name, left_number, right_number, absolute_error, limit
    ))
  }
  if (identical(left, right)) return(character())
  sprintf("%s: values differ", path)
}

differences <- character()
if (!is.null(expected)) {
  for (key in core_keys) {
    differences <- c(differences, compare_values(expected[[key]], observed[[key]], paste0("$.", key)))
  }
}
result <- list(
  schema_version = "tcga-trace-standalone-rerun-v1",
  status = if (length(differences) == 0L) "passed" else "failed",
  compared_to_expected = !is.null(expected),
  numeric_comparison = list(
    policy_version = "tcga-trace-numeric-comparison-v1",
    pass_rule = "absolute_error <= absolute + relative * max(abs(expected), abs(observed))",
    classes = tolerance_policy,
    observed_errors = numeric_stats
  ),
  differences = unname(differences),
  r_version = R.version.string,
  package_versions = as.list(vapply(
    c("jsonlite", "survival", "survminer", "ggplot2", "svglite", "survRM2", "coxphf", "maxstat"),
    function(package) if (requireNamespace(package, quietly = TRUE)) as.character(packageVersion(package)) else "not available",
    character(1)
  ))
)
write_json(result, file.path(output_dir, "reproduction_result.json"), auto_unbox = TRUE, pretty = TRUE)
writeLines(process_output, file.path(output_dir, "rscript.log"))
if (length(differences)) quit(status = 1L)
cat("Standalone reproduction passed\n")
