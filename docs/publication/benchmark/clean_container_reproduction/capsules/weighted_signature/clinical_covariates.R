normalize_clinical_text <- function(values) {
  normalized <- toupper(trimws(as.character(values)))
  normalized[is.na(values) | normalized == "" | normalized %in% c("NA", "N/A", "NULL", "NONE", "NOT REPORTED", "UNKNOWN")] <- NA_character_
  normalized
}

SUPPORTED_CLINICAL_COVARIATES <- c(
  "age_at_index",
  "stage",
  "grade",
  "gender",
  "race"
)

CLINICAL_COVARIATE_LABELS <- c(
  age_at_index = "Age",
  stage = "ordinal stage",
  grade = "ordinal grade",
  gender = "GDC gender",
  race = "GDC race"
)

encode_stage_ordinal <- function(values) {
  normalized <- normalize_clinical_text(values)
  compact <- gsub("^PATHOLOGIC\\s+", "", normalized)
  compact <- gsub("^CLINICAL\\s+", "", compact)
  compact <- gsub("^STAGE\\s*", "", compact)
  compact <- gsub("[^A-Z0-9]", "", compact)
  scores <- rep(NA_real_, length(compact))

  scores[grepl("^0", compact)] <- 0
  scores[grepl("^I", compact)] <- 1
  scores[grepl("^II", compact)] <- 2
  scores[grepl("^III", compact)] <- 3
  scores[grepl("^IV", compact)] <- 4
  scores[grepl("^1", compact)] <- 1
  scores[grepl("^2", compact)] <- 2
  scores[grepl("^3", compact)] <- 3
  scores[grepl("^4", compact)] <- 4

  scores
}

encode_grade_ordinal <- function(values) {
  normalized <- normalize_clinical_text(values)
  compact <- gsub("^HISTOLOGIC\\s+", "", normalized)
  compact <- gsub("^TUMOU?R\\s+", "", compact)
  compact <- gsub("^GRADE\\s*", "", compact)
  compact <- gsub("^G\\s*", "", compact)
  compact <- gsub("[^A-Z0-9]", "", compact)
  scores <- rep(NA_real_, length(compact))

  for (level in 1:5) {
    scores[grepl(paste0("^", level), compact)] <- level
  }

  scores
}

ordinal_covariate_metadata <- function(source, raw_values, scores) {
  normalized <- normalize_clinical_text(raw_values)
  mapped <- is.finite(scores)
  unmapped <- sort(unique(normalized[!is.na(normalized) & !mapped]))
  observed <- sort(unique(scores[mapped]))
  if (source == "stage") {
    coding <- "Major stage trend: Stage 0, I, II, III and IV map to 0, 1, 2, 3 and 4; substages A/B/C collapse to their major stage."
    unit <- "one major-stage increase"
  } else {
    coding <- "Histologic grade trend: G1 through G5 map to 1 through 5."
    unit <- "one grade increase"
  }
  list(
    source = source,
    encoded_name = paste0(source, "_ordinal"),
    type = "ordinal_numeric",
    unit = unit,
    coding = coding,
    mapped_patients = sum(mapped),
    observed_scores = as.list(observed),
    unmapped_values = as.list(unmapped)
  )
}

encode_age_per_10_years <- function(values) {
  age <- suppressWarnings(as.numeric(values))
  age[!is.finite(age) | age < 0 | age > 120] <- NA_real_
  age / 10
}

continuous_age_metadata <- function(raw_values, scores) {
  mapped <- is.finite(scores)
  observed <- scores[mapped] * 10
  list(
    source = "age_at_index",
    encoded_name = "age_at_index_per_10y",
    type = "continuous_numeric",
    unit = "10-year increase",
    coding = "Age at index is modeled continuously after division by 10; the hazard ratio is per 10-year increase.",
    mapped_patients = sum(mapped),
    observed_range_years = if (length(observed)) {
      as.list(range(observed))
    } else {
      list()
    }
  )
}

