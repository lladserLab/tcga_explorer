import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
SignatureMethod = Literal["single", "mean", "zscore", "weighted"]
CombinedSignatureMethod = Literal["median", "tertiles"]
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


class PlotStyle(BaseModel):
    palette: list[str] = Field(default_factory=lambda: ["#2f756f", "#d7953f", "#b44b3f"])
    font_family: FontFamily = "sans"
    plot_aspect: PlotAspect = "rectangular"
    base_font_size: int = Field(default=12, ge=8, le=20)
    axis_text_size: int = Field(default=11, ge=6, le=24)
    axis_title_size: int = Field(default=12, ge=6, le=26)
    show_grid: bool = True
    show_title: bool = False
    plot_title: str | None = Field(default=None, max_length=140)

    @field_validator("palette")
    @classmethod
    def validate_palette(cls, value: list[str]) -> list[str]:
        if len(value) < 2 or len(value) > 9:
            raise ValueError("Palette must contain between 2 and 9 colors.")
        pattern = re.compile(r"^#[0-9A-Fa-f]{6}$")
        invalid = [color for color in value if not pattern.match(color)]
        if invalid:
            raise ValueError(f"Invalid hex colors: {invalid}.")
        return value


class SignatureGene(BaseModel):
    gene_symbol: str
    weight: float = 1.0


class SignatureSpec(BaseModel):
    name: str = Field(default="", max_length=48)
    gene_symbol: str
    signature_method: SignatureMethod = "zscore"
    signature_genes: list[SignatureGene] = Field(default_factory=list)


class AnalysisRequest(BaseModel):
    cohort: str
    gene_symbol: str
    signature_method: SignatureMethod = "single"
    signature_genes: list[SignatureGene] = Field(default_factory=list)
    endpoint: Endpoint = "OS"
    expression_scale: ExpressionScale = "log2_tpm"
    cutpoint_method: CutpointMethod = "median"
    custom_percentile: float | None = Field(default=None, ge=1, le=99)
    filters: AnalysisFilters = Field(default_factory=AnalysisFilters)
    time_unit: Literal["days", "months", "years"] = "days"
    show_confidence_interval: bool = True
    show_risk_table: bool = True
    plot_style: PlotStyle = Field(default_factory=PlotStyle)


class CombinedSignatureAnalysisRequest(BaseModel):
    cohort: str
    signature_a: SignatureSpec
    signature_b: SignatureSpec
    endpoint: Endpoint = "OS"
    expression_scale: ExpressionScale = "log2_tpm"
    combination_method: CombinedSignatureMethod = "median"
    filters: AnalysisFilters = Field(default_factory=AnalysisFilters)
    time_unit: Literal["days", "months", "years"] = "days"
    show_confidence_interval: bool = True
    show_risk_table: bool = True
    plot_style: PlotStyle = Field(default_factory=PlotStyle)


class AnalysisOut(BaseModel):
    id: str
    status: str
    cohort: str
    gene_symbol: str
    expression_scale: str = "log2_tpm"
    expression_scale_label: str = "log2(TPM + 1)"
    cutpoint_method: str
    metrics: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
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
    fdr: float | None = None
    ph_p_value: float | None = None
    direction: str | None = None
    effect_category: str | None = None
    significant: bool = False
    concordance: str | None = None
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
    fdr_threshold: float
    summary: dict[str, Any]
    reference: dict[str, Any] | None = None
    meta_analysis: dict[str, Any]
    results: list[PanCancerCohortResult]
    warnings: list[str] = Field(default_factory=list)
    downloads: dict[str, str] = Field(default_factory=dict)


class AnalysisBatchRequest(BaseModel):
    analyses: list[AnalysisRequest] = Field(min_length=1, max_length=100)
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


class GeneSearchOut(BaseModel):
    cohort: str
    query: str
    genes: list[str]


class ExpressionScaleOut(BaseModel):
    value: str
    label: str
    source: str
    note: str
