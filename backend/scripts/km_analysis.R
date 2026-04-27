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
  "group",
  "time_days",
  "event",
  "os_time_days",
  "os_event",
  "sample_type",
  "stage",
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
records$group <- factor(records$group, levels = payload$group_levels)
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
cox_warning <- NULL
if (length(levels(records$group)) == 2) {
  cox_fit <- tryCatch(coxph(surv_obj ~ group, data = records), error = function(e) e)
  if (inherits(cox_fit, "error")) {
    cox_warning <- conditionMessage(cox_fit)
  } else {
    cox_summary <- summary(cox_fit)
    cox_metrics <- list(
      hazard_ratio = unname(cox_summary$conf.int[1, "exp(coef)"]),
      hr_conf_low = unname(cox_summary$conf.int[1, "lower .95"]),
      hr_conf_high = unname(cox_summary$conf.int[1, "upper .95"]),
      hr_p_value = unname(cox_summary$coefficients[1, "Pr(>|z|)"])
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
    median_survival[[group_name]] <- unname(median_table[row_name, "median"])
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

plot_obj <- ggsurvplot(
  plot_fit,
  data = records,
  conf.int = isTRUE(payload$show_confidence_interval),
  risk.table = isTRUE(payload$show_risk_table),
  pval = FALSE,
  pval.method = FALSE,
  censor = TRUE,
  xlab = time_label,
  ylab = paste(endpoint_label, "probability"),
  title = title,
  legend.title = "Expression group",
  palette = palette,
  ggtheme = plot_theme
)

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

render_png <- isTRUE(payload$render_png %||% TRUE)
render_svg <- isTRUE(payload$render_svg %||% TRUE)

if (render_png) {
  png(payload$png_path, width = 1600, height = ifelse(isTRUE(payload$show_risk_table), 1250, 950), res = 180)
  print(plot_obj)
  dev.off()
}

if (render_svg) {
  svglite(payload$svg_path, width = 10, height = ifelse(isTRUE(payload$show_risk_table), 7.8, 6.0))
  print(plot_obj)
  dev.off()
}

warnings <- list()
if (!is.null(cox_warning)) {
  warnings <- c(warnings, paste("Cox model warning:", cox_warning))
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
    cutpoint_details = payload$cutpoint_details,
    warnings = warnings,
    software_versions = software_versions
  ),
  cox_metrics
)

write_json(metrics, payload$output_path, pretty = TRUE, auto_unbox = TRUE, null = "null", digits = 16)
