suppressPackageStartupMessages({
  library(jsonlite)
  library(survival)
  library(survminer)
  library(ggplot2)
  library(svglite)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1) {
  stop("Usage: Rscript km_analysis.R <input.json>")
}

payload <- fromJSON(args[[1]], simplifyDataFrame = FALSE)

`%||%` <- function(left, right) {
  if (is.null(left) || length(left) == 0) {
    return(right)
  }
  left
}

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
  "os_time_days",
  "os_event",
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

records <- do.call(rbind, lapply(payload$records, normalize_record))

if (nrow(records) < 2) {
  stop("At least two records are required")
}

records$time_days <- as.numeric(records$time_days)
records$event <- as.integer(records$event)
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
records$stage <- trimws(as.character(records$stage))
records$stage[is.na(records$stage) | records$stage == ""] <- NA
records$grade <- trimws(as.character(records$grade))
records$grade[is.na(records$grade) | records$grade == ""] <- NA
group_levels <- payload$group_levels
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
p_value <- 1 - pchisq(survdiff_fit$chisq, length(survdiff_fit$n) - 1)

cox_metrics <- list()
cox_models <- list()
cox_warning_messages <- c()

cox_skip <- function(model_id, label, covariates, reason, data = records) {
  list(
    model = model_id,
    label = label,
    covariates = as.list(covariates),
    status = "skipped",
    reason = reason,
    n_patients = nrow(data),
    n_events = sum(data$event, na.rm = TRUE)
  )
}

fit_cox_model <- function(model_id, label, covariates) {
  data <- records[, c("time_days", "event", "group", covariates), drop = FALSE]
  data <- data[is.finite(data$time_days) & !is.na(data$event) & !is.na(data$group), , drop = FALSE]
  for (covariate in covariates) {
    data[[covariate]] <- trimws(as.character(data[[covariate]]))
    data[[covariate]][is.na(data[[covariate]]) | data[[covariate]] == ""] <- NA
  }
  data <- data[complete.cases(data), , drop = FALSE]
  data$group <- droplevels(factor(data$group, levels = group_levels))
  if (nrow(data) < 10) {
    return(cox_skip(model_id, label, covariates, "Fewer than 10 complete patients after covariate filtering.", data))
  }
  if (sum(data$event, na.rm = TRUE) < 1) {
    return(cox_skip(model_id, label, covariates, "No events after covariate filtering.", data))
  }
  if (length(levels(data$group)) != 2) {
    return(cox_skip(model_id, label, covariates, "Cox marker HR is reported only for two expression groups.", data))
  }
  for (covariate in covariates) {
    data[[covariate]] <- droplevels(factor(data[[covariate]]))
    if (length(levels(data[[covariate]])) < 2) {
      return(cox_skip(model_id, label, covariates, paste0("Covariate ", covariate, " has fewer than two levels after filtering."), data))
    }
  }

  formula_terms <- c("group", covariates)
  formula <- as.formula(paste("Surv(time_days, event) ~", paste(formula_terms, collapse = " + ")))
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
    return(list(
      model = model_id,
      label = label,
      covariates = as.list(covariates),
      status = "failed",
      reason = conditionMessage(fit),
      n_patients = nrow(data),
      n_events = sum(data$event, na.rm = TRUE)
    ))
  }

  cox_summary <- summary(fit)
  coefficient_names <- rownames(cox_summary$coefficients)
  group_rows <- grep("^group", coefficient_names)
  if (length(group_rows) != 1) {
    return(cox_skip(model_id, label, covariates, "Could not isolate a single expression-group coefficient.", data))
  }
  row_index <- group_rows[[1]]
  hazard_ratio <- unname(cox_summary$conf.int[row_index, "exp(coef)"])
  hr_conf_low <- unname(cox_summary$conf.int[row_index, "lower .95"])
  hr_conf_high <- unname(cox_summary$conf.int[row_index, "upper .95"])
  p_value <- unname(cox_summary$coefficients[row_index, "Pr(>|z|)"])
  coefficient <- unname(cox_summary$coefficients[row_index, "coef"])
  standard_error <- unname(cox_summary$coefficients[row_index, "se(coef)"])
  if (!is.finite(hazard_ratio) || !is.finite(hr_conf_low) || !is.finite(hr_conf_high)) {
    return(cox_skip(model_id, label, covariates, "Model did not produce finite HR confidence intervals.", data))
  }
  if (length(model_warnings)) {
    cox_warning_messages <<- c(cox_warning_messages, paste(label, paste(unique(model_warnings), collapse = " | "), sep = ": "))
  }
  list(
    model = model_id,
    label = label,
    covariates = as.list(covariates),
    status = "completed",
    term = coefficient_names[[row_index]],
    contrast = paste(group_levels[[2]], "vs", group_levels[[1]]),
    n_patients = nrow(data),
    n_events = sum(data$event, na.rm = TRUE),
    log_hr = coefficient,
    standard_error = standard_error,
    hazard_ratio = hazard_ratio,
    hr_conf_low = hr_conf_low,
    hr_conf_high = hr_conf_high,
    p_value = p_value,
    warnings = as.list(unique(model_warnings))
  )
}

