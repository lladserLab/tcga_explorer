import json
from pathlib import Path
import shutil
import subprocess

import pytest


RSCRIPT = shutil.which("Rscript")
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "km_analysis.R"


@pytest.mark.skipif(RSCRIPT is None, reason="Rscript is not installed")
@pytest.mark.parametrize(
    "group_levels,time_unit",
    [
        (["Low", "High"], "days"),
        (["High", "Low"], "years"),
        (["Low_Low", "Low_High", "High_Low", "High_High"], "months"),
    ],
)
def test_rendered_risk_rows_match_patient_groups(
    tmp_path: Path, group_levels: list[str], time_unit: str
) -> None:
    # Unequal group sizes and follow-up distinguish each row at every time.
    records = []
    for group_index, group in enumerate(group_levels):
        for index in range(31 + 7 * group_index):
            records.append(
                {
                    "patient_id": f"P{group_index}-{index}",
                    "group": group,
                    "expression_value": group_index + index * 0.08,
                    "time_days": 100 + ((index * 113 + group_index * 79) % 1400),
                    "event": int(index % 3 != 0),
                }
            )
    input_path = tmp_path / "input.json"
    inspection_path = tmp_path / "risk_rows.json"
    svg_path = tmp_path / "survival.svg"
    payload = {
        "cohort": "TEST",
        "gene_symbol": "TEST1",
        "endpoint": "OS",
        "records": records,
        "continuous_records": [],
        "group_levels": group_levels,
        "time_unit": time_unit,
        "show_risk_table": True,
        "show_confidence_interval": True,
        "render_png": False,
        "render_svg": True,
        "svg_path": str(svg_path),
        "output_path": str(tmp_path / "metrics.json"),
    }
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    # Inspect the production ggplot after scales have assigned visible labels
    # to rows. Reading the table's source strata alone misses this regression.
    r_code = f"""
        script <- {json.dumps(str(SCRIPT))}
        analysis <- globalenv()
        analysis$commandArgs <- function(trailingOnly = FALSE) {{
          if (trailingOnly) {json.dumps(str(input_path))}
          else paste0("--file=", script)
        }}
        sys.source(script, envir = analysis)
        built <- ggplot2::ggplot_build(analysis$plot_obj$table)
        y_axis <- built$layout$panel_params[[1]]$y
        ticks <- y_axis$scale$map(y_axis$get_breaks())
        visible_labels <- y_axis$get_labels()
        layer <- built$data[[1]]
        rows <- data.frame(
          source_group = as.character(analysis$plot_obj$table$data$strata),
          visible_group = visible_labels[match(as.numeric(layer$y), ticks)],
          time = layer$x,
          count = as.integer(layer$label)
        )
        jsonlite::write_json(rows, {json.dumps(str(inspection_path))},
                             auto_unbox = TRUE)
    """
    completed = subprocess.run(
        [RSCRIPT, "-e", r_code],
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    rows = json.loads(inspection_path.read_text(encoding="utf-8"))
    divisor = {"days": 1, "months": 30.4375, "years": 365.25}[time_unit]
    assert {row["visible_group"] for row in rows} == set(group_levels)
    for row in rows:
        assert row["visible_group"] == row["source_group"], row
        expected_count = sum(
            record["group"] == row["visible_group"]
            and record["time_days"] / divisor >= row["time"] - 0.0001
            for record in records
        )
        assert row["count"] == expected_count, row
    assert svg_path.exists()