categorical_covariate_levels <- function(source) {
  if (source == "gender") {
    return(c("FEMALE", "MALE"))
  }
  if (source == "race") {
    return(c(
      "WHITE",
      "BLACK OR AFRICAN AMERICAN",
      "ASIAN",
      "AMERICAN INDIAN OR ALASKA NATIVE",
      "NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER"
    ))
  }
  character()
}

encode_categorical_covariate <- function(values, source) {
  normalized <- normalize_clinical_text(values)
  levels <- categorical_covariate_levels(source)
  normalized[!is.na(normalized) & !normalized %in% levels] <- NA_character_
  droplevels(factor(normalized, levels = levels))
}

categorical_covariate_metadata <- function(source, raw_values, encoded) {
  normalized <- normalize_clinical_text(raw_values)
  allowed <- categorical_covariate_levels(source)
  mapped <- !is.na(encoded)
  unmapped <- sort(unique(normalized[!is.na(normalized) & !normalized %in% allowed]))
  observed_levels <- levels(encoded)
  counts <- table(encoded, useNA = "no")
  list(
    source = source,
    encoded_name = paste0(source, "_factor"),
    type = "categorical_factor",
    unit = if (length(observed_levels)) {
      paste("category relative to", tolower(observed_levels[[1]]))
    } else {
      "category contrast"
    },
    coding = paste(
      "Categorical GDC field with missing, unknown and non-standard values excluded;",
      "the first observed canonical level is the treatment-contrast reference."
    ),
    mapped_patients = sum(mapped),
    observed_levels = as.list(observed_levels),
    reference_level = if (length(observed_levels)) observed_levels[[1]] else NA_character_,
    level_counts = as.list(as.integer(counts)),
    level_count_names = as.list(names(counts)),
    unmapped_values = as.list(unmapped)
  )
}

normalize_requested_covariates <- function(covariates) {
  requested <- if (is.null(covariates) || !length(covariates)) {
    character()
  } else {
    unique(as.character(unlist(covariates)))
  }
  requested <- requested[nzchar(requested)]
  unsupported <- setdiff(requested, SUPPORTED_CLINICAL_COVARIATES)
  if (length(unsupported)) {
    stop(
      "Unsupported clinical adjustment covariate(s): ",
      paste(unsupported, collapse = ", ")
    )
  }
  requested
}

prepare_model_covariates <- function(data, covariates) {
  covariates <- normalize_requested_covariates(covariates)
  encoded <- character()
  metadata <- list()
  if (!length(covariates)) {
    return(list(data = data, covariates = encoded, metadata = metadata))
  }

  for (source in covariates) {
    if (!source %in% names(data)) {
      stop("Clinical adjustment field is missing from the analysis records: ", source)
    }
    raw_values <- data[[source]]
    if (source %in% c("stage", "grade")) {
      encoded_name <- paste0(source, "_ordinal")
      scores <- if (source == "stage") {
        encode_stage_ordinal(raw_values)
      } else {
        encode_grade_ordinal(raw_values)
      }
      data[[encoded_name]] <- scores
      metadata[[encoded_name]] <- ordinal_covariate_metadata(source, raw_values, scores)
    } else if (source == "age_at_index") {
      encoded_name <- "age_at_index_per_10y"
      scores <- encode_age_per_10_years(raw_values)
      data[[encoded_name]] <- scores
      metadata[[encoded_name]] <- continuous_age_metadata(raw_values, scores)
    } else {
      encoded_name <- paste0(source, "_factor")
      factor_values <- encode_categorical_covariate(raw_values, source)
      data[[encoded_name]] <- factor_values
      metadata[[encoded_name]] <- categorical_covariate_metadata(
        source,
        raw_values,
        factor_values
      )
    }
    encoded <- c(encoded, encoded_name)
  }

  list(data = data, covariates = encoded, metadata = metadata)
}

prepare_ordinal_covariates <- function(data, covariates) {
  prepare_model_covariates(data, covariates)
}

model_covariate_has_variation <- function(values) {
  observed <- values[!is.na(values)]
  length(unique(observed)) >= 2
}

clinical_adjustment_label <- function(covariates) {
  requested <- normalize_requested_covariates(covariates)
  labels <- unname(CLINICAL_COVARIATE_LABELS[requested])
  paste(labels, collapse = " + ")
}
