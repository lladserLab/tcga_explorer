`%||cov%` <- function(left, right) {
  if (is.null(left) || length(left) == 0) {
    return(right)
  }
  left
}

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

external_covariate_definition_map <- function(definitions) {
  if (is.null(definitions) || !length(definitions)) {
    return(list())
  }
  mapped <- list()
  for (definition in definitions) {
    name <- trimws(as.character(definition$name %||cov% ""))
    if (!nzchar(name) || !grepl("^[a-z][a-z0-9_]{0,31}$", name)) {
      stop("Invalid external covariate definition name: ", name)
    }
    if (!is.null(mapped[[name]])) {
      stop("Duplicate external covariate definition: ", name)
    }
    mapped[[name]] <- definition
  }
  mapped
}

normalize_requested_external_covariates <- function(covariates, definitions) {
  requested <- if (is.null(covariates) || !length(covariates)) {
    character()
  } else {
    unique(as.character(unlist(covariates)))
  }
  requested <- requested[nzchar(requested)]
  definition_map <- external_covariate_definition_map(definitions)
  unsupported <- setdiff(requested, names(definition_map))
  if (length(unsupported)) {
    stop(
      "Undefined external adjustment covariate(s): ",
      paste(unsupported, collapse = ", ")
    )
  }
  requested
}

external_covariate_record_name <- function(name) {
  paste0("external__", name)
}

external_covariate_encoded_name <- function(name, value_type) {
  suffix <- switch(
    value_type,
    continuous = "per_unit",
    categorical = "factor",
    ordinal = "ordinal",
    stop("Unsupported external covariate type: ", value_type)
  )
  paste0("external_", name, "_", suffix)
}

external_covariate_label <- function(definition) {
  label <- trimws(as.character(definition$label %||cov% definition$name %||cov% "External covariate"))
  if (nzchar(label)) label else "External covariate"
}