if (length(levels(records$group)) == 2) {
  cox_models <- list(
    fit_cox_model("univariable", "Univariable", character(0)),
    fit_cox_model("stage_adjusted", "Adjusted for stage", c("stage")),
    fit_cox_model("grade_adjusted", "Adjusted for grade", c("grade")),
    fit_cox_model("stage_grade_adjusted", "Adjusted for stage and grade", c("stage", "grade"))
  )
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
palette <- unlist(plot_style$palette %||% c("#2f756f", "#d7953f", "#b44b3f"))
if (length(palette) < length(levels(records$group))) {
  palette <- rep(palette, length.out = length(levels(records$group)))
}
palette <- palette[seq_len(length(levels(records$group)))]

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
show_grid <- if (is.null(plot_style$show_grid)) TRUE else isTRUE(plot_style$show_grid)
plot_aspect <- plot_style$plot_aspect %||% "rectangular"
if (!plot_aspect %in% c("rectangular", "square")) {
  plot_aspect <- "rectangular"
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
plot_theme <- theme_minimal(base_size = base_font_size, base_family = font_family) +
  theme(
    axis.text = element_text(size = axis_text_size),
    axis.title = element_text(size = axis_title_size),
    panel.grid.major = if (show_grid) element_line(color = "#e1e7e4", linewidth = 0.35) else element_blank(),
    panel.grid.minor = if (show_grid) element_line(color = "#edf1ef", linewidth = 0.2) else element_blank()
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
  cox_plot_data$hr_label <- paste0(
    sprintf("%.2f", cox_plot_data$hazard_ratio),
    " (",
    sprintf("%.2f", cox_plot_data$hr_conf_low),
    "-",
    sprintf("%.2f", cox_plot_data$hr_conf_high),
    "), ",
    vapply(cox_plot_data$p_value, format_p_value, character(1))
  )
  cox_x_values <- c(cox_plot_data$hr_conf_low, cox_plot_data$hazard_ratio, cox_plot_data$hr_conf_high)
  cox_x_values <- cox_x_values[is.finite(cox_x_values) & cox_x_values > 0]
  cox_x_min <- min(0.25, min(cox_x_values, na.rm = TRUE) * 0.82)
  cox_x_max <- max(4, max(cox_x_values, na.rm = TRUE) * 1.18)
  cox_forest_plot <- ggplot(cox_plot_data, aes(x = hazard_ratio, y = label)) +
    geom_vline(xintercept = 1, color = "#7b8582", linewidth = 0.45, linetype = "dashed") +
    geom_segment(aes(x = hr_conf_low, xend = hr_conf_high, yend = label, color = direction), linewidth = 1.0) +
    geom_point(aes(color = direction), size = 3.4) +
    geom_text(aes(x = cox_x_max, label = hr_label), hjust = 1, size = base_font_size / ggplot2::.pt, family = font_family) +
    scale_x_log10(limits = c(cox_x_min, cox_x_max)) +
    scale_color_manual(values = c("Higher hazard" = "#b44b3f", "Lower hazard" = "#2f756f"), guide = "none") +
    labs(
      title = "Cox proportional hazards models",
      subtitle = paste(group_levels[[2]], "vs", group_levels[[1]], "expression group"),
      x = "Hazard ratio (log scale)",
      y = NULL
    ) +
    plot_theme +
    theme(
      plot.title = element_text(face = "bold"),
      plot.subtitle = element_text(color = "#586864"),
      panel.grid.minor = element_blank()
    )
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
  ggplot2 = as.character(packageVersion("ggplot2")),
  svglite = as.character(packageVersion("svglite"))
)

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
    cox_models = cox_models,
    cutpoint_details = payload$cutpoint_details,
    warnings = warnings,
    software_versions = software_versions
  ),
  cox_metrics
)

write_json(metrics, payload$output_path, pretty = TRUE, auto_unbox = TRUE, null = "null", na = "null", digits = 16)
