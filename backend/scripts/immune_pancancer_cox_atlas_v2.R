suppressPackageStartupMessages({
  library(jsonlite)
  library(survival)
})

script_argument <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_directory <- if (length(script_argument)) {
  dirname(normalizePath(sub("^--file=", "", script_argument[[1]])))
} else {
  getwd()
}
source(file.path(script_directory, "clinical_covariates.R"))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1) {
  stop("Usage: Rscript immune_pancancer_cox_atlas_v2.R <input.json>")
}

payload <- fromJSON(args[[1]], simplifyVector = FALSE)

`%||%` <- function(left, right) {
  if (is.null(left) || length(left) == 0) {
    return(right)
  }
  left
}

model_specs <- list(
  list(
    model = "primary",
    label = "Primary univariable continuous Cox",
    covariates = character()
  ),
  list(
    model = "stage_adjusted",
    label = "Sensitivity adjusted for ordinal stage",
    covariates = c("stage_ordinal")
  ),
  list(
    model = "grade_adjusted",
    label = "Sensitivity adjusted for ordinal grade",
    covariates = c("grade_ordinal")
  ),
  list(
    model = "stage_grade_adjusted",
    label = "Sensitivity adjusted for ordinal stage and grade",
    covariates = c("stage_ordinal", "grade_ordinal")
  )
)

fieldnames <- c(
  "gene_symbol",
  "cohort",
  "cohort_label",
  "disease_type",
  "primary_site",
  "endpoint",
  "endpoint_label",
  "endpoint_source",
  "model",
  "model_label",
  "covariates",
  "status",
  "code",
  "reason",
  "n_patients",
  "n_events",
  "expression_mean",
  "expression_sd",
  "log_hr",
  "standard_error",
  "hazard_ratio",
  "hr_conf_low",
  "hr_conf_high",
  "p_value",
  "ph_status",
  "ph_p_value",
  "ph_global_p_value",
  "cox_warning_count",
  "cox_warnings"
)

finite_or_na <- function(value) {
  if (is.null(value) || length(value) == 0 || is.na(value) || !is.finite(value)) {
    return(NA)
  }
  unname(value)
}

base_row <- function(gene, cohort, spec) {
  list(
    gene_symbol = gene,
    cohort = cohort$cohort,
    cohort_label = cohort$cohort_label %||% cohort$cohort,
    disease_type = cohort$disease_type %||% NA,
    primary_site = cohort$primary_site %||% NA,
    endpoint = cohort$endpoint %||% NA,
    endpoint_label = cohort$endpoint_label %||% NA,
    endpoint_source = cohort$endpoint_source %||% NA,
    model = spec$model,
    model_label = spec$label,
    covariates = paste(spec$covariates, collapse = "|"),
    status = NA,
    code = NA,
    reason = NA,
    n_patients = NA,
    n_events = NA,
    expression_mean = NA,
    expression_sd = NA,
    log_hr = NA,
    standard_error = NA,
    hazard_ratio = NA,
    hr_conf_low = NA,
    hr_conf_high = NA,
    p_value = NA,
    ph_status = "not_evaluable",
    ph_p_value = NA,
    ph_global_p_value = NA,
    cox_warning_count = 0,
    cox_warnings = NA
  )
}

empty_result <- function(gene, cohort, spec, status, code, reason, model_data = NULL) {
  row <- base_row(gene, cohort, spec)
  row$status <- status
  row$code <- code
  row$reason <- reason
  if (!is.null(model_data)) {
    row$n_patients <- nrow(model_data)
    row$n_events <- sum(model_data$event == 1, na.rm = TRUE)
  }
  row
}

frame_from_rows <- function(rows) {
  do.call(
    rbind,
    lapply(rows, function(row) {
      missing <- setdiff(fieldnames, names(row))
      if (length(missing)) {
        row[missing] <- NA
      }
      as.data.frame(row[fieldnames], stringsAsFactors = FALSE, check.names = FALSE)
    })
  )
}

read_expression_row <- function(connection, row_index, sample_count) {
  offset <- as.numeric(row_index) * as.numeric(sample_count) * 4
  seek(connection, where = offset, origin = "start", rw = "read")
  readBin(
    connection,
    what = "numeric",
    n = sample_count,
    size = 4,
    endian = "little"
  )
}

