import re
import math
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CutpointMethod = Literal[
    "maxstat",
    "median",
    "tertiles",
    "upper_quartile",
    "upper_lower_quartile",
    "percentile",
]

FontFamily = Literal["sans", "serif", "mono"]
PlotAspect = Literal["rectangular", "square"]
CoxForestModelLayout = Literal["combined", "separate"]
SignatureMethod = Literal["single", "mean", "zscore", "weighted"]
CombinedSignatureMethod = Literal["median", "tertiles"]
ClinicalCovariate = Literal["age_at_index", "stage", "grade", "gender", "race"]
ExternalCovariateType = Literal["continuous", "categorical", "ordinal"]
Endpoint = Literal["OS", "PFI", "DFI", "DSS"]
PanCancerEndpointMode = Literal["same_endpoint", "death_like", "progression_like", "best_available"]
ExpressionScale = Literal[
    "log2_tpm",
    "log2_cpm",
    "log2_fpkm",
    "log2_fpkm_uq",
]


class CohortOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    disease_type: str | None = None
    primary_site: str | None = None
    n_samples_paired: int | None = None
    n_patients_paired: int | None = None
    n_primary_tumor: int | None = None
    n_solid_normal: int | None = None
    n_other_samples: int | None = None
    n_genes: int | None = None


class FilterOptions(BaseModel):
    sample_types: list[str]
    stages: list[str]
    grades: list[str]
    genders: list[str]
    races: list[str]
    age_min: float | None = None
    age_max: float | None = None
    os_time_max_days: float | None = None


class AnalysisFilters(BaseModel):
    sample_types: list[str] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)
    grades: list[str] = Field(default_factory=list)
    genders: list[str] = Field(default_factory=list)
    races: list[str] = Field(default_factory=list)
    age_min: float | None = None
    age_max: float | None = None
    max_time_days: float | None = None

    @field_validator("age_min", "age_max", "max_time_days", mode="before")
    @classmethod
    def empty_string_to_none(cls, value: Any) -> Any:
        return None if value == "" else value


HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
EXTERNAL_COVARIATE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
TCGA_PARTICIPANT_PATTERN = re.compile(r"^TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}$")
EXTERNAL_COVARIATE_SCHEMA_VERSION = "tcga-trace-external-covariates-v1"
MAX_EXTERNAL_COVARIATES = 10
MAX_EXTERNAL_COVARIATE_ROWS = 2_000
EXTERNAL_MISSING_TOKENS = {
    "",
    "NA",
    "N/A",
    "NULL",
    "NONE",
    "NOT AVAILABLE",
    "NOT REPORTED",
    "UNKNOWN",
}


def validate_hex_color(value: str) -> str:
    if not HEX_COLOR_PATTERN.match(value):
        raise ValueError(f"Invalid hex color: {value}.")
    return value