prepare_external_model_covariates <- function(data, covariates, definitions) {
  requested <- normalize_requested_external_covariates(covariates, definitions)
  definition_map <- external_covariate_definition_map(definitions)
  encoded <- character()
  metadata <- list()
  if (!length(requested)) {
    return(list(data = data, covariates = encoded, metadata = metadata))
  }

  for (name in requested) {
    definition <- definition_map[[name]]
    value_type <- trimws(as.character(definition$value_type %||cov% ""))
    raw_name <- external_covariate_record_name(name)
    if (!raw_name %in% names(data)) {
      stop("External adjustment field is missing from the analysis records: ", name)
    }
    encoded_name <- external_covariate_encoded_name(name, value_type)
    raw_values <- data[[raw_name]]
    label <- external_covariate_label(definition)
    unit <- trimws(as.character(definition$unit %||cov% ""))

    if (value_type == "continuous") {
      effect_unit <- suppressWarnings(as.numeric(definition$effect_unit %||cov% 1))
      if (!is.finite(effect_unit) || effect_unit <= 0) {
        stop("External continuous covariate ", name, " has an invalid effect_unit.")
      }
      numeric_values <- suppressWarnings(as.numeric(raw_values))
      numeric_values[!is.finite(numeric_values)] <- NA_real_
      encoded_values <- numeric_values / effect_unit
      data[[encoded_name]] <- encoded_values
      observed <- numeric_values[is.finite(numeric_values)]
      metadata[[encoded_name]] <- list(
        source = name,
        label = label,
        encoded_name = encoded_name,
        type = "continuous_numeric",
        unit = if (nzchar(unit)) {
          paste0(effect_unit, " ", unit)
        } else {
          paste0(effect_unit, " raw unit(s)")
        },
        effect_unit = effect_unit,
        coding = paste0(
          "User-supplied numeric values divided by ", effect_unit,
          "; the hazard ratio is per one declared effect unit."
        ),
        mapped_patients = sum(is.finite(encoded_values)),
        missing_patients = sum(!is.finite(encoded_values)),
        observed_range = if (length(observed)) as.list(range(observed)) else list()
      )
    } else {
      declared_levels <- as.character(unlist(definition$levels %||cov% list()))
      if (length(declared_levels) < 2 ||
          any(!nzchar(declared_levels)) ||
          anyDuplicated(toupper(declared_levels))) {
        stop("External covariate ", name, " requires at least two unique declared levels.")
      }
      normalized <- trimws(as.character(raw_values))
      normalized[is.na(raw_values) | !nzchar(normalized)] <- NA_character_
      canonical <- rep(NA_character_, length(normalized))
      for (level in declared_levels) {
        canonical[
          !is.na(normalized) & toupper(normalized) == toupper(level)
        ] <- level
      }
      unmapped <- sort(unique(normalized[!is.na(normalized) & is.na(canonical)]))

      if (value_type == "categorical") {
        reference <- trimws(as.character(definition$reference_level %||cov% ""))
        reference_index <- match(toupper(reference), toupper(declared_levels))
        if (is.na(reference_index)) {
          stop("External categorical covariate ", name, " has an invalid reference level.")
        }
        canonical_levels <- c(
          declared_levels[[reference_index]],
          declared_levels[-reference_index]
        )
        encoded_values <- factor(canonical, levels = canonical_levels)
        data[[encoded_name]] <- encoded_values
        counts <- table(encoded_values, useNA = "no")
        metadata[[encoded_name]] <- list(
          source = name,
          label = label,
          encoded_name = encoded_name,
          type = "categorical_factor",
          unit = paste(
            "category relative to",
            declared_levels[[reference_index]]
          ),
          coding = "Treatment contrasts using the explicitly declared reference level.",
          mapped_patients = sum(!is.na(encoded_values)),
          missing_patients = sum(is.na(encoded_values)),
          declared_levels = as.list(declared_levels),
          observed_levels = as.list(levels(droplevels(encoded_values))),
          reference_level = declared_levels[[reference_index]],
          level_counts = as.list(as.integer(counts)),
          level_count_names = as.list(names(counts)),
          unmapped_values = as.list(unmapped)
        )
      } else if (value_type == "ordinal") {
        encoded_values <- match(canonical, declared_levels) - 1
        encoded_values[is.na(canonical)] <- NA_real_
        data[[encoded_name]] <- encoded_values
        metadata[[encoded_name]] <- list(
          source = name,
          label = label,
          encoded_name = encoded_name,
          type = "ordinal_numeric",
          unit = "one declared-level increase",
          coding = paste(
            "Ordered levels map to consecutive scores beginning at zero:",
            paste(
              paste0(
                declared_levels,
                "=",
                seq_along(declared_levels) - 1
              ),
              collapse = ", "
            )
          ),
          mapped_patients = sum(is.finite(encoded_values)),
          missing_patients = sum(!is.finite(encoded_values)),
          declared_levels = as.list(declared_levels),
          observed_scores = as.list(sort(unique(encoded_values[is.finite(encoded_values)]))),
          unmapped_values = as.list(unmapped)
        )
      } else {
        stop("Unsupported external covariate type: ", value_type)
      }
    }
    encoded <- c(encoded, encoded_name)
  }

  list(data = data, covariates = encoded, metadata = metadata)
}

prepare_model_covariates <- function(
  data,
  covariates,
  external_covariates = character(),
  external_definitions = list()
) {
  covariates <- normalize_requested_covariates(covariates)
  encoded <- character()
  metadata <- list()

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

  external <- prepare_external_model_covariates(
    data,
    external_covariates,
    external_definitions
  )
  data <- external$data
  encoded <- c(encoded, external$covariates)
  metadata <- c(metadata, external$metadata)

  list(data = data, covariates = encoded, metadata = metadata)
}

prepare_ordinal_covariates <- function(data, covariates) {
  prepare_model_covariates(data, covariates)
}

model_covariate_has_variation <- function(values) {
  observed <- values[!is.na(values)]
  length(unique(observed)) >= 2
}

clinical_adjustment_label <- function(
  covariates,
  external_covariates = character(),
  external_definitions = list()
) {
  requested <- normalize_requested_covariates(covariates)
  labels <- unname(CLINICAL_COVARIATE_LABELS[requested])
  external_requested <- normalize_requested_external_covariates(
    external_covariates,
    external_definitions
  )
  definition_map <- external_covariate_definition_map(external_definitions)
  external_labels <- vapply(
    external_requested,
    function(name) external_covariate_label(definition_map[[name]]),
    character(1)
  )
  paste(c(labels, external_labels), collapse = " + ")
}