fit_model <- function(gene, cohort, primary_data, spec, expression_mean, expression_sd) {
  model_data <- primary_data[
    ,
    c("time_days", "event", "expression_z", spec$covariates),
    drop = FALSE
  ]
  model_data <- model_data[complete.cases(model_data), , drop = FALSE]

  if (nrow(model_data) < payload$min_patients) {
    return(
      empty_result(
        gene,
        cohort,
        spec,
        "skipped",
        "INSUFFICIENT_COMPLETE_PATIENTS",
        sprintf(
          "Requires at least %s complete patients for this model; found %s.",
          payload$min_patients,
          nrow(model_data)
        ),
        model_data
      )
    )
  }
  model_events <- sum(model_data$event == 1, na.rm = TRUE)
  if (model_events < payload$min_events) {
    return(
      empty_result(
        gene,
        cohort,
        spec,
        "skipped",
        "INSUFFICIENT_COMPLETE_EVENTS",
        sprintf(
          "Requires at least %s complete-case events for this model; found %s.",
          payload$min_events,
          model_events
        ),
        model_data
      )
    )
  }
  for (covariate in spec$covariates) {
    observed <- model_data[[covariate]][is.finite(model_data[[covariate]])]
    if (length(unique(observed)) < 2) {
      return(
        empty_result(
          gene,
          cohort,
          spec,
          "skipped",
          "COVARIATE_NO_VARIATION",
          paste0(
            "Ordinal covariate ",
            covariate,
            " has fewer than two observed scores."
          ),
          model_data
        )
      )
    }
  }

  formula_terms <- c("expression_z", spec$covariates)
  formula <- as.formula(
    paste(
      "Surv(time_days, event) ~",
      paste(formula_terms, collapse = " + ")
    )
  )
  model_warnings <- character()
  fit <- tryCatch(
    withCallingHandlers(
      coxph(formula, data = model_data, ties = "efron"),
      warning = function(warning) {
        model_warnings <<- c(model_warnings, conditionMessage(warning))
        invokeRestart("muffleWarning")
      }
    ),
    error = function(error) error
  )
  if (inherits(fit, "error")) {
    return(
      empty_result(
        gene,
        cohort,
        spec,
        "failed",
        "COX_FAILED",
        conditionMessage(fit),
        model_data
      )
    )
  }

  cox_summary <- summary(fit)
  coefficient_names <- rownames(cox_summary$coefficients)
  row_index <- match("expression_z", coefficient_names)
  if (is.na(row_index)) {
    return(
      empty_result(
        gene,
        cohort,
        spec,
        "failed",
        "EXPRESSION_TERM_MISSING",
        "Could not isolate the standardized-expression coefficient.",
        model_data
      )
    )
  }

  coefficient <- finite_or_na(cox_summary$coefficients[row_index, "coef"])
  standard_error <- finite_or_na(
    cox_summary$coefficients[row_index, "se(coef)"]
  )
  p_value <- finite_or_na(
    cox_summary$coefficients[row_index, "Pr(>|z|)"]
  )
  hazard_ratio <- finite_or_na(cox_summary$conf.int[row_index, "exp(coef)"])
  hr_conf_low <- finite_or_na(cox_summary$conf.int[row_index, "lower .95"])
  hr_conf_high <- finite_or_na(cox_summary$conf.int[row_index, "upper .95"])
  if (
    any(
      is.na(
        c(
          coefficient,
          standard_error,
          p_value,
          hazard_ratio,
          hr_conf_low,
          hr_conf_high
        )
      )
    )
  ) {
    return(
      empty_result(
        gene,
        cohort,
        spec,
        "failed",
        "COX_NONFINITE",
        "Cox model returned non-finite standardized-expression estimates.",
        model_data
      )
    )
  }

  ph_status <- "completed"
  ph_p_value <- NA
  ph_global_p_value <- NA
  ph_test <- tryCatch(
    withCallingHandlers(
      cox.zph(fit),
      warning = function(warning) {
        model_warnings <<- c(
          model_warnings,
          paste("cox.zph warning:", conditionMessage(warning))
        )
        invokeRestart("muffleWarning")
      }
    ),
    error = function(error) error
  )
  if (inherits(ph_test, "error")) {
    ph_status <- "failed"
    model_warnings <- c(
      model_warnings,
      paste("cox.zph failed:", conditionMessage(ph_test))
    )
  } else if (!is.null(ph_test$table) && "p" %in% colnames(ph_test$table)) {
    if ("expression_z" %in% rownames(ph_test$table)) {
      ph_p_value <- finite_or_na(ph_test$table["expression_z", "p"])
    }
    if ("GLOBAL" %in% rownames(ph_test$table)) {
      ph_global_p_value <- finite_or_na(ph_test$table["GLOBAL", "p"])
    } else {
      ph_global_p_value <- ph_p_value
    }
    if (
      !is.na(ph_global_p_value)
      && is.finite(ph_global_p_value)
      && ph_global_p_value < 0.05
    ) {
      model_warnings <- c(
        model_warnings,
        "Global proportional hazards test p < 0.05; inspect time-varying effects."
      )
    }
  }

  row <- base_row(gene, cohort, spec)
  row$status <- "completed"
  row$n_patients <- nrow(model_data)
  row$n_events <- model_events
  row$expression_mean <- finite_or_na(expression_mean)
  row$expression_sd <- finite_or_na(expression_sd)
  row$log_hr <- coefficient
  row$standard_error <- standard_error
  row$hazard_ratio <- hazard_ratio
  row$hr_conf_low <- hr_conf_low
  row$hr_conf_high <- hr_conf_high
  row$p_value <- p_value
  row$ph_status <- ph_status
  row$ph_p_value <- finite_or_na(ph_p_value)
  row$ph_global_p_value <- finite_or_na(ph_global_p_value)
  row$cox_warning_count <- length(unique(model_warnings))
  row$cox_warnings <- if (length(model_warnings)) {
    paste(unique(model_warnings), collapse = " | ")
  } else {
    NA
  }
  row
}

