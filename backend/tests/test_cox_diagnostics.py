from pathlib import Path
import shutil
import subprocess

import pytest


RSCRIPT = shutil.which("Rscript")
HELPER = Path(__file__).resolve().parents[1] / "scripts" / "cox_diagnostics.R"


def run_r(expression: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [RSCRIPT, "-e", expression],
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(RSCRIPT is None, reason="Rscript is not installed")
def test_events_per_parameter_diagnostics_trigger_penalized_sensitivity() -> None:
    expression = f"""
library(survival)
source({str(HELPER)!r})
data <- data.frame(
  time = seq_len(20),
  event = c(rep(1, 6), rep(0, 14)),
  marker = seq_len(20),
  stage = rep(c(1, 2), 10)
)
formula <- Surv(time, event) ~ marker + stage
information <- cox_information_diagnostics(
  sum(data$event),
  cox_parameter_count(formula, data)
)
stopifnot(information$parameter_count == 2L)
stopifnot(isTRUE(all.equal(information$events_per_parameter, 3)))
stopifnot(identical(information$status, "severe"))
stopifnot(isTRUE(information$penalized_sensitivity_recommended))
stopifnot(length(information$trigger_reasons) == 1)
"""

    completed = run_r(expression)

    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(RSCRIPT is None, reason="Rscript is not installed")
def test_firth_sensitivity_returns_finite_profile_likelihood_estimate() -> None:
    availability = run_r(
        'quit(status = if (requireNamespace("coxphf", quietly = TRUE)) 0 else 3)'
    )
    if availability.returncode == 3:
        pytest.skip("coxphf is not installed")
    assert availability.returncode == 0, availability.stderr

    expression = f"""
library(survival)
source({str(HELPER)!r})
data <- data.frame(
  time = seq_len(10),
  event = c(1, 1, 1, 1, 0, 0, 0, 0, 0, 0),
  marker = c(1, 1, 1, 1, 0, 0, 0, 0, 0, 0)
)
formula <- Surv(time, event) ~ marker
information <- cox_information_diagnostics(
  sum(data$event),
  cox_parameter_count(formula, data)
)
result <- fit_firth_sensitivity(
  formula,
  data,
  information,
  term = "marker",
  effect_label = "Marker"
)
stopifnot(identical(result$status, "completed"))
stopifnot(is.finite(result$hazard_ratio))
stopifnot(is.finite(result$hr_conf_low))
stopifnot(is.finite(result$hr_conf_high))
stopifnot(result$hr_conf_low > 0)
stopifnot(result$hr_conf_high > result$hr_conf_low)
stopifnot(identical(result$confidence_interval_method, "profile penalized likelihood"))
"""

    completed = run_r(expression)

    assert completed.returncode == 0, completed.stderr
