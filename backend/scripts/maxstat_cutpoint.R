suppressPackageStartupMessages({
  library(jsonlite)
  library(survival)
  library(survminer)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1) {
  stop("Usage: Rscript maxstat_cutpoint.R <input.json>")
}

payload <- fromJSON(args[[1]], simplifyDataFrame = FALSE)

record_fields <- c("patient_id", "expression_value", "time_days", "event", "os_time_days", "os_event")
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
records <- records[complete.cases(records[, c("time_days", "event", "expression_value")]), ]

if (nrow(records) < 10) {
  stop("Maxstat requires at least 10 complete records.")
}
if (length(unique(records$expression_value)) < 2) {
  stop("Maxstat requires expression variation.")
}
if (sum(records$event) == 0) {
  stop("Maxstat requires at least one survival event.")
}

minprop <- if (is.null(payload$minprop) || length(payload$minprop) == 0) {
  0.15
} else {
  as.numeric(payload$minprop)
}

cutpoint <- surv_cutpoint(
  records,
  time = "time_days",
  event = "event",
  variables = "expression_value",
  minprop = minprop,
  progressbar = FALSE
)

cutpoint_table <- as.data.frame(cutpoint$cutpoint)
threshold <- unname(cutpoint_table[1, "cutpoint"])
statistic <- if ("statistic" %in% colnames(cutpoint_table)) {
  unname(cutpoint_table[1, "statistic"])
} else {
  NA
}

if (is.na(threshold)) {
  stop("Maxstat did not produce a finite cutpoint.")
}

result <- list(
  method = "maxstat",
  threshold = threshold,
  statistic = statistic,
  minprop = minprop,
  package = "survminer::surv_cutpoint"
)

write_json(result, payload$output_path, pretty = TRUE, auto_unbox = TRUE, null = "null", digits = 16)
