from pathlib import Path
import shutil
import subprocess

import pytest


RSCRIPT = shutil.which("Rscript")


@pytest.mark.skipif(RSCRIPT is None, reason="Rscript is not installed")
def test_stage_and_grade_are_encoded_as_ordinal_trends() -> None:
    helper = Path(__file__).resolve().parents[1] / "scripts" / "clinical_covariates.R"
    expression = f"""
source({str(helper)!r})
stopifnot(isTRUE(all.equal(
  encode_stage_ordinal(c("Stage 0", "Stage IA", "Stage IIB", "Stage IIIC", "Stage IVA", "Stage X")),
  c(0, 1, 2, 3, 4, NA_real_)
)))
stopifnot(isTRUE(all.equal(
  encode_grade_ordinal(c("G1", "G2", "G3", "G4", "GX")),
  c(1, 2, 3, 4, NA_real_)
)))
"""

    completed = subprocess.run(
        [RSCRIPT, "-e", expression],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(RSCRIPT is None, reason="Rscript is not installed")
def test_user_selected_covariates_have_explicit_deterministic_encodings() -> None:
    helper = Path(__file__).resolve().parents[1] / "scripts" / "clinical_covariates.R"
    expression = f"""
source({str(helper)!r})
data <- data.frame(
  age_at_index = c(35, 65, 130, 45),
  stage = c("Stage I", "Stage II", "Stage III", "Stage IV"),
  grade = c("G1", "G2", "G3", "G4"),
  gender = c("female", "male", "unknown", "female"),
  race = c("white", "asian", "not reported", "white"),
  stringsAsFactors = FALSE
)
prepared <- prepare_model_covariates(
  data,
  c("age_at_index", "stage", "grade", "gender", "race")
)
stopifnot(identical(
  prepared$covariates,
  c(
    "age_at_index_per_10y",
    "stage_ordinal",
    "grade_ordinal",
    "gender_factor",
    "race_factor"
  )
))
stopifnot(isTRUE(all.equal(
  prepared$data$age_at_index_per_10y,
  c(3.5, 6.5, NA_real_, 4.5)
)))
stopifnot(identical(levels(prepared$data$gender_factor), c("FEMALE", "MALE")))
stopifnot(identical(levels(prepared$data$race_factor), c("WHITE", "ASIAN")))
stopifnot(is.na(prepared$data$gender_factor[[3]]))
stopifnot(prepared$metadata$age_at_index_per_10y$unit == "10-year increase")
stopifnot(prepared$metadata$race_factor$reference_level == "WHITE")
stopifnot(model_covariate_has_variation(prepared$data$gender_factor))
"""

    completed = subprocess.run(
        [RSCRIPT, "-e", expression],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
