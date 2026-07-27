from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


BASE_IMAGE = (
    "rocker/r-ver@sha256:"
    "df26749182af64d5263bf64149d51a427b476ed28c4e046997143be3f97fdd7c"
)
CRAN_SNAPSHOT = "https://p3m.dev/cran/2026-07-25"
RENV_VERSION = "1.2.3"
ENGINE_FILENAMES = (
    "km_analysis.R",
    "clinical_covariates.R",
    "cox_diagnostics.R",
    "competing_risks.R",
)
CORE_RESULT_KEYS = (
    "n_patients",
    "n_events",
    "group_counts",
    "event_counts",
    "median_survival_days",
    "rmst",
    "competing_risks",
    "logrank_p_value",
    "hazard_ratio",
    "hr_conf_low",
    "hr_conf_high",
    "hr_p_value",
    "cox_models",
    "signature_interaction_cox_models",
)
REPRODUCTION_TOLERANCE_POLICY_VERSION = "tcga-trace-numeric-comparison-v1"
REPRODUCTION_TOLERANCE_POLICY = {
    "exact": {"absolute": 0.0, "relative": 0.0},
    "probability": {"absolute": 1e-12, "relative": 1e-6},
    "effect": {"absolute": 1e-8, "relative": 1e-8},
    "time": {"absolute": 1e-6, "relative": 1e-9},
    "generic": {"absolute": 1e-10, "relative": 1e-8},
}