def normalize_optional_plot_label(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


class ContinuousPlotStyle(BaseModel):
    effect_color: str = "#1f6f8b"
    reference_color: str = "#75817e"
    show_title: bool = True
    plot_title: str | None = Field(default=None, max_length=140)
    x_axis_title: str | None = Field(default=None, max_length=100)
    y_axis_title: str | None = Field(default=None, max_length=100)

    @field_validator("effect_color", "reference_color")
    @classmethod
    def validate_colors(cls, value: str) -> str:
        return validate_hex_color(value)

    @field_validator("plot_title", "x_axis_title", "y_axis_title", mode="before")
    @classmethod
    def normalize_labels(cls, value: Any) -> str | None:
        return normalize_optional_plot_label(value)


class CoxForestPlotStyle(BaseModel):
    lower_hazard_color: str = "#1f6f8b"
    higher_hazard_color: str = "#b94d48"
    reference_color: str = "#7b8582"
    model_layout: CoxForestModelLayout = "combined"
    show_title: bool = True
    plot_title: str | None = Field(default=None, max_length=140)
    univariable_plot_title: str | None = Field(default=None, max_length=140)
    multivariable_plot_title: str | None = Field(default=None, max_length=140)
    x_axis_title: str | None = Field(default=None, max_length=100)

    @field_validator(
        "lower_hazard_color",
        "higher_hazard_color",
        "reference_color",
    )
    @classmethod
    def validate_colors(cls, value: str) -> str:
        return validate_hex_color(value)

    @field_validator(
        "plot_title",
        "univariable_plot_title",
        "multivariable_plot_title",
        "x_axis_title",
        mode="before",
    )
    @classmethod
    def normalize_labels(cls, value: Any) -> str | None:
        return normalize_optional_plot_label(value)


class PlotStyle(BaseModel):
    palette: list[str] = Field(default_factory=lambda: ["#1f6f8b", "#c8842d", "#b94d48"])
    font_family: FontFamily = "sans"
    plot_aspect: PlotAspect = "rectangular"
    base_font_size: int = Field(default=12, ge=8, le=20)
    axis_text_size: int = Field(default=11, ge=6, le=24)
    axis_title_size: int = Field(default=12, ge=6, le=26)
    show_grid: bool = False
    show_title: bool = False
    plot_title: str | None = Field(default=None, max_length=140)
    continuous: ContinuousPlotStyle = Field(default_factory=ContinuousPlotStyle)
    cox_forest: CoxForestPlotStyle = Field(default_factory=CoxForestPlotStyle)

    @field_validator("palette")
    @classmethod
    def validate_palette(cls, value: list[str]) -> list[str]:
        if len(value) < 2 or len(value) > 9:
            raise ValueError("Palette must contain between 2 and 9 colors.")
        invalid = [color for color in value if not HEX_COLOR_PATTERN.match(color)]
        if invalid:
            raise ValueError(f"Invalid hex colors: {invalid}.")
        return value

    @field_validator("plot_title", mode="before")
    @classmethod
    def normalize_title(cls, value: Any) -> str | None:
        return normalize_optional_plot_label(value)


class SignatureGene(BaseModel):
    gene_symbol: str
    weight: float = 1.0


class SignatureSpec(BaseModel):
    name: str = Field(default="", max_length=48)
    gene_symbol: str
    signature_method: SignatureMethod = "zscore"
    signature_genes: list[SignatureGene] = Field(default_factory=list)


class ExternalCovariateDefinition(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=80)
    value_type: ExternalCovariateType
    levels: list[str] = Field(default_factory=list, max_length=20)
    reference_level: str | None = Field(default=None, max_length=64)
    unit: str = Field(default="", max_length=80)
    effect_unit: float = Field(default=1.0, gt=0, le=1e12)
    description: str = Field(default="", max_length=240)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if not EXTERNAL_COVARIATE_NAME_PATTERN.fullmatch(normalized):
            raise ValueError(
                "External covariate names must begin with a letter and contain "
                "only lowercase letters, digits or underscores (maximum 32 characters)."
            )
        if normalized in {
            "patient_id",
            "sample_barcode",
            "time_days",
            "event",
            "group",
            "expression_value",
            "age_at_index",
            "stage",
            "grade",
            "gender",
            "race",
        }:
            raise ValueError(f"External covariate name is reserved: {normalized}.")
        return normalized

    @field_validator("label", "unit", "description", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("levels", mode="before")
    @classmethod
    def normalize_levels(cls, value: Any) -> list[str]:
        if value is None:
            return []
        normalized = [str(item).strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("External covariate levels cannot be empty.")
        if any(len(item) > 64 for item in normalized):
            raise ValueError(
                "External covariate levels cannot exceed 64 characters."
            )
        folded = [item.casefold() for item in normalized]
        if len(folded) != len(set(folded)):
            raise ValueError("External covariate levels must be unique ignoring case.")
        return normalized

    @field_validator("reference_level", mode="before")
    @classmethod
    def normalize_reference_level(cls, value: Any) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator("effect_unit")
    @classmethod
    def validate_effect_unit(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("External continuous effect_unit must be finite.")
        return value

    @model_validator(mode="after")
    def validate_encoding(self) -> "ExternalCovariateDefinition":
        if self.value_type == "continuous":
            if self.levels or self.reference_level is not None:
                raise ValueError(
                    "Continuous external covariates cannot declare levels or a reference level."
                )
            return self

        if len(self.levels) < 2:
            raise ValueError(
                f"{self.value_type.title()} external covariates require at least two ordered levels."
            )
        if self.value_type == "categorical":
            if self.reference_level is None:
                raise ValueError(
                    "Categorical external covariates require an explicit reference_level."
                )
            level_by_case = {level.casefold(): level for level in self.levels}
            canonical_reference = level_by_case.get(self.reference_level.casefold())
            if canonical_reference is None:
                raise ValueError(
                    "Categorical reference_level must match one of the declared levels."
                )
            self.reference_level = canonical_reference
        elif self.reference_level is not None:
            raise ValueError(
                "Ordinal external covariates use their declared level order and cannot set reference_level."
            )
        return self


class ExternalCovariateRow(BaseModel):
    patient_id: str
    values: dict[str, str | float | int | None] = Field(
        default_factory=dict,
        max_length=MAX_EXTERNAL_COVARIATES,
    )

    @field_validator("patient_id", mode="before")
    @classmethod
    def normalize_patient_id(cls, value: Any) -> str:
        normalized = str(value or "").strip().upper()
        if not TCGA_PARTICIPANT_PATTERN.fullmatch(normalized):
            raise ValueError(
                "External covariate patient_id must be an exact TCGA participant "
                "barcode such as TCGA-AB-1234."
            )
        return normalized


class ExternalCovariateDataset(BaseModel):
    schema_version: Literal["tcga-trace-external-covariates-v1"] = (
        EXTERNAL_COVARIATE_SCHEMA_VERSION
    )
    source_label: str = Field(default="", max_length=120)
    definitions: list[ExternalCovariateDefinition] = Field(
        min_length=1,
        max_length=MAX_EXTERNAL_COVARIATES,
    )
    rows: list[ExternalCovariateRow] = Field(
        min_length=1,
        max_length=MAX_EXTERNAL_COVARIATE_ROWS,
    )

    @field_validator("source_label", mode="before")
    @classmethod
    def normalize_source_label(cls, value: Any) -> str:
        return str(value or "").strip()

    @model_validator(mode="after")
    def validate_rows(self) -> "ExternalCovariateDataset":
        definitions = {definition.name: definition for definition in self.definitions}
        if len(definitions) != len(self.definitions):
            raise ValueError("External covariate definition names must be unique.")

        patient_ids = [row.patient_id for row in self.rows]
        if len(patient_ids) != len(set(patient_ids)):
            raise ValueError("External covariate rows must contain unique patient_id values.")

        for row in self.rows:
            unsupported = sorted(set(row.values) - set(definitions))
            if unsupported:
                raise ValueError(
                    "External covariate row contains undefined variable(s): "
                    + ", ".join(unsupported)
                )
            canonical_values: dict[str, str | float | None] = {}
            for name, raw_value in row.values.items():
                definition = definitions[name]
                if raw_value is None:
                    canonical_values[name] = None
                    continue
                if isinstance(raw_value, str):
                    normalized_text = raw_value.strip()
                    if normalized_text.upper() in EXTERNAL_MISSING_TOKENS:
                        canonical_values[name] = None
                        continue
                if definition.value_type == "continuous":
                    if isinstance(raw_value, bool):
                        raise ValueError(
                            f"Continuous external covariate {name} cannot contain boolean values."
                        )
                    try:
                        numeric_value = float(raw_value)
                    except (TypeError, ValueError) as exc:
                        raise ValueError(
                            f"Continuous external covariate {name} contains a non-numeric value."
                        ) from exc
                    if not math.isfinite(numeric_value):
                        raise ValueError(
                            f"Continuous external covariate {name} must contain finite values."
                        )
                    canonical_values[name] = numeric_value
                    continue

                if not isinstance(raw_value, str):
                    raise ValueError(
                        f"{definition.value_type.title()} external covariate {name} "
                        "must use string values matching its declared levels."
                    )
                level_by_case = {
                    level.casefold(): level for level in definition.levels
                }
                canonical_level = level_by_case.get(raw_value.strip().casefold())
                if canonical_level is None:
                    raise ValueError(
                        f"External covariate {name} contains undeclared level: {raw_value!r}."
                    )
                canonical_values[name] = canonical_level
            row.values = canonical_values
        return self


def validate_external_adjustment_selection(
    dataset: ExternalCovariateDataset | None,
    selected: list[str],
) -> list[str]:
    normalized = list(
        dict.fromkeys(str(value or "").strip().lower() for value in selected)
    )
    normalized = [value for value in normalized if value]
    if normalized and dataset is None:
        raise ValueError(
            "external_adjustment_covariates requires an external_covariates dataset."
        )
    available = {
        definition.name for definition in (dataset.definitions if dataset else [])
    }
    missing = sorted(set(normalized) - available)
    if missing:
        raise ValueError(
            "Selected external adjustment covariate(s) are not defined: "
            + ", ".join(missing)
        )
    return normalized


class AnalysisRequest(BaseModel):
    cohort: str
    dataset_id: str | None = Field(default=None, max_length=128)
    dataset_release_id: str | None = Field(default=None, max_length=128)
    expression_layer_id: str | None = Field(default=None, max_length=64)
    gene_symbol: str
    signature_method: SignatureMethod = "single"
    signature_genes: list[SignatureGene] = Field(default_factory=list)
    endpoint: str = Field(default="OS", min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    expression_scale: ExpressionScale = "log2_tpm"
    cutpoint_method: CutpointMethod = "median"
    custom_percentile: float | None = Field(default=None, ge=1, le=99)
    filters: AnalysisFilters = Field(default_factory=AnalysisFilters)
    adjustment_covariates: list[ClinicalCovariate] = Field(
        default_factory=list,
        max_length=5,
    )
    external_covariates: ExternalCovariateDataset | None = None
    external_adjustment_covariates: list[str] = Field(
        default_factory=list,
        max_length=MAX_EXTERNAL_COVARIATES,
    )
    time_unit: Literal["days", "months", "years"] = "days"
    show_confidence_interval: bool = True
    show_risk_table: bool = False
    plot_style: PlotStyle = Field(default_factory=PlotStyle)

    @field_validator("adjustment_covariates")
    @classmethod
    def deduplicate_adjustment_covariates(
        cls,
        value: list[ClinicalCovariate],
    ) -> list[ClinicalCovariate]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def validate_external_adjustment(self) -> "AnalysisRequest":
        if bool(self.dataset_id) != bool(self.dataset_release_id):
            raise ValueError(
                "dataset_id and dataset_release_id must be supplied together."
            )
        if self.dataset_id and self.external_covariates is not None:
            raise ValueError(
                "Per-run uploaded covariates are not supported for curated external datasets."
            )
        self.external_adjustment_covariates = validate_external_adjustment_selection(
            self.external_covariates,
            self.external_adjustment_covariates,
        )
        return self


class CombinedSignatureAnalysisRequest(BaseModel):
    cohort: str
    dataset_id: str | None = Field(default=None, max_length=128)
    dataset_release_id: str | None = Field(default=None, max_length=128)
    expression_layer_id: str | None = Field(default=None, max_length=64)
    signature_a: SignatureSpec
    signature_b: SignatureSpec
    endpoint: str = Field(default="OS", min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    expression_scale: ExpressionScale = "log2_tpm"
    combination_method: CombinedSignatureMethod = "median"
    filters: AnalysisFilters = Field(default_factory=AnalysisFilters)
    adjustment_covariates: list[ClinicalCovariate] = Field(
        default_factory=list,
        max_length=5,
    )
    external_covariates: ExternalCovariateDataset | None = None
    external_adjustment_covariates: list[str] = Field(
        default_factory=list,
        max_length=MAX_EXTERNAL_COVARIATES,
    )
    time_unit: Literal["days", "months", "years"] = "days"
    show_confidence_interval: bool = True
    show_risk_table: bool = False
    plot_style: PlotStyle = Field(default_factory=PlotStyle)

    @field_validator("adjustment_covariates")
    @classmethod
    def deduplicate_adjustment_covariates(
        cls,
        value: list[ClinicalCovariate],
    ) -> list[ClinicalCovariate]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def validate_external_adjustment(self) -> "CombinedSignatureAnalysisRequest":
        if bool(self.dataset_id) != bool(self.dataset_release_id):
            raise ValueError(
                "dataset_id and dataset_release_id must be supplied together."
            )
        if self.dataset_id and self.external_covariates is not None:
            raise ValueError(
                "Per-run uploaded covariates are not supported for curated external datasets."
            )
        self.external_adjustment_covariates = validate_external_adjustment_selection(
            self.external_covariates,
            self.external_adjustment_covariates,
        )
        return self


class AnalysisNotice(BaseModel):
    category: Literal["cohort", "method", "model", "availability"]
    severity: Literal["info", "caution", "not_evaluable"]
    code: str
    message: str
    model: str | None = None
    model_label: str | None = None
    selected_model: bool = False


class AnalysisDiagnostics(BaseModel):
    selected_adjusted_model: str | None = None
    selected_adjusted_model_label: str | None = None
    selected_adjusted_model_family: Literal["continuous", "cox", "interaction"] | None = None
    selected_adjusted_status: Literal["clean", "caution", "not_evaluable"]
    selected_model_caution_count: int = 0
    model_caution_count: int = 0
    information_count: int = 0
    not_evaluable_count: int = 0
    cohort_information_count: int = 0
    method_information_count: int = 0
    legacy_warning_count: int = 0


class AnalysisOut(BaseModel):
    id: str
    status: str
    cohort: str
    dataset_id: str | None = None
    dataset_release_id: str | None = None
    gene_symbol: str
    expression_scale: str = "log2_tpm"
    expression_scale_label: str = "log2(TPM + 1)"
    cutpoint_method: str
    metrics: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    notices: list[AnalysisNotice] = Field(default_factory=list)
    diagnostics: AnalysisDiagnostics | None = None
    error: str | None = None
    downloads: dict[str, str] = Field(default_factory=dict)
    cached: bool = False


class PanCancerSurvivalRequest(BaseModel):
    gene_symbol: str
    signature_method: SignatureMethod = "single"
    signature_genes: list[SignatureGene] = Field(default_factory=list)
    index_cohort: str | None = None
    cohorts: list[str] = Field(default_factory=list, max_length=33)
    endpoint: Endpoint = "OS"
    endpoint_mode: PanCancerEndpointMode = "same_endpoint"
    expression_scale: ExpressionScale = "log2_tpm"
    filters: AnalysisFilters = Field(default_factory=AnalysisFilters)
    min_patients: int = Field(default=10, ge=10, le=500)
    min_events: int = Field(default=5, ge=5, le=500)
    fdr_threshold: float = Field(default=0.10, gt=0, le=1)


class PanCancerCohortResult(BaseModel):
    cohort: str
    cohort_label: str | None = None
    disease_type: str | None = None
    primary_site: str | None = None
    endpoint: str | None = None
    endpoint_label: str | None = None
    endpoint_source: str | None = None
    status: str
    code: str | None = None
    reason: str | None = None
    n_patients: int | None = None
    n_events: int | None = None
    expression_mean: float | None = None
    expression_sd: float | None = None
    log_hr: float | None = None
    standard_error: float | None = None
    hazard_ratio: float | None = None
    hr_conf_low: float | None = None
    hr_conf_high: float | None = None
    p_value: float | None = None
    common_scale_log_hr: float | None = None
    common_scale_standard_error: float | None = None
    common_scale_hazard_ratio: float | None = None
    common_scale_hr_conf_low: float | None = None
    common_scale_hr_conf_high: float | None = None
    common_scale_p_value: float | None = None
    common_scale_unit: str | None = None
    common_scale_eligible: bool = False
    fdr: float | None = None
    ph_p_value: float | None = None
    ph_global_p_value: float | None = None
    time_varying_effect: dict[str, Any] | None = None
    direction: str | None = None
    effect_category: str | None = None
    significant: bool = False
    concordance: str | None = None
    cox_models: list[dict[str, Any]] = Field(default_factory=list)
    selected_adjusted_model: str | None = None
    selected_adjusted_model_label: str | None = None
    adjusted_status: str | None = None
    adjusted_reason: str | None = None
    adjusted_n_patients: int | None = None
    adjusted_n_events: int | None = None
    adjusted_log_hr: float | None = None
    adjusted_standard_error: float | None = None
    adjusted_hazard_ratio: float | None = None
    adjusted_hr_conf_low: float | None = None
    adjusted_hr_conf_high: float | None = None
    adjusted_p_value: float | None = None
    adjusted_fdr: float | None = None
    adjusted_ph_p_value: float | None = None
    adjusted_ph_global_p_value: float | None = None
    adjusted_time_varying_effect: dict[str, Any] | None = None
    adjusted_common_scale_log_hr: float | None = None
    adjusted_common_scale_standard_error: float | None = None
    adjusted_common_scale_hazard_ratio: float | None = None
    adjusted_common_scale_hr_conf_low: float | None = None
    adjusted_common_scale_hr_conf_high: float | None = None
    adjusted_common_scale_p_value: float | None = None
    adjusted_direction: str | None = None
    adjusted_effect_category: str | None = None
    adjusted_significant: bool = False
    clinical_sensitivity: str | None = None
    sample_selection: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)


class PanCancerSurvivalOut(BaseModel):
    scan_id: str
    status: str
    cached: bool = False
    gene_symbol: str
    signature: dict[str, Any] | None = None
    index_cohort: str | None = None
    endpoint: str
    endpoint_mode: str
    expression_scale: str
    expression_scale_label: str
    effect_scale: dict[str, Any] = Field(default_factory=dict)
    fdr_threshold: float
    pipeline_version: str | None = None
    data_version: dict[str, Any] = Field(default_factory=dict)
    request_snapshot: dict[str, Any] = Field(default_factory=dict)
    software_versions: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any]
    reference: dict[str, Any] | None = None
    meta_analysis: dict[str, Any]
    clinical_sensitivity: dict[str, Any] = Field(default_factory=dict)
    audit: dict[str, Any] = Field(default_factory=dict)
    results: list[PanCancerCohortResult]
    warnings: list[str] = Field(default_factory=list)
    downloads: dict[str, str] = Field(default_factory=dict)


class AnalysisBatchRequest(BaseModel):
    analyses: list[AnalysisRequest] = Field(min_length=1, max_length=100)
    max_concurrency: int | None = Field(default=None, ge=1, le=10)


class PublicAnalysisBatchRequest(BaseModel):
    analyses: list[AnalysisRequest] = Field(min_length=1, max_length=25)
    max_concurrency: int | None = Field(default=None, ge=1, le=10)


class AnalysisBatchItemOut(BaseModel):
    index: int
    status: Literal["completed", "failed"]
    result: AnalysisOut | None = None
    error: str | None = None
    code: str | None = None


class AnalysisBatchOut(BaseModel):
    total: int
    completed: int
    failed: int
    max_concurrency: int
    results: list[AnalysisBatchItemOut]


class MultiverseAnalysisRequest(BaseModel):
    cohort: str
    dataset_id: str | None = Field(default=None, max_length=128)
    dataset_release_id: str | None = Field(default=None, max_length=128)
    expression_layer_id: str | None = Field(default=None, max_length=64)
    genes: list[SignatureGene] = Field(min_length=1, max_length=50)
    signature_name: str = Field(default="", max_length=80)
    endpoints: list[str] = Field(
        default_factory=lambda: ["OS", "DSS", "PFI", "DFI"],
        min_length=1,
        max_length=8,
    )
    scoring_methods: list[SignatureMethod] = Field(
        default_factory=lambda: ["single"],
        min_length=1,
        max_length=4,
    )
    cutpoint_methods: list[CutpointMethod] = Field(
        default_factory=lambda: [
            "maxstat",
            "median",
            "upper_quartile",
            "upper_lower_quartile",
            "percentile",
        ],
        min_length=1,
        max_length=6,
    )
    expression_scale: ExpressionScale = "log2_tpm"
    custom_percentile: float = Field(default=60, ge=1, le=99)
    filters: AnalysisFilters = Field(default_factory=AnalysisFilters)
    adjustment_covariates: list[ClinicalCovariate] = Field(
        default_factory=list,
        max_length=5,
    )
    external_covariates: ExternalCovariateDataset | None = None
    external_adjustment_covariates: list[str] = Field(
        default_factory=list,
        max_length=MAX_EXTERNAL_COVARIATES,
    )
    time_unit: Literal["days", "months", "years"] = "days"
    show_confidence_interval: bool = True
    plot_style: PlotStyle = Field(default_factory=PlotStyle)
    session_label: str = Field(default="", max_length=80)

    @field_validator(
        "endpoints",
        "scoring_methods",
        "cutpoint_methods",
        "adjustment_covariates",
        "external_adjustment_covariates",
    )
    @classmethod
    def deduplicate_design_values(cls, value: list[Any]) -> list[Any]:
        return list(dict.fromkeys(value))

    @field_validator("genes")
    @classmethod
    def deduplicate_genes(cls, value: list[SignatureGene]) -> list[SignatureGene]:
        deduplicated: dict[str, SignatureGene] = {}
        for gene in value:
            symbol = gene.gene_symbol.strip().upper()
            if not symbol:
                raise ValueError("Gene symbols cannot be empty.")
            deduplicated[symbol] = SignatureGene(
                gene_symbol=symbol,
                weight=gene.weight,
            )
        return list(deduplicated.values())

    @model_validator(mode="after")
    def validate_multiverse_design(self) -> "MultiverseAnalysisRequest":
        if bool(self.dataset_id) != bool(self.dataset_release_id):
            raise ValueError(
                "dataset_id and dataset_release_id must be supplied together."
            )
        if self.dataset_id and self.external_covariates is not None:
            raise ValueError(
                "Per-run uploaded covariates are not supported for curated external datasets."
            )
        self.external_adjustment_covariates = validate_external_adjustment_selection(
            self.external_covariates,
            self.external_adjustment_covariates,
        )
        if "single" in self.scoring_methods and len(self.genes) != 1:
            raise ValueError(
                "Single-gene scoring requires exactly one gene in a multiverse."
            )
        if any(method != "single" for method in self.scoring_methods) and len(self.genes) < 2:
            raise ValueError(
                "Mean, z-score and weighted scoring require at least two genes."
            )
        planned = (
            len(self.endpoints)
            * len(self.scoring_methods)
            * len(self.cutpoint_methods)
        )
        if planned > 72:
            raise ValueError(
                "A multiverse is limited to 72 endpoint x scoring x cutpoint specifications."
            )
        return self


class MultiverseAnalysisOut(BaseModel):
    session_id: str
    dataset_id: str | None = None
    dataset_release_id: str | None = None
    expression_layer_id: str | None = None
    status: Literal["completed", "completed_with_failures"]
    pipeline_version: str
    generated_at: str
    request_snapshot: dict[str, Any]
    analysis_family: dict[str, Any]
    summary: dict[str, Any]
    continuous_references: list[dict[str, Any]]
    specifications: list[dict[str, Any]]
    execution_ledger: list[dict[str, Any]]
    warnings: list[str] = Field(default_factory=list)
    audit: dict[str, Any] = Field(default_factory=dict)
    downloads: dict[str, str] = Field(default_factory=dict)


class ExploratorySessionEntry(BaseModel):
    event_id: str = Field(
        min_length=8,
        max_length=80,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    )
    job_id: str = Field(
        min_length=32,
        max_length=64,
        pattern=r"^[A-Fa-f0-9]+$",
    )
    recorded_at: datetime
    label: str = Field(default="", max_length=160)
    source_view: str = Field(default="", max_length=40)

    @field_validator("label", "source_view", mode="before")
    @classmethod
    def normalize_session_annotation(cls, value: Any) -> str:
        return str(value or "").strip()


class ExploratorySessionExportRequest(BaseModel):
    browser_session_id: str = Field(
        min_length=12,
        max_length=80,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    )
    session_label: str = Field(default="", max_length=120)
    entries: list[ExploratorySessionEntry] = Field(
        min_length=1,
        max_length=200,
    )

    @field_validator("session_label", mode="before")
    @classmethod
    def normalize_session_label(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("entries")
    @classmethod
    def require_unique_session_events(
        cls,
        value: list[ExploratorySessionEntry],
    ) -> list[ExploratorySessionEntry]:
        event_ids = [entry.event_id for entry in value]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("Exploratory session event_id values must be unique.")
        return value


class ExploratorySessionOut(BaseModel):
    report_id: str
    status: Literal["completed", "completed_with_exclusions"]
    pipeline_version: str
    generated_at: str
    request_snapshot: dict[str, Any]
    analysis_families: dict[str, Any]
    summary: dict[str, Any]
    runs: list[dict[str, Any]]
    hypotheses: list[dict[str, Any]]
    managed_family_references: list[dict[str, Any]]
    warnings: list[str] = Field(default_factory=list)
    audit: dict[str, Any] = Field(default_factory=dict)
    downloads: dict[str, str] = Field(default_factory=dict)


class GeneSearchOut(BaseModel):
    cohort: str
    query: str
    genes: list[str]


class ExpressionScaleOut(BaseModel):
    value: str
    label: str
    source: str
    note: str


ComputeJobKind = Literal[
    "analysis",
    "combined",
    "batch",
    "multiverse",
    "pancancer",
    "session",
]
ComputeJobStatus = Literal["queued", "running", "completed", "failed", "expired"]


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ErrorOut(BaseModel):
    error: ErrorDetail


class ComputeJobOut(BaseModel):
    id: str
    kind: ComputeJobKind
    status: ComputeJobStatus
    cached: bool = False
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    status_url: str
    result_url: str | None = None
    result_id: str | None = None
    result: dict[str, Any] | None = None
    error: ErrorDetail | None = None


class PublicApiIndexOut(BaseModel):
    name: str
    app_version: str
    api_version: Literal["v1"]
    status: Literal["available"]
    description: str
    links: dict[str, str]


class PublicHealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    app_version: str
    api_version: str
    release: dict[str, str]
    pipeline_versions: dict[str, str]
    cohorts: int
    external_repository: dict[str, Any]
    cache_status: str
    data_dates: dict[str, Any]
    queue: dict[str, Any]
