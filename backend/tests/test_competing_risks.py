import json
from pathlib import Path
import shutil
import struct
import subprocess

import pytest


RSCRIPT = shutil.which("Rscript")
SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"


def r_package_available(package: str) -> bool:
    if RSCRIPT is None:
        return False
    result = subprocess.run(
        [
            RSCRIPT,
            "-e",
            f"quit(status=if (requireNamespace('{package}', quietly=TRUE)) 0 else 1)",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode == 0


CMPRSK_AVAILABLE = r_package_available("cmprsk")


def run_competing_risk_helper(
    tmp_path: Path,
    *,
    endpoint: str = "DSS",
    include_competing_events: bool = True,
    plot_aspect: str = "square",
) -> tuple[dict, Path]:
    output_path = tmp_path / f"{endpoint.lower()}-competing.json"
    plot_path = tmp_path / f"{endpoint.lower()}-cif.png"
    competing_status_recode = (
        ""
        if include_competing_events
        else "status[status == 2L] <- 0L"
    )
    r_code = f"""
        suppressPackageStartupMessages(library(jsonlite))
        suppressPackageStartupMessages(library(ggplot2))
        suppressPackageStartupMessages(library(scales))
        source({json.dumps(str(SCRIPT_DIR / "clinical_covariates.R"))})
        source({json.dumps(str(SCRIPT_DIR / "competing_risks.R"))})

        low_status <- c(rep(1L, 10), rep(2L, 20), rep(0L, 30))
        high_status <- c(rep(1L, 30), rep(2L, 10), rep(0L, 20))
        status <- c(low_status, high_status)
        {competing_status_recode}
        time_days <- c(
          seq(900, 1600, length.out = 10),
          seq(300, 1200, length.out = 20),
          seq(1700, 2300, length.out = 30),
          seq(120, 900, length.out = 30),
          seq(500, 1400, length.out = 10),
          seq(1700, 2300, length.out = 20)
        )
        group <- factor(rep(c("Low", "High"), each = 60), levels = c("Low", "High"))
        expression_value <- c(seq(-2, -0.1, length.out = 60), seq(0.1, 2, length.out = 60))
        records <- data.frame(
          patient_id = sprintf("P%03d", seq_len(120)),
          time_days = time_days,
          competing_risk_status = status,
          group = group,
          expression_value = expression_value,
          stage = rep(c("Stage I", "Stage II", "Stage III"), 40),
          grade = rep(c("G1", "G2", "G3", "G2"), 30),
          age_at_index = rep(seq(42, 78, length.out = 20), 6),
          stringsAsFactors = FALSE
        )
        result <- fit_competing_risks_analysis(
          records = records,
          continuous_records = records,
          endpoint = {json.dumps(endpoint)},
          group_levels = c("Low", "High"),
          requested_adjustment_covariates = c("age_at_index"),
          requested_external_adjustment_covariates = character(),
          external_covariate_definitions = list(),
          time_divisor = 365.25,
          time_label = "Years",
          palette = c("#2367a2", "#b33d4a"),
          plot_theme = ggplot2::theme_minimal(base_size = 11),
          output_png = {json.dumps(str(plot_path))},
          output_svg = "",
          render_png = TRUE,
          render_svg = FALSE,
          plot_aspect = {json.dumps(plot_aspect)}
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
        timeout=90,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return json.loads(output_path.read_text(encoding="utf-8")), plot_path


def png_dimensions(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", payload[16:24])


def model_by_id(models: list[dict], model_id: str) -> dict:
    return next(model for model in models if model["model"] == model_id)


@pytest.mark.skipif(
    RSCRIPT is None or not CMPRSK_AVAILABLE,
    reason="Rscript with cmprsk is not installed",
)
def test_competing_risk_contract_reports_cif_gray_and_fine_gray(
    tmp_path: Path,
) -> None:
    result, plot_path = run_competing_risk_helper(tmp_path)

    assert result["applicable"] is True
    assert result["status"] == "completed"
    assert result["coding"]["source_status_column"] == "DSS_cr"
    assert result["coding"]["status_codes"]["2"] == "death from another cause"

    cumulative = result["cumulative_incidence"]
    assert cumulative["status"] == "completed"
    assert cumulative["n_patients"] == 120
    assert cumulative["n_events_of_interest"] == 40
    assert cumulative["n_competing_events"] == 30
    assert cumulative["gray_test"]["status"] == "completed"
    assert 0 <= cumulative["gray_test"]["p_value"] <= 1
    assert cumulative["group_summary"]["Low"]["events_of_interest"] == 10
    assert cumulative["group_summary"]["High"]["events_of_interest"] == 30

    assert len(cumulative["horizons"]) == 3
    for horizon in cumulative["horizons"]:
        assert horizon["support_threshold"] == 5
        for group in ("Low", "High"):
            estimate = horizon["groups"][group]
            assert 0 <= estimate["estimate"] <= 1
            assert 0 <= estimate["conf_low"] <= estimate["conf_high"] <= 1
            assert estimate["confidence_level"] == pytest.approx(0.95)
            assert estimate["n_at_risk"] >= 0
            assert estimate["support_threshold"] == 5

    grouped = model_by_id(
        result["grouped_fine_gray_models"],
        "fine_gray_grouped_univariable",
    )
    assert grouped["status"] == "completed"
    assert grouped["marker_reference"] == "Low"
    assert grouped["marker_terms"][0]["contrast"] == "High vs Low"
    assert grouped["marker_terms"][0]["subdistribution_hazard_ratio"] > 1

    continuous = model_by_id(
        result["continuous_fine_gray_models"],
        "fine_gray_continuous_univariable",
    )
    assert continuous["status"] == "completed"
    assert continuous["marker_terms"][0]["contrast"] == "+1 SD expression"
    assert continuous["marker_terms"][0]["subdistribution_hazard_ratio"] > 1

    user_adjusted = model_by_id(
        result["continuous_fine_gray_models"],
        "fine_gray_continuous_user_adjusted",
    )
    assert user_adjusted["status"] == "completed"
    assert "age_at_index_per_10y" in user_adjusted["covariates"]

    assert plot_path.is_file()
    width, height = png_dimensions(plot_path)
    assert width == height


@pytest.mark.skipif(
    RSCRIPT is None or not CMPRSK_AVAILABLE,
    reason="Rscript with cmprsk is not installed",
)
def test_competing_risk_contract_is_explicit_when_no_competing_events_remain(
    tmp_path: Path,
) -> None:
    result, plot_path = run_competing_risk_helper(
        tmp_path,
        include_competing_events=False,
    )

    assert result["applicable"] is True
    assert result["status"] == "skipped"
    assert result["cumulative_incidence"]["status"] == "skipped"
    assert "No competing deaths" in result["cumulative_incidence"]["reason"]
    assert all(
        model["status"] == "skipped"
        for model in result["grouped_fine_gray_models"]
        + result["continuous_fine_gray_models"]
    )
    assert not plot_path.exists()


@pytest.mark.skipif(
    RSCRIPT is None or not CMPRSK_AVAILABLE,
    reason="Rscript with cmprsk is not installed",
)
def test_overall_survival_does_not_claim_a_competing_risk_estimand(
    tmp_path: Path,
) -> None:
    result, plot_path = run_competing_risk_helper(tmp_path, endpoint="OS")

    assert result == {
        "applicable": False,
        "status": "not_applicable",
        "reason": "The selected endpoint has no TCGA-CDR competing-risk status.",
    }
    assert not plot_path.exists()