fit_gene <- function(
  gene,
  cohort,
  records,
  barcodes,
  gene_to_row,
  matrix_connection,
  sample_count
) {
  row_index <- gene_to_row[[gene]]
  if (is.null(row_index)) {
    return(
      lapply(
        model_specs,
        function(spec) {
          empty_result(
            gene,
            cohort,
            spec,
            "skipped",
            "GENE_NOT_IN_MATRIX",
            "Gene was not present in this cohort expression matrix."
          )
        }
      )
    )
  }

  expression <- read_expression_row(
    matrix_connection,
    row_index,
    sample_count
  )
  if (length(expression) != sample_count) {
    return(
      lapply(
        model_specs,
        function(spec) {
          empty_result(
            gene,
            cohort,
            spec,
            "failed",
            "MATRIX_READ_FAILED",
            "Expression row could not be read completely."
          )
        }
      )
    )
  }
  names(expression) <- barcodes

  primary_data <- records
  primary_data$expression_value <- as.numeric(
    expression[primary_data$sample_barcode]
  )
  primary_data <- primary_data[
    complete.cases(
      primary_data[, c("time_days", "event", "expression_value")]
    ),
    ,
    drop = FALSE
  ]
  primary_data <- primary_data[
    primary_data$time_days > 0
      & primary_data$event %in% c(0, 1)
      & is.finite(primary_data$expression_value),
    ,
    drop = FALSE
  ]

  n_patients <- nrow(primary_data)
  n_events <- sum(primary_data$event == 1, na.rm = TRUE)
  if (n_patients < payload$min_patients) {
    reason <- sprintf(
      "Requires at least %s patients; found %s.",
      payload$min_patients,
      n_patients
    )
    return(
      lapply(
        model_specs,
        function(spec) {
          empty_result(
            gene,
            cohort,
            spec,
            "skipped",
            "INSUFFICIENT_PATIENTS",
            reason,
            primary_data
          )
        }
      )
    )
  }
  if (n_events < payload$min_events) {
    reason <- sprintf(
      "Requires at least %s events; found %s.",
      payload$min_events,
      n_events
    )
    return(
      lapply(
        model_specs,
        function(spec) {
          empty_result(
            gene,
            cohort,
            spec,
            "skipped",
            "NO_EVENTS",
            reason,
            primary_data
          )
        }
      )
    )
  }

  expression_mean <- mean(primary_data$expression_value, na.rm = TRUE)
  expression_sd <- sd(primary_data$expression_value, na.rm = TRUE)
  if (
    is.na(expression_sd)
    || !is.finite(expression_sd)
    || expression_sd <= 0
  ) {
    return(
      lapply(
        model_specs,
        function(spec) {
          empty_result(
            gene,
            cohort,
            spec,
            "skipped",
            "NO_EXPRESSION_VARIATION",
            "Expression has no usable variation after filters.",
            primary_data
          )
        }
      )
    )
  }

  primary_data$expression_z <- (
    primary_data$expression_value - expression_mean
  ) / expression_sd
  lapply(
    model_specs,
    function(spec) {
      fit_model(
        gene,
        cohort,
        primary_data,
        spec,
        expression_mean,
        expression_sd
      )
    }
  )
}