def write_reproduction_capsule(
    analysis_dir: Path,
    *,
    r_script_path: Path,
    renv_lock_path: Path,
) -> dict[str, str]:
    analysis_dir.mkdir(parents=True, exist_ok=True)
    required = [
        analysis_dir / "input.json",
        analysis_dir / "metrics.json",
        renv_lock_path,
        *(r_script_path.parent / name for name in ENGINE_FILENAMES),
    ]
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Cannot create the reproduction capsule; missing: "
            + ", ".join(str(path) for path in missing)
        )

    copied: dict[str, Path] = {}
    for filename in ENGINE_FILENAMES:
        source = r_script_path.parent / filename
        destination = analysis_dir / filename
        if source.resolve() != destination.resolve():
            shutil.copyfile(source, destination)
        copied[f"reproduction_{Path(filename).stem}"] = destination

    lock_destination = analysis_dir / "renv.lock"
    if renv_lock_path.resolve() != lock_destination.resolve():
        shutil.copyfile(renv_lock_path, lock_destination)
    copied["reproduction_renv_lock"] = lock_destination

    runner_path = analysis_dir / "rerun_analysis.R"
    runner_path.write_text(reproduction_runner_source(), encoding="utf-8")
    copied["reproduction_r_runner"] = runner_path

    dockerfile_path = analysis_dir / "Dockerfile.reproduce"
    dockerfile_path.write_text(reproduction_dockerfile_source(), encoding="utf-8")
    copied["reproduction_dockerfile"] = dockerfile_path

    readme_path = analysis_dir / "REPRODUCE.md"
    readme_path.write_text(reproduction_readme_source(), encoding="utf-8")
    copied["reproduction_readme"] = readme_path

    manifest_path = analysis_dir / "reproduction_manifest.json"
    manifest = {
        "schema_version": "tcga-trace-reproduction-capsule-v1",
        "base_image": BASE_IMAGE,
        "cran_snapshot": CRAN_SNAPSHOT,
        "renv_version": RENV_VERSION,
        "entrypoint": "rerun_analysis.R",
        "input": "input.json",
        "expected_results": "metrics.json",
        "expected_results_integrity": (
            "Core results are bound by audit_report.json reproducibility_hash; "
            "metrics.json is excluded from this manifest to avoid a circular checksum."
        ),
        "core_result_keys": list(CORE_RESULT_KEYS),
        "numeric_comparison": {
            "policy_version": REPRODUCTION_TOLERANCE_POLICY_VERSION,
            "pass_rule": "absolute_error <= absolute + relative * max(abs(expected), abs(observed))",
            "classes": REPRODUCTION_TOLERANCE_POLICY,
        },
        "files": {},
    }
    capsule_files = {"input": analysis_dir / "input.json", **copied}
    for label, path in sorted(capsule_files.items()):
        manifest["files"][label] = {
            "filename": path.name,
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    copied["reproduction_manifest"] = manifest_path
    return {label: str(path) for label, path in copied.items()}


def reproduction_runner_source() -> str:
    core_keys = json.dumps(list(CORE_RESULT_KEYS))
    tolerance_policy = json.dumps(REPRODUCTION_TOLERANCE_POLICY)
    return f"""#!/usr/bin/env Rscript
suppressPackageStartupMessages(library(jsonlite))

`%||%` <- function(left, right) {{
  if (is.null(left) || length(left) == 0) right else left
}}

script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_path <- normalizePath(sub("^--file=", "", script_arg[[1]]))
capsule_dir <- dirname(script_path)
args <- commandArgs(trailingOnly = TRUE)
output_dir <- if (length(args) >= 1) normalizePath(args[[1]], mustWork = FALSE) else file.path(capsule_dir, "rerun_output")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

input_path <- file.path(capsule_dir, "input.json")
engine_path <- file.path(capsule_dir, "km_analysis.R")
expected_path <- file.path(capsule_dir, "metrics.json")
required <- c(input_path, engine_path, file.path(capsule_dir, "clinical_covariates.R"), file.path(capsule_dir, "cox_diagnostics.R"), file.path(capsule_dir, "competing_risks.R"))
missing <- required[!file.exists(required)]
if (length(missing)) stop("Missing reproduction files: ", paste(basename(missing), collapse = ", "))

payload <- fromJSON(input_path, simplifyVector = FALSE)
payload$output_path <- file.path(output_dir, "metrics.json")
payload$png_path <- file.path(output_dir, "plot.png")
payload$svg_path <- file.path(output_dir, "plot.svg")
payload$cox_forest_png_path <- file.path(output_dir, "cox_forest.png")
payload$cox_forest_svg_path <- file.path(output_dir, "cox_forest.svg")
payload$cox_univariable_png_path <- file.path(output_dir, "cox_univariable.png")
payload$cox_univariable_svg_path <- file.path(output_dir, "cox_univariable.svg")
payload$cox_multivariable_png_path <- file.path(output_dir, "cox_multivariable.png")
payload$cox_multivariable_svg_path <- file.path(output_dir, "cox_multivariable.svg")
payload$continuous_effect_png_path <- file.path(output_dir, "continuous_effect.png")
payload$continuous_effect_svg_path <- file.path(output_dir, "continuous_effect.svg")
payload$cumulative_incidence_png_path <- file.path(output_dir, "cumulative_incidence.png")
payload$cumulative_incidence_svg_path <- file.path(output_dir, "cumulative_incidence.svg")
payload$render_png <- FALSE
payload$render_svg <- FALSE
rerun_input <- file.path(output_dir, "input.json")
write_json(payload, rerun_input, auto_unbox = TRUE, null = "null", digits = NA)

command <- file.path(R.home("bin"), "Rscript")
process_output <- system2(command, c(shQuote(engine_path), shQuote(rerun_input)), stdout = TRUE, stderr = TRUE)
status <- attr(process_output, "status") %||% 0L
if (status != 0L || !file.exists(payload$output_path)) {{
  writeLines(process_output, file.path(output_dir, "rscript.log"))
  stop("Frozen R analysis failed with status ", status)
}}

core_keys <- fromJSON('{core_keys}')
tolerance_policy <- fromJSON('{tolerance_policy}', simplifyVector = FALSE)
observed <- fromJSON(payload$output_path, simplifyVector = FALSE)
expected <- if (file.exists(expected_path)) fromJSON(expected_path, simplifyVector = FALSE) else NULL

numeric_scalar <- function(value) {{
  is.numeric(value) && length(value) == 1L && !is.na(value)
}}

metric_class <- function(path) {{
  if (grepl("(\\\\.n_patients$|\\\\.n_events$|\\\\.parameter_count$|\\\\.group_counts\\\\.|\\\\.event_counts\\\\.|\\\\.degrees_of_freedom$)", path)) return("exact")
  if (grepl("(p_value|q_value|fdr|probability|alpha)", path, ignore.case = TRUE)) return("probability")
  if (grepl("(time|days|tau|rmst|median_survival)", path, ignore.case = TRUE)) return("time")
  if (grepl("(hazard_ratio|hr_conf|log_hr|standard_error|coefficient|estimate|expression|score|center|deviation|threshold)", path, ignore.case = TRUE)) return("effect")
  "generic"
}}

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

record_numeric_error <- function(class_name, absolute_error, relative_error, path) {{
  stats <- numeric_stats[[class_name]]
  stats$comparisons <- stats$comparisons + 1L
  if (absolute_error >= stats$max_absolute_error) {{
    stats$max_absolute_error <- absolute_error
    stats$max_absolute_path <- path
  }}
  if (relative_error >= stats$max_relative_error) {{
    stats$max_relative_error <- relative_error
    stats$max_relative_path <- path
  }}
  numeric_stats[[class_name]] <<- stats
}}

compare_values <- function(left, right, path = "$") {{
  if (is.null(left) && is.null(right)) return(character())
  if (is.list(left) && is.list(right) && !is.null(names(left)) && !is.null(names(right))) {{
    keys <- sort(unique(c(names(left), names(right))))
    return(unlist(lapply(keys, function(key) compare_values(left[[key]], right[[key]], paste0(path, ".", key))), use.names = FALSE))
  }}
  if (is.list(left) && is.list(right) && is.null(names(left)) && is.null(names(right))) {{
    if (length(left) != length(right)) return(sprintf("%s: length %d != %d", path, length(left), length(right)))
    return(unlist(lapply(seq_along(left), function(index) compare_values(left[[index]], right[[index]], sprintf("%s[%d]", path, index - 1L))), use.names = FALSE))
  }}
  if (numeric_scalar(left) && numeric_scalar(right)) {{
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
  }}
  if (identical(left, right)) return(character())
  sprintf("%s: values differ", path)
}}

differences <- character()
if (!is.null(expected)) {{
  for (key in core_keys) {{
    differences <- c(differences, compare_values(expected[[key]], observed[[key]], paste0("$.", key)))
  }}
}}
result <- list(
  schema_version = "tcga-trace-standalone-rerun-v1",
  status = if (length(differences) == 0L) "passed" else "failed",
  compared_to_expected = !is.null(expected),
  numeric_comparison = list(
    policy_version = "{REPRODUCTION_TOLERANCE_POLICY_VERSION}",
    pass_rule = "absolute_error <= absolute + relative * max(abs(expected), abs(observed))",
    classes = tolerance_policy,
    observed_errors = numeric_stats
  ),
  differences = unname(differences),
  r_version = R.version.string,
  package_versions = as.list(vapply(
    c("jsonlite", "survival", "survminer", "ggplot2", "svglite", "survRM2", "coxphf", "maxstat", "cmprsk"),
    function(package) if (requireNamespace(package, quietly = TRUE)) as.character(packageVersion(package)) else "not available",
    character(1)
  ))
)
write_json(result, file.path(output_dir, "reproduction_result.json"), auto_unbox = TRUE, pretty = TRUE)
writeLines(process_output, file.path(output_dir, "rscript.log"))
if (length(differences)) quit(status = 1L)
cat("Standalone reproduction passed\\n")
"""


def reproduction_dockerfile_source() -> str:
    return f"""FROM {BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \\
    RENV_CONFIG_REPOS_OVERRIDE={CRAN_SNAPSHOT}

RUN apt-get update && apt-get install -y --no-install-recommends \\
    cmake \\
    libcairo2-dev \\
    libcurl4-openssl-dev \\
    libfontconfig1-dev \\
    libfreetype6-dev \\
    libfribidi-dev \\
    libharfbuzz-dev \\
    libjpeg-dev \\
    libnlopt-dev \\
    libpng-dev \\
    libssl-dev \\
    libtiff5-dev \\
    libxml2-dev \\
    && rm -rf /var/lib/apt/lists/*

COPY renv.lock /opt/tcga-trace/renv.lock
RUN Rscript -e "install.packages('renv', repos='{CRAN_SNAPSHOT}'); stopifnot(as.character(packageVersion('renv')) == '{RENV_VERSION}'); renv::restore(lockfile='/opt/tcga-trace/renv.lock', library=.libPaths()[1], repos='{CRAN_SNAPSHOT}', prompt=FALSE)"

WORKDIR /analysis
CMD ["Rscript", "/analysis/rerun_analysis.R", "/output"]
"""


def reproduction_readme_source() -> str:
    return f"""# Reproduce this TCGA-TRACE analysis

This directory contains the exact patient-level R input and statistical source
used for the exported analysis. It does not require TCGA matrices, PostgreSQL,
FastAPI or the TCGA-TRACE web application.

## Docker

```sh
docker build -f Dockerfile.reproduce -t tcga-trace-rerun .
mkdir -p rerun_output
docker run --rm --network none --read-only \\
  --tmpfs /tmp:rw,noexec,nosuid,size=512m \\
  -v "$PWD:/analysis:ro" \\
  -v "$PWD/rerun_output:/output" \\
  tcga-trace-rerun
```

The base image is fixed to `{BASE_IMAGE}` and R packages are restored from
`renv.lock` using `{CRAN_SNAPSHOT}`.

## Existing R installation

With the package versions in `renv.lock` available:

```sh
Rscript rerun_analysis.R rerun_output
```

`rerun_output/reproduction_result.json` reports package versions and whether
the core outputs match `metrics.json`. Counts and categorical fields must match
exactly; floating-point outputs use the quantity-aware absolute-plus-relative
policy recorded in both `reproduction_manifest.json` and the result, including
the maximum observed error for every metric class.
"""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
