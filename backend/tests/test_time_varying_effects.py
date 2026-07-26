import json
from pathlib import Path
import shutil
import subprocess

import pytest


RSCRIPT = shutil.which("Rscript")


def run_time_varying_helper(
    tmp_path: Path,
    *,
    ph_p_value: float,
    limited_follow_up: bool = False,
) -> dict:
    helper_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "cox_diagnostics.R"
    )
    output_path = tmp_path / (
        "limited.json" if limited_follow_up else f"result-{ph_p_value}.json"
    )
    data_generation = (
        """
        data <- data.frame(
          time_days = rep(300, 40),
          event = rep(c(1, 0), 20),
          expression_z = rep(c(-1, 1), 20)
        )
        """
        if limited_follow_up
        else """
        set.seed(20260725)
        n <- 800
        expression_z <- rep(c(-1, 1), each = n / 2)
        early_rate <- 0.0010 * exp(log(2.0) * expression_z)
        late_rate <- 0.0010 * exp(log(0.5) * expression_z)
        cumulative_draw <- -log(runif(n))
        early_hazard <- early_rate * TIME_VARYING_SPLIT_DAYS
        event_time <- ifelse(
          cumulative_draw <= early_hazard,
          cumulative_draw / early_rate,
          TIME_VARYING_SPLIT_DAYS +
            ((cumulative_draw - early_hazard) / late_rate)
        )
        censor_time <- runif(n, 1200, 3000)
        data <- data.frame(
          time_days = pmin(event_time, censor_time),
          event = as.integer(event_time <= censor_time),
          expression_z = expression_z
        )
        """
    )
    r_code = f"""
        suppressPackageStartupMessages(library(jsonlite))
        suppressPackageStartupMessages(library(survival))
        source({json.dumps(str(helper_path))})
        {data_generation}
        result <- fit_prespecified_time_varying_effect(
          data = data,
          formula_terms = c("expression_z"),
          marker_formula_term = "expression_z",
          marker_coefficient = "expression_z",
          effect_label = "Expression per +1 unit",
          ph_p_value = {ph_p_value}
        )
        write_json(
          result,
          {json.dumps(str(output_path))},
          auto_unbox = TRUE,
          null = "null",
          na = "null",
          digits = 16
        )
    """
    completed = subprocess.run(
        [RSCRIPT, "-e", r_code],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return json.loads(output_path.read_text(encoding="utf-8"))


@pytest.mark.skipif(RSCRIPT is None, reason="Rscript is not installed")
def test_time_varying_effect_recovers_prespecified_early_and_late_effects(
    tmp_path: Path,
) -> None:
    result = run_time_varying_helper(tmp_path, ph_p_value=0.01)

    assert result["status"] == "completed"
    assert result["split_days"] == pytest.approx(730.5)
    assert result["split_years"] == 2
    assert result["trigger"] == "Marker-specific cox.zph p < 0.05"
    assert "not selected" in result["split_rule"]
    assert result["support"]["early_events"] >= 5
    assert result["support"]["late_events"] >= 5
    assert result["support"]["at_risk_at_split"] >= 10
    assert result["periods"]["early"]["hazard_ratio"] > 1.4
    assert result["periods"]["late"]["hazard_ratio"] < 0.8
    assert result["change"]["hazard_ratio_ratio"] < 1


@pytest.mark.skipif(RSCRIPT is None, reason="Rscript is not installed")
def test_time_varying_effect_is_not_run_without_marker_ph_trigger(
    tmp_path: Path,
) -> None:
    result = run_time_varying_helper(tmp_path, ph_p_value=0.20)

    assert result["status"] == "not_triggered"
    assert result["trigger_alpha"] == pytest.approx(0.05)
    assert result["trigger_ph_p_value"] == pytest.approx(0.20)
    assert "not below" in result["reason"]


@pytest.mark.skipif(RSCRIPT is None, reason="Rscript is not installed")
def test_time_varying_effect_requires_support_on_both_sides_of_fixed_split(
    tmp_path: Path,
) -> None:
    result = run_time_varying_helper(
        tmp_path,
        ph_p_value=0.01,
        limited_follow_up=True,
    )

    assert result["status"] == "skipped"
    assert result["support"]["late_events"] == 0
    assert result["support"]["at_risk_at_split"] == 0
    assert "late period" in result["reason"]
    assert "entered the late period" in result["reason"]
