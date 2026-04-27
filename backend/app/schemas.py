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
SignatureMethod = Literal["single", "mean", "zscore", "weighted"]
Endpoint = Literal["OS", "PFI", "DFI", "DSS"]
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
    genders: list[str]
    races: list[str]
    age_min: float | None = None
    age_max: float | None = None
    os_time_max_days: float | None = None


class AnalysisFilters(BaseModel):
    sample_types: list[str] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)
    genders: list[str] = Field(default_factory=list)
    races: list[str] = Field(default_factory=list)
    age_min: float | None = None
    age_max: float | None = None
    max_time_days: float | None = None


class PlotStyle(BaseModel):
    palette: list[str] = Field(default_factory=lambda: ["#2f756f", "#d7953f", "#b44b3f"])
    font_family: FontFamily = "sans"
    base_font_size: int = Field(default=12, ge=8, le=20)
    axis_text_size: int = Field(default=11, ge=6, le=24)
    axis_title_size: int = Field(default=12, ge=6, le=26)
    show_grid: bool = True
    show_title: bool = False
    plot_title: str | None = Field(default=None, max_length=140)

    @field_validator("palette")
    @classmethod
    def validate_palette(cls, value: list[str]) -> list[str]:
        if len(value) < 2 or len(value) > 6:
            raise ValueError("Palette must contain between 2 and 6 colors.")
        pattern = re.compile(r"^#[0-9A-Fa-f]{6}$")
        invalid = [color for color in value if not pattern.match(color)]
        if invalid:
            raise ValueError(f"Invalid hex colors: {invalid}.")
        return value


class SignatureGene(BaseModel):
    gene_symbol: str
    weight: float = 1.0


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