prepare_records <- function(records) {
  records$time_days <- as.numeric(records$time_days)
  records$event <- as.integer(records$event)
  records$stage <- trimws(as.character(records$stage))
  records$stage[is.na(records$stage) | records$stage == ""] <- NA
  records$grade <- trimws(as.character(records$grade))
  records$grade[is.na(records$grade) | records$grade == ""] <- NA
  prepared <- prepare_ordinal_covariates(records, c("stage", "grade"))
  prepared$data
}

process_cohort <- function(cohort, genes, output_dir, force) {
  output_path <- file.path(
    output_dir,
    paste0(gsub("[^A-Za-z0-9_.-]", "_", cohort$cohort), ".raw.csv")
  )
  if (
    !force
    && file.exists(output_path)
    && file.info(output_path)$size > 100
  ) {
    message("Reusing checkpoint ", cohort$cohort)
    return(output_path)
  }

  records <- tryCatch(
    read.csv(
      cohort$records_csv_path,
      stringsAsFactors = FALSE,
      check.names = FALSE
    ),
    error = function(error) error
  )
  if (inherits(records, "error") || nrow(records) == 0) {
    rows <- unlist(
      lapply(
        genes,
        function(gene) {
          lapply(
            model_specs,
            function(spec) {
              empty_result(
                gene,
                cohort,
                spec,
                "skipped",
                "NO_RECORDS",
                "No patient records passed endpoint and sample filters."
              )
            }
          )
        }
      ),
      recursive = FALSE
    )
    frame <- frame_from_rows(rows)
  } else {
    records <- prepare_records(records)
    metadata <- tryCatch(
      fromJSON(cohort$metadata_path, simplifyVector = FALSE),
      error = function(error) error
    )
    if (inherits(metadata, "error")) {
      rows <- unlist(
        lapply(
          genes,
          function(gene) {
            lapply(
              model_specs,
              function(spec) {
                empty_result(
                  gene,
                  cohort,
                  spec,
                  "failed",
                  "METADATA_READ_FAILED",
                  conditionMessage(metadata)
                )
              }
            )
          }
        ),
        recursive = FALSE
      )
      frame <- frame_from_rows(rows)
    } else {
      barcodes <- unlist(metadata$barcodes, use.names = FALSE)
      sample_count <- as.integer(metadata$sample_count)
      gene_to_row <- metadata$gene_to_row
      connection <- file(cohort$matrix_path, open = "rb")
      on.exit(close(connection), add = TRUE)
      rows <- vector("list", length(genes) * length(model_specs))
      cursor <- 1L
      for (gene in genes) {
        gene_rows <- fit_gene(
          gene,
          cohort,
          records,
          barcodes,
          gene_to_row,
          connection,
          sample_count
        )
        for (row in gene_rows) {
          rows[[cursor]] <- row
          cursor <- cursor + 1L
        }
      }
      frame <- frame_from_rows(rows)
      close(connection)
      on.exit(NULL, add = FALSE)
    }
  }

  temporary_path <- paste0(output_path, ".tmp-", Sys.getpid())
  write.table(
    frame,
    file = temporary_path,
    sep = ",",
    row.names = FALSE,
    col.names = TRUE,
    na = "",
    qmethod = "double"
  )
  if (!file.rename(temporary_path, output_path)) {
    unlink(temporary_path)
    stop("Could not publish checkpoint for ", cohort$cohort)
  }
  message(
    "Completed ",
    cohort$cohort,
    ": ",
    nrow(frame),
    " model rows"
  )
  output_path
}

output_dir <- payload$output_dir
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
genes <- vapply(
  payload$genes,
  function(item) item$gene_symbol,
  character(1)
)
cohorts <- payload$cohorts %||% list()
workers <- max(
  1L,
  min(
    as.integer(payload$workers %||% 1L),
    length(cohorts)
  )
)
force <- isTRUE(payload$force)

if (.Platform$OS.type == "unix" && workers > 1L) {
  paths <- parallel::mclapply(
    cohorts,
    function(cohort) {
      process_cohort(cohort, genes, output_dir, force)
    },
    mc.cores = workers,
    mc.preschedule = FALSE
  )
} else {
  paths <- lapply(
    cohorts,
    function(cohort) {
      process_cohort(cohort, genes, output_dir, force)
    }
  )
}

failed <- vapply(paths, inherits, logical(1), what = "try-error")
if (any(failed)) {
  stop(
    "One or more cohort workers failed: ",
    paste(
      vapply(paths[failed], as.character, character(1)),
      collapse = " | "
    )
  )
}
message(
  "Atlas model fitting complete: ",
  length(genes),
  " genes, ",
  length(cohorts),
  " cohorts, ",
  length(model_specs),
  " model families."
)
