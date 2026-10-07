import re
import math
from datetime import datetime
from typing import Any, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.gene_symbols import canonical_gene_symbol, normalize_gene_symbol


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
PlotFrame = Literal["open", "axes", "box"]
CoxForestModelLayout = Literal["combined", "separate"]
CoxForestMultivariableDisplay = Literal["all", "selected"]
CoxForestMultivariableModel = Literal[
    "stage_adjusted",
    "grade_adjusted",
    "stage_grade_adjusted",
    "user_adjusted",
]
SignatureMethod = Literal[
    "single",
    "mean",
    "zscore",
    "weighted",
    "singscore",
    "ssgsea",
    "aucell",
]
SignatureDirection = Literal["up", "down"]
CombinedSignatureMethod = Literal["median", "tertiles"]
GseaGroupSource = Literal["clinical", "survival", "expression"]
GseaRankingMetric = Literal["welch_t", "signal_to_noise"]
GseaExpressionCutpoint = Literal[
    "median",
    "upper_quartile",
    "upper_lower_quartile",
    "percentile",
]
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
    status: str | None = None


class ClinicalGroupingLevelOut(BaseModel):
    value: str
    label: str
    count: int = Field(ge=0)
    analysis_eligible: bool = True
    unavailable_reason: str | None = None


class ClinicalGroupingNumericSummaryOut(BaseModel):
    min: float | None = None
    max: float | None = None
    median: float | None = None
    unit: str | None = None


class ClinicalGroupingReferenceOut(BaseModel):
    label: str
    doi: str | None = None
    url: str | None = None


class ClinicalGroupingProvenanceOut(BaseModel):
    origin: Literal[
        "harmonized_clinical",
        "source_reported_annotation",
        "source_reported_metadata",
        "source_reported_molecular",
        "user_declared",
        "trace_computed",
    ]
    label: str
    reported_by: str
    method_summary: str
    reference: ClinicalGroupingReferenceOut | None = None
    expression_derived: bool = False
    recomputed_by_trace: bool = False
    comparability: str


class ClinicalGroupingVariableOut(BaseModel):
    id: str
    label: str
    value_type: Literal["categorical", "numeric"]
    category: Literal[
        "standardized",
        "clinical",
        "tumor_specific",
        "dataset_specific",
    ]
    source: str
    source_field: str
    declared_source_column: str | None = None
    description: str | None = None
    catalog_version: str
    analysis_eligible: bool
    unavailable_reason: str | None = None
    patient_count: int = Field(ge=0)
    non_missing_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    coverage: float = Field(ge=0, le=1)
    levels: list[ClinicalGroupingLevelOut] = Field(default_factory=list)
    numeric_summary: ClinicalGroupingNumericSummaryOut | None = None
    expression_derived: bool = False
    timing: str | None = None
    survival_eligible: bool = True
    survival_unavailable_reason: str | None = None
    analysis_note: str | None = None
    provenance: ClinicalGroupingProvenanceOut


class FilterOptions(BaseModel):
    sample_types: list[str]
    sample_populations: list[dict[str, Any]] = Field(default_factory=list)
    selected_sample_population: dict[str, Any] | None = None
    population_selection_required: bool = False
    sample_population_metadata_conflicts: int = 0
    stages: list[str]
    grades: list[str]
    genders: list[str]
    races: list[str]
    age_min: float | None = None
    age_max: float | None = None
    os_time_max_days: float | None = None
    clinical_grouping_variables: list[ClinicalGroupingVariableOut] = Field(
        default_factory=list
    )


class CustomClinicalFilter(BaseModel):
    """A catalog-declared clinical filter applied before sample selection.

    Categorical and numeric selectors are intentionally mutually exclusive.
    Levels within one variable use OR and multiple variables use AND. The
    referenced variable remains metadata used to subset the cohort; it is never
    promoted to an automatic Cox adjustment covariate.
    """

    # Catalog IDs for external metadata fields are
    # ``metadata.<slug up to 80 chars>.<8-char digest>`` (up to 98 characters).
    variable_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$",
        description=(
            "Stable ID returned by clinical_grouping_variables in the selected "
            "dataset filter-options response."
        ),
    )
    categorical_levels: list[str] = Field(default_factory=list, max_length=30)
    numeric_min: float | None = Field(default=None, ge=-1e300, le=1e300)
    numeric_max: float | None = Field(default=None, ge=-1e300, le=1e300)

    @field_validator("variable_id", mode="before")
    @classmethod
    def normalize_custom_filter_id(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("categorical_levels", mode="before")
    @classmethod
    def normalize_custom_filter_levels(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, (list, tuple, set)):
            return value
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            if item is None:
                continue
            candidate = str(item).strip()
            key = candidate.casefold()
            if candidate and key not in seen:
                normalized.append(candidate)
                seen.add(key)
        return normalized

    @field_validator("numeric_min", "numeric_max")
    @classmethod
    def finite_custom_filter_bound(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("Custom clinical filter bounds must be finite.")
        return value

    @model_validator(mode="after")
    def validate_custom_filter_selector(self) -> "CustomClinicalFilter":
        has_levels = bool(self.categorical_levels)
        has_range = self.numeric_min is not None or self.numeric_max is not None
        if has_levels == has_range:
            raise ValueError(
                "Select either categorical_levels or a numeric_min/numeric_max range."
            )
        if (
            self.numeric_min is not None
            and self.numeric_max is not None
            and self.numeric_min > self.numeric_max
        ):
            raise ValueError(
                "Custom clinical filter numeric_min cannot exceed numeric_max."
            )
        return self


class AnalysisFilters(BaseModel):
    sample_population: Literal[
        "primary_disease",
        "primary_solid",
        "primary_blood",
        "metastatic",
        "recurrent",
        "additional_primary",
        "other_tumor",
    ] | None = None
    sample_types: list[str] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)
    grades: list[str] = Field(default_factory=list)
    genders: list[str] = Field(default_factory=list)
    races: list[str] = Field(default_factory=list)
    age_min: float | None = Field(default=None, ge=0, le=150)
    age_max: float | None = Field(default=None, ge=0, le=150)
    max_time_days: float | None = Field(
        default=None,
        gt=0,
        le=3_652_500,
    )
    custom_filters: list[CustomClinicalFilter] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "Up to 10 catalog-declared patient restrictions. Selected levels "
            "within one variable use OR; different variables use AND. These "
            "filters do not become automatic Cox covariates."
        ),
    )

    @field_validator("age_min", "age_max", "max_time_days", mode="before")
    @classmethod
    def empty_string_to_none(cls, value: Any) -> Any:
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_custom_filter_ids(self) -> "AnalysisFilters":
        for label, value in (
            ("age_min", self.age_min),
            ("age_max", self.age_max),
            ("max_time_days", self.max_time_days),
        ):
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{label} must be finite.")
        if (
            self.age_min is not None
            and self.age_max is not None
            and self.age_min > self.age_max
        ):
            raise ValueError("age_min cannot exceed age_max.")
        variable_ids = [
            item.variable_id.casefold() for item in self.custom_filters
        ]
        if len(variable_ids) != len(set(variable_ids)):
            raise ValueError(
                "Each custom clinical variable may be filtered only once."
            )
        return self


def declare_request_sample_population(
    *,
    cohort: str,
    dataset_id: str | None,
    filters: AnalysisFilters,
) -> None:
    """Persist the molecular population in every TCGA compute request."""
    if dataset_id:
        if filters.sample_population is not None:
            raise ValueError(
                "sample_population applies only to TCGA cohorts; curated and "
                "private datasets use their release-specific eligibility rule."
            )
        return
    if cohort == "TCGA-SKCM" and filters.sample_population is None:
        raise ValueError(
            "TCGA-SKCM requires an explicit sample_population: choose "
            "primary_solid or metastatic."
        )
    if filters.sample_population is None:
        filters.sample_population = "primary_disease"


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
    multivariable_display: CoxForestMultivariableDisplay = "all"
    multivariable_model_ids: list[CoxForestMultivariableModel] = Field(
        default_factory=lambda: [
            "stage_adjusted",
            "grade_adjusted",
            "stage_grade_adjusted",
            "user_adjusted",
        ],
        min_length=1,
        max_length=4,
    )
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

    @field_validator("multivariable_model_ids")
    @classmethod
    def unique_multivariable_models(
        cls,
        value: list[CoxForestMultivariableModel],
    ) -> list[CoxForestMultivariableModel]:
        return list(dict.fromkeys(value))


class PlotStyle(BaseModel):
    palette: list[str] = Field(default_factory=lambda: ["#1f6f8b", "#c8842d", "#b94d48"])
    font_family: FontFamily = "sans"
    plot_aspect: PlotAspect = "rectangular"
    base_font_size: int = Field(default=12, ge=8, le=20)
    axis_text_size: int = Field(default=11, ge=6, le=24)
    axis_text_bold: bool = False
    axis_text_italic: bool = False
    axis_title_size: int = Field(default=12, ge=6, le=26)
    axis_title_bold: bool = False
    axis_title_italic: bool = False
    plot_frame: PlotFrame = "open"
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
    direction: SignatureDirection | None = None

    @field_validator("gene_symbol", mode="before")
    @classmethod
    def normalize_signature_gene_symbol(cls, value: Any) -> str:
        symbol = str(value or "").strip()
        if not symbol:
            raise ValueError("Signature gene symbols cannot be empty.")
        return symbol

    @field_validator("weight")
    @classmethod
    def validate_weight(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Signature gene weights must be finite.")
        if value == 0:
            raise ValueError(
                "Signature gene weights cannot be zero; remove the gene instead."
            )
        return value


class SignatureSpec(BaseModel):
    name: str = Field(default="", max_length=48)
    gene_symbol: str
    signature_method: SignatureMethod = "zscore"
    signature_genes: list[SignatureGene] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scoring_contract(self) -> "SignatureSpec":
        genes = signature_spec_components(self)
        if self.signature_method == "single" and len(genes) != 1:
            raise ValueError("Single-gene scoring requires exactly one gene.")
        if self.signature_method != "single" and len(genes) < 2:
            raise ValueError(
                "Multi-gene signature scoring requires at least two genes."
            )
        validate_signature_scoring_contract(
            method=self.signature_method,
            genes=genes,
        )
        return self


RANK_BASED_SIGNATURE_METHODS = frozenset(
    {"singscore", "ssgsea", "aucell"}
)


def signature_spec_components(signature: SignatureSpec) -> list[SignatureGene]:
    return signature_components_from_fields(
        method=signature.signature_method,
        gene_symbol=signature.gene_symbol,
        signature_genes=signature.signature_genes,
    )


def signature_components_from_fields(
    *,
    method: SignatureMethod,
    gene_symbol: str,
    signature_genes: list[SignatureGene],
) -> list[SignatureGene]:
    if signature_genes:
        return list(signature_genes)
    raw = gene_symbol.replace(";", ",").replace("+", ",")
    components: list[SignatureGene] = []
    for raw_token in raw.split(","):
        token = raw_token.strip()
        if not token:
            continue
        symbol = token
        weight = 1.0
        direction = None
        if method in RANK_BASED_SIGNATURE_METHODS and ":" in token:
            symbol, raw_direction = token.rsplit(":", 1)
            normalized_direction = raw_direction.strip().casefold()
            direction_aliases = {
                "up": "up",
                "down": "down",
                "1": "up",
                "1.0": "up",
                "-1": "down",
                "-1.0": "down",
            }
            if normalized_direction not in direction_aliases:
                raise ValueError(
                    "Rank-based gene strings use GENE:1 or GENE:-1 "
                    "(GENE:up and GENE:down are also accepted)."
                )
            direction = direction_aliases[normalized_direction]
            weight = -1.0 if direction == "down" else 1.0
        elif method in {"weighted", "zscore"} and ":" in token:
            symbol, raw_weight = token.rsplit(":", 1)
            try:
                weight = float(raw_weight.strip())
            except ValueError as exc:
                raise ValueError(
                    f"Signature gene {symbol.strip()} has an invalid weight."
                ) from exc
        elif ":" in token:
            raise ValueError(
                f"{method} scoring does not accept weighted or directional "
                "gene tokens."
            )
        components.append(
            SignatureGene(
                gene_symbol=symbol.strip(),
                weight=weight,
                direction=direction,
            )
        )
    return components


def validate_signature_scoring_contract(
    *,
    method: SignatureMethod,
    genes: list[SignatureGene],
) -> None:
    """Reject signature inputs whose meaning would otherwise be ambiguous.

    The rank-based engines support signed up/down membership, not arbitrary
    coefficient magnitudes.  A negative unit weight remains a backwards-
    compatible shorthand for ``direction="down"``; when present, the explicit
    direction is authoritative.
    """

    if method not in RANK_BASED_SIGNATURE_METHODS:
        if any(gene.direction is not None for gene in genes):
            raise ValueError(
                "Explicit up/down direction is available only for singscore, "
                "ssGSEA and AUCell signatures."
            )
        if method in {"single", "mean"} and any(
            not math.isclose(float(gene.weight), 1.0) for gene in genes
        ):
            raise ValueError(
                f"{method} scoring does not use gene weights; remove the "
                "coefficient values or choose Z-score or Weighted scoring."
            )
        return
    for gene in genes:
        if not math.isclose(abs(float(gene.weight)), 1.0):
            raise ValueError(
                f"{method} uses signed gene membership, not coefficient "
                "magnitudes; every weight must be +1 or -1."
            )
    if method == "ssgsea":
        direction_counts = {"up": 0, "down": 0}
        for gene in genes:
            direction = gene.direction or (
                "down" if gene.weight < 0 else "up"
            )
            direction_counts[direction] += 1
        undersized = [
            direction
            for direction, count in direction_counts.items()
            if 0 < count < 2
        ]
        if undersized:
            raise ValueError(
                "ssGSEA requires at least two genes in each non-empty "
                "directional component; undersized component(s): "
                + ", ".join(undersized)
                + "."
            )


def signature_genes_for_method(
    genes: list[SignatureGene],
    method: SignatureMethod,
) -> list[SignatureGene]:
    """Project a shared gene declaration onto one scoring-method contract."""

    projected: list[SignatureGene] = []
    for gene in genes:
        if method in RANK_BASED_SIGNATURE_METHODS:
            projected.append(gene.model_copy(deep=True))
            continue
        if method in {"zscore", "weighted"}:
            direction = gene.direction or (
                "down" if gene.weight < 0 else "up"
            )
            sign = -1.0 if direction == "down" else 1.0
            projected.append(
                SignatureGene(
                    gene_symbol=gene.gene_symbol,
                    weight=sign * abs(float(gene.weight)),
                )
            )
            continue
        projected.append(
            SignatureGene(gene_symbol=gene.gene_symbol, weight=1.0)
        )
    return projected


class GseaGroupingDefinition(BaseModel):
    source: GseaGroupSource
    group_a_label: str = Field(default="Group A", min_length=1, max_length=64)
    group_b_label: str = Field(default="Group B", min_length=1, max_length=64)
    clinical_variable: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$",
    )
    group_a_values: list[str] = Field(default_factory=list, max_length=30)
    group_b_values: list[str] = Field(default_factory=list, max_length=30)
    clinical_cutpoint_method: Literal["median", "value"] = "median"
    clinical_cutpoint: float | None = Field(
        default=None,
        ge=-1e12,
        le=1e12,
    )
    survival_analysis_id: str | None = Field(default=None, max_length=64)
    signature: SignatureSpec | None = None
    cutpoint_method: GseaExpressionCutpoint = "median"
    custom_percentile: float | None = Field(default=None, ge=1, le=99)

    @field_validator(
        "group_a_label",
        "group_b_label",
        "survival_analysis_id",
        mode="before",
    )
    @classmethod
    def normalize_grouping_text(cls, value: Any) -> Any:
        if value is None:
            return None
        return str(value).strip()

    @field_validator("group_a_values", "group_b_values", mode="before")
    @classmethod
    def normalize_grouping_values(cls, value: Any) -> list[str]:
        if value is None:
            return []
        normalized = [str(item).strip() for item in value if str(item).strip()]
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def validate_grouping_source(self) -> "GseaGroupingDefinition":
        if self.group_a_label.casefold() == self.group_b_label.casefold():
            raise ValueError("GSEA group labels must be distinct.")

        if self.source == "clinical":
            if self.clinical_variable is None:
                raise ValueError("Clinical grouping requires clinical_variable.")
            has_categorical_values = bool(
                self.group_a_values or self.group_b_values
            )
            if not has_categorical_values:
                if (
                    self.clinical_cutpoint_method == "value"
                    and self.clinical_cutpoint is None
                ):
                    raise ValueError(
                        "Numeric clinical grouping with a fixed value requires "
                        "clinical_cutpoint."
                    )
            else:
                if not self.group_a_values or not self.group_b_values:
                    raise ValueError(
                        "Categorical clinical grouping requires values for both groups."
                    )
                overlap = {
                    item.casefold() for item in self.group_a_values
                } & {
                    item.casefold() for item in self.group_b_values
                }
                if overlap:
                    raise ValueError(
                        "Clinical group value selections must not overlap."
                    )
            return self

        if self.source == "survival":
            if not self.survival_analysis_id:
                raise ValueError(
                    "Survival grouping requires survival_analysis_id."
                )
            if bool(self.group_a_values) != bool(self.group_b_values):
                raise ValueError(
                    "Select both inherited survival group values together."
                )
            if len(self.group_a_values) > 1 or len(self.group_b_values) > 1:
                raise ValueError(
                    "Survival grouping accepts one source value per group."
                )
            if (
                self.group_a_values
                and self.group_a_values[0].casefold()
                == self.group_b_values[0].casefold()
            ):
                raise ValueError(
                    "Inherited survival group values must be distinct."
                )
            return self

        if self.signature is None:
            raise ValueError("Expression grouping requires a gene or signature.")
        if not self.signature.gene_symbol.strip() and not self.signature.signature_genes:
            raise ValueError("Expression grouping requires at least one gene.")
        signature_gene_count = (
            len(
                [
                    item
                    for item in self.signature.signature_genes
                    if item.gene_symbol.strip()
                ]
            )
            if self.signature.signature_genes
            else len(
                [
                    item
                    for item in (
                        self.signature.gene_symbol.replace(";", ",")
                        .replace("+", ",")
                        .split(",")
                    )
                    if item.strip()
                ]
            )
        )
        if (
            self.signature.signature_method == "single"
            and signature_gene_count != 1
        ):
            raise ValueError(
                "Single-gene GSEA grouping requires exactly one gene."
            )
        if (
            self.cutpoint_method == "percentile"
            and self.custom_percentile is None
        ):
            raise ValueError(
                "Percentile expression grouping requires custom_percentile."
            )
        return self


class GseaAnalysisRequest(BaseModel):
    cohort: str = Field(min_length=1, max_length=16)
    dataset_id: str | None = Field(default=None, max_length=128)
    dataset_release_id: str | None = Field(default=None, max_length=128)
    expression_layer_id: str | None = Field(default=None, max_length=64)
    expression_scale: ExpressionScale = "log2_tpm"
    filters: AnalysisFilters = Field(default_factory=AnalysisFilters)
    grouping: GseaGroupingDefinition
    gene_set_collection: str = Field(
        default="immport",
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    )
    ranking_metric: GseaRankingMetric = "welch_t"
    min_gene_set_size: int = Field(default=15, ge=5, le=500)
    max_gene_set_size: int = Field(default=500, ge=10, le=5_000)
    permutations: int = Field(default=1_000, ge=100, le=5_000)
    seed: int = Field(default=17_291, ge=0, le=2_147_483_647)
    fdr_threshold: float = Field(default=0.25, gt=0, le=1)

    @model_validator(mode="after")
    def validate_gsea_request(self) -> "GseaAnalysisRequest":
        if bool(self.dataset_id) != bool(self.dataset_release_id):
            raise ValueError(
                "dataset_id and dataset_release_id must be supplied together."
            )
        if self.min_gene_set_size > self.max_gene_set_size:
            raise ValueError(
                "min_gene_set_size cannot exceed max_gene_set_size."
            )
        if (
            self.grouping.source == "clinical"
            and self.grouping.clinical_variable
            and any(
                item.variable_id.casefold()
                == self.grouping.clinical_variable.casefold()
                for item in self.filters.custom_filters
            )
        ):
            raise ValueError(
                "A clinical variable cannot define the groups and restrict "
                "eligibility at the same time."
            )
        declare_request_sample_population(
            cohort=self.cohort,
            dataset_id=self.dataset_id,
            filters=self.filters,
        )
        return self


class ExpressionComparisonRequest(BaseModel):
    """Compare up to 25 genes across one traceable, binary GSEA grouping."""

    cohort: str = Field(min_length=1, max_length=16)
    dataset_id: str | None = Field(default=None, max_length=128)
    dataset_release_id: str | None = Field(default=None, max_length=128)
    expression_layer_id: str | None = Field(default=None, max_length=64)
    expression_scale: ExpressionScale = "log2_tpm"
    filters: AnalysisFilters = Field(default_factory=AnalysisFilters)
    genes: list[str] = Field(min_length=1, max_length=25)
    grouping: GseaGroupingDefinition
    fdr_threshold: float = Field(default=0.05, gt=0, le=1)
    heatmap_max_samples: int = Field(default=300, ge=20, le=500)

    @field_validator("genes", mode="before")
    @classmethod
    def normalize_genes(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            return value
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in value:
            symbol = str(raw or "").strip().upper()
            if not symbol:
                raise ValueError("Gene symbols must not be empty.")
            if len(symbol) > 128:
                raise ValueError("Gene symbols must not exceed 128 characters.")
            if symbol not in seen:
                seen.add(symbol)
                normalized.append(symbol)
        return normalized

    @model_validator(mode="after")
    def validate_expression_comparison_request(
        self,
    ) -> "ExpressionComparisonRequest":
        if bool(self.dataset_id) != bool(self.dataset_release_id):
            raise ValueError(
                "dataset_id and dataset_release_id must be supplied together."
            )
        if (
            self.grouping.source == "clinical"
            and self.grouping.clinical_variable
            and any(
                item.variable_id.casefold()
                == self.grouping.clinical_variable.casefold()
                for item in self.filters.custom_filters
            )
        ):
            raise ValueError(
                "A clinical variable cannot define the groups and restrict "
                "eligibility at the same time."
            )
        declare_request_sample_population(
            cohort=self.cohort,
            dataset_id=self.dataset_id,
            filters=self.filters,
        )
        return self


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
        signature_entries = [
            item.gene_symbol.strip()
            for item in self.signature_genes
            if item.gene_symbol.strip()
        ]
        raw_entries = [
            item.strip()
            for item in self.gene_symbol.replace(";", ",").replace("+", ",").split(",")
            if item.strip()
        ]
        gene_count = len(signature_entries or raw_entries)
        if self.signature_method == "single" and gene_count != 1:
            raise ValueError("Single-gene analysis requires exactly one gene.")
        if self.signature_method != "single" and gene_count < 2:
            raise ValueError(
                "Multi-gene signature scoring requires at least two genes."
            )
        validate_signature_scoring_contract(
            method=self.signature_method,
            genes=signature_components_from_fields(
                method=self.signature_method,
                gene_symbol=self.gene_symbol,
                signature_genes=self.signature_genes,
            ),
        )
        if self.cutpoint_method == "percentile" and self.custom_percentile is None:
            raise ValueError(
                "Percentile grouping requires custom_percentile from 1 through 99."
            )
        self.external_adjustment_covariates = validate_external_adjustment_selection(
            self.external_covariates,
            self.external_adjustment_covariates,
        )
        declare_request_sample_population(
            cohort=self.cohort,
            dataset_id=self.dataset_id,
            filters=self.filters,
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
        declare_request_sample_population(
            cohort=self.cohort,
            dataset_id=self.dataset_id,
            filters=self.filters,
        )
        return self


class SignaturePanelAnalysisRequest(BaseModel):
    cohort: str
    dataset_id: str | None = Field(default=None, max_length=128)
    dataset_release_id: str | None = Field(default=None, max_length=128)
    expression_layer_id: str | None = Field(default=None, max_length=64)
    panel_name: str | None = Field(default=None, max_length=80)
    signatures: list[SignatureSpec] = Field(min_length=2, max_length=6)
    endpoint: str = Field(
        default="OS",
        min_length=1,
        max_length=32,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    expression_scale: ExpressionScale = "log2_tpm"
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
    plot_style: PlotStyle = Field(default_factory=PlotStyle)

    @field_validator("panel_name", mode="before")
    @classmethod
    def normalize_panel_name(cls, value: Any) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator("adjustment_covariates")
    @classmethod
    def deduplicate_adjustment_covariates(
        cls,
        value: list[ClinicalCovariate],
    ) -> list[ClinicalCovariate]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def validate_panel(self) -> "SignaturePanelAnalysisRequest":
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
        declare_request_sample_population(
            cohort=self.cohort,
            dataset_id=self.dataset_id,
            filters=self.filters,
        )

        names = [signature.name.strip() for signature in self.signatures]
        if any(not name for name in names):
            raise ValueError("Every panel signature requires a non-empty name.")
        folded_names = [name.casefold() for name in names]
        if len(folded_names) != len(set(folded_names)):
            raise ValueError(
                "Panel signature names must be unique ignoring case."
            )
        for signature in self.signatures:
            if signature.signature_method != "single":
                continue
            single_genes = (
                [
                    item
                    for item in signature.signature_genes
                    if item.gene_symbol.strip()
                ]
                if signature.signature_genes
                else [
                    item
                    for item in (
                        signature.gene_symbol.replace(";", ",")
                        .replace("+", ",")
                        .split(",")
                    )
                    if item.strip()
                ]
            )
            if len(single_genes) != 1:
                raise ValueError(
                    f"Panel signature {signature.name.strip()} in single "
                    "mode requires exactly one gene."
                )

        definitions = [
            signature_definition_key(signature)
            for signature in self.signatures
        ]
        if len(definitions) != len(set(definitions)):
            raise ValueError(
                "The panel contains duplicate signature definitions."
            )
        return self


def signature_definition_key(signature: SignatureSpec) -> tuple:
    genes = []
    for component in signature_spec_components(signature):
        if signature.signature_method in RANK_BASED_SIGNATURE_METHODS:
            value: float | str = component.direction or (
                "down" if component.weight < 0 else "up"
            )
        elif signature.signature_method in {"zscore", "weighted"}:
            value = float(component.weight)
        else:
            value = 1.0
        genes.append((component.gene_symbol.strip().upper(), value))
    if not genes:
        raise ValueError(
            f"Signature {signature.name.strip() or '<unnamed>'} requires at least one gene."
        )
    if signature.signature_method == "single":
        genes = genes[:1]
    else:
        genes = sorted(genes)
    return (signature.signature_method, tuple(genes))


class AnalysisNotice(BaseModel):
    category: Literal["cohort", "method", "model", "availability"]
    severity: Literal["info", "caution", "not_evaluable", "error"]
    scope: Literal["primary", "requested_adjustment", "auxiliary", "context"] = "context"
    priority: Literal["high", "medium", "low"] = "low"
    code: str
    message: str
    model: str | None = None
    model_label: str | None = None
    selected_model: bool = False


class AnalysisDiagnostics(BaseModel):
    primary_result_model: str | None = None
    primary_result_model_label: str | None = None
    primary_result_model_family: Literal[
        "continuous",
        "cox",
        "interaction",
        "signature_panel",
    ] | None = None
    primary_result_status: Literal["clean", "caution", "not_evaluable"]
    selected_adjusted_model: str | None = None
    selected_adjusted_model_label: str | None = None
    selected_adjusted_model_family: Literal[
        "continuous",
        "cox",
        "interaction",
        "signature_panel",
    ] | None = None
    selected_adjusted_status: Literal[
        "clean",
        "caution",
        "not_evaluable",
        "not_requested",
    ]
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

    @model_validator(mode="after")
    def declare_primary_disease_population(self) -> "PanCancerSurvivalRequest":
        components = signature_components_from_fields(
            method=self.signature_method,
            gene_symbol=self.gene_symbol,
            signature_genes=self.signature_genes,
        )
        if self.signature_method == "single" and len(components) != 1:
            raise ValueError("Single-gene scoring requires exactly one gene.")
        if self.signature_method != "single" and len(components) < 2:
            raise ValueError(
                "Multi-gene signature scoring requires at least two genes."
            )
        validate_signature_scoring_contract(
            method=self.signature_method,
            genes=components,
        )
        if self.filters.sample_population is None:
            self.filters.sample_population = "primary_disease"
        return self


class HierarchicalPanCancerRequest(BaseModel):
    """Combine comparable study effects without pooling expression matrices."""

    gene_symbol: str = Field(min_length=1, max_length=128)
    # These values are available to the synchronous preflight provenance
    # contract but excluded from the canonical estimand dump. Artifact identity
    # adds them explicitly so alias and canonical queries cannot overwrite one
    # another's audit trail.
    requested_gene_symbol: str = Field(default="", exclude=True, repr=False)
    resolved_gene_symbol: str = Field(default="", exclude=True, repr=False)
    scope: Literal["combined", "tcga_only", "external_only"] = "combined"
    cancers: list[str] = Field(default_factory=list, max_length=128)
    study_ids: list[str] = Field(default_factory=list, max_length=200)
    endpoint: Literal["OS"] = "OS"
    clinical_context: Literal[
        "primary_baseline",
        "advanced_treatment",
        "advanced_diagnostic",
        "hematologic_diagnostic",
        "hematologic_treatment",
    ] = "primary_baseline"
    time_origin_policy: Literal["strict_baseline"] = "strict_baseline"
    effect_scale: Literal["within_study_iqr"] = "within_study_iqr"
    overlap_policy: Literal["independent_clusters"] = "independent_clusters"
    min_patients: int = Field(default=20, ge=20, le=500)
    min_events: int = Field(default=10, ge=10, le=500)
    min_censored: int = Field(default=5, ge=5, le=500)
    include_exploratory: bool = False
    fdr_threshold: float = Field(default=0.05, gt=0, le=1)

    @model_validator(mode="before")
    @classmethod
    def normalize_hierarchical_gene(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        requested = normalize_gene_symbol(value.get("gene_symbol"))
        if not requested:
            raise ValueError("A gene symbol is required.")
        resolved = canonical_gene_symbol(requested)
        payload = dict(value)
        payload["gene_symbol"] = resolved
        # Ignore caller-supplied provenance fields.  They are always derived
        # from the actual query accepted at this validation boundary.
        payload["requested_gene_symbol"] = requested
        payload["resolved_gene_symbol"] = resolved
        return payload

    @property
    def gene_resolution(self) -> dict[str, str]:
        return {
            "requested_gene_symbol": self.requested_gene_symbol,
            "resolved_gene_symbol": self.resolved_gene_symbol,
            "resolution": (
                "exact"
                if self.requested_gene_symbol == self.resolved_gene_symbol
                else "alias"
            ),
        }

    def worker_payload(self) -> dict[str, Any]:
        """Serialize the literal query while keeping analysis identity canonical.

        Pydantic's normal dump intentionally contains the resolved symbol so
        aliases share a canonical estimand. Queue workers also need the
        submitted spelling to reproduce the resolution provenance.
        """

        payload = self.model_dump(mode="json")
        payload["gene_symbol"] = (
            self.requested_gene_symbol or self.resolved_gene_symbol
        )
        return payload

    @field_validator("cancers", "study_ids")
    @classmethod
    def normalize_hierarchical_selections(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))


class HierarchicalPanCancerPreflightOut(BaseModel):
    schema_version: Literal[
        "tcga-trace-hierarchical-pancancer-preflight-v1"
    ] = "tcga-trace-hierarchical-pancancer-preflight-v1"
    pipeline_version: str
    registry_version: str
    requested_gene_symbol: str | None = None
    resolved_gene_symbol: str | None = None
    request: dict[str, Any]
    summary: dict[str, Any]
    universes: list[dict[str, Any]] = Field(default_factory=list)
    cancer_groups: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class HierarchicalPanCancerOut(BaseModel):
    schema_version: Literal[
        "tcga-trace-hierarchical-pancancer-result-v1"
    ] = "tcga-trace-hierarchical-pancancer-result-v1"
    scan_id: str
    status: Literal["completed"]
    cached: bool = False
    pipeline_version: str
    registry_version: str
    analysis_mode: Literal["hierarchical"] = "hierarchical"
    gene_symbol: str
    requested_gene_symbol: str | None = None
    resolved_gene_symbol: str | None = None
    endpoint: str
    effect_scale: dict[str, Any]
    request_snapshot: dict[str, Any]
    data_version: dict[str, Any] = Field(default_factory=dict)
    software_versions: dict[str, Any] = Field(default_factory=dict)
    preflight: dict[str, Any]
    summary: dict[str, Any]
    study_results: list[dict[str, Any]] = Field(default_factory=list)
    cancer_results: list[dict[str, Any]] = Field(default_factory=list)
    global_result: dict[str, Any] = Field(default_factory=dict)
    leave_one_out: dict[str, Any] = Field(default_factory=dict)
    sensitivities: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    downloads: dict[str, str] = Field(default_factory=dict)
    audit: dict[str, Any] = Field(default_factory=dict)


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
    signature_scoring: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)


class PanCancerSurvivalOut(BaseModel):
    scan_id: str
    status: str
    cached: bool = False
    gene_symbol: str
    signature: dict[str, Any] | None = None
    signature_scoring_scope: dict[str, Any] = Field(default_factory=dict)
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


class BatchGroupedTestOut(BaseModel):
    index: int = Field(ge=0)
    test: Literal["logrank", "maxstat_lau94_corrected", "maxstat_corrected_unavailable"]
    p_value: float | None = Field(default=None, ge=0, le=1)
    bh_q_value: float | None = Field(default=None, ge=0, le=1)
    bonferroni_p_value: float | None = Field(default=None, ge=0, le=1)


class BatchGroupedFamilyOut(BaseModel):
    contract: Literal["compare-grouped-family-v1"]
    scope: Literal["valid_grouped_tests_in_submitted_batch"]
    requested: int = Field(ge=0)
    completed: int = Field(ge=0)
    failed: int = Field(ge=0)
    evaluable: int = Field(ge=0)
    unavailable: int = Field(ge=0)
    tests: list[BatchGroupedTestOut]


class AnalysisBatchOut(BaseModel):
    total: int
    completed: int
    failed: int
    max_concurrency: int
    results: list[AnalysisBatchItemOut]
    grouped_family: BatchGroupedFamilyOut | None = None


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
        max_length=7,
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
            normalized = SignatureGene(
                gene_symbol=symbol,
                weight=gene.weight,
                direction=gene.direction,
            )
            previous = deduplicated.get(symbol)
            if previous is not None:
                if (
                    not math.isclose(previous.weight, normalized.weight)
                    or previous.direction != normalized.direction
                ):
                    raise ValueError(
                        f"Duplicate gene {symbol} has conflicting weights or directions."
                    )
                continue
            deduplicated[symbol] = normalized
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
        declare_request_sample_population(
            cohort=self.cohort,
            dataset_id=self.dataset_id,
            filters=self.filters,
        )
        if "single" in self.scoring_methods and len(self.genes) != 1:
            raise ValueError(
                "Single-gene scoring requires exactly one gene in a multiverse."
            )
        if any(method != "single" for method in self.scoring_methods) and len(self.genes) < 2:
            raise ValueError(
                "Multi-gene signature scoring requires at least two genes."
            )
        has_rank_method = any(
            method in RANK_BASED_SIGNATURE_METHODS
            for method in self.scoring_methods
        )
        if not has_rank_method and any(
            gene.direction is not None for gene in self.genes
        ):
            raise ValueError(
                "Explicit up/down direction requires singscore, ssGSEA or "
                "AUCell in the Robustness scoring family."
            )
        for method in self.scoring_methods:
            validate_signature_scoring_contract(
                method=method,
                genes=signature_genes_for_method(self.genes, method),
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


UserExpressionOrientation = Literal["genes_by_rows", "samples_by_rows"]
UserClinicalVariableTiming = Literal[
    "baseline",
    "pre_treatment",
    "on_treatment",
    "post_treatment",
    "post_baseline",
    "outcome",
    "unknown",
]
UserExpressionUnit = Literal[
    "counts",
    "tpm",
    "fpkm",
    "fpkm_uq",
    "cpm",
    "log2_tpm",
    "log2_fpkm",
    "log2_fpkm_uq",
    "log2_cpm",
    "normalized_log2",
    "normalized_continuous",
]


class UserDatasetCustomClinicalVariable(BaseModel):
    """A user-declared, reusable clinical annotation.

    These fields are retained as dataset metadata for filtering and grouping.
    They are deliberately separate from ``ClinicalCovariate`` and therefore do
    not enter Cox models unless a future, explicit adjustment contract is
    implemented.
    """

    source_column: str = Field(min_length=1, max_length=128)
    id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$",
    )
    label: str = Field(min_length=1, max_length=100)
    value_type: Literal["categorical", "numeric"]
    unit: str | None = Field(default=None, max_length=64)
    timing: UserClinicalVariableTiming = "unknown"
    expression_derived: bool = False
    description: str | None = Field(default=None, max_length=500)

    @field_validator(
        "source_column",
        "id",
        "label",
        "unit",
        "description",
        mode="before",
    )
    @classmethod
    def normalize_custom_variable_text(cls, value: Any) -> Any:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("timing", mode="before")
    @classmethod
    def normalize_custom_variable_timing(cls, value: Any) -> str:
        return str(value or "unknown").strip().casefold().replace("-", "_")


class UserDatasetCovariateColumns(BaseModel):
    stage: str | None = Field(default=None, max_length=128)
    grade: str | None = Field(default=None, max_length=128)
    age_at_index: str | None = Field(default=None, max_length=128)
    gender: str | None = Field(default=None, max_length=128)
    race: str | None = Field(default=None, max_length=128)

    @field_validator(
        "stage",
        "grade",
        "age_at_index",
        "gender",
        "race",
        mode="before",
    )
    @classmethod
    def normalize_optional_columns(cls, value: Any) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None


class UserDatasetMapping(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    cancer_code: str = Field(
        min_length=2,
        max_length=8,
        pattern=r"^[A-Za-z0-9-]+$",
    )
    expression_orientation: UserExpressionOrientation
    expression_id_column: str = Field(min_length=1, max_length=128)
    clinical_id_column: str = Field(min_length=1, max_length=128)
    has_survival_outcome: bool = True
    time_column: str | None = Field(default=None, max_length=128)
    event_column: str | None = Field(default=None, max_length=128)
    event_value: str | None = Field(default=None, max_length=128)
    censored_value: str | None = Field(default=None, max_length=128)
    time_unit: Literal["days", "months", "years"] | None = None
    endpoint: Endpoint = "OS"
    expression_unit: UserExpressionUnit
    covariates: UserDatasetCovariateColumns = Field(
        default_factory=UserDatasetCovariateColumns
    )
    custom_clinical_variables: list[UserDatasetCustomClinicalVariable] = Field(
        default_factory=list,
        max_length=10,
        validation_alias=AliasChoices(
            "custom_clinical_variables",
            "custom_variables",
        ),
    )
    confirm_deidentified: bool

    @property
    def custom_variables(self) -> list[UserDatasetCustomClinicalVariable]:
        """Concise compatibility accessor for early v2 clients."""

        return self.custom_clinical_variables

    @field_validator(
        "name",
        "cancer_code",
        "expression_id_column",
        "clinical_id_column",
    )
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator(
        "time_column",
        "event_column",
        "event_value",
        "censored_value",
        mode="before",
    )
    @classmethod
    def normalize_optional_outcome_text(cls, value: Any) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator("cancer_code")
    @classmethod
    def normalize_cancer_code(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_mapping(self) -> "UserDatasetMapping":
        if not self.confirm_deidentified:
            raise ValueError(
                "Confirm that the uploaded files contain de-identified research data."
            )
        if self.has_survival_outcome:
            outcome_fields = {
                "time_column": self.time_column,
                "event_column": self.event_column,
                "event_value": self.event_value,
                "censored_value": self.censored_value,
                "time_unit": self.time_unit,
            }
            missing = [key for key, value in outcome_fields.items() if not value]
            if missing:
                raise ValueError(
                    "Time, event, event value and censored value are required when a survival outcome is declared."
                )
            if self.event_value.casefold() == self.censored_value.casefold():
                raise ValueError(
                    "event_value and censored_value must identify different values."
                )
            required = {
                self.clinical_id_column,
                self.time_column,
                self.event_column,
            }
            if len(required) != 3:
                raise ValueError(
                    "Clinical ID, time and event must use three distinct columns."
                )
        standard_columns = {
            value.casefold()
            for value in self.covariates.model_dump().values()
            if value
        }
        protected_columns = {
            self.clinical_id_column.casefold(),
            *standard_columns,
        }
        if self.has_survival_outcome:
            protected_columns.update(
                value.casefold()
                for value in (self.time_column, self.event_column)
                if value
            )
        reserved_ids = {
            "patient_id",
            "sample_id",
            "case_id",
            "subject_id",
            "participant_id",
            "person_id",
            "individual_id",
            "donor_id",
            "barcode",
            "mrn",
            "time",
            "time_days",
            "event",
            "event_status",
            "survival_time",
            "followup_time",
            "follow_up_time",
            "os_time",
            "os_event",
            "os_status",
            "stage",
            "grade",
            "age_at_index",
            "gender",
            "race",
        }
        direct_identifier_columns = {
            "id",
            "patient_id",
            "sample_id",
            "case_id",
            "subject_id",
            "participant_id",
            "barcode",
            "name",
            "first_name",
            "last_name",
            "email",
            "phone",
            "address",
            "mrn",
            "medical_record_number",
            "full_name",
            "given_name",
            "family_name",
            "surname",
            "telephone",
            "email_address",
            "phone_number",
            "street_address",
            "date_of_birth",
            "birth_date",
            "dob",
        }
        seen_ids: set[str] = set()
        seen_source_columns: set[str] = set()
        for variable in self.custom_clinical_variables:
            variable_id = variable.id.casefold()
            source_column = variable.source_column.casefold()
            normalized_source = re.sub(
                r"[^a-z0-9]+", "_", source_column
            ).strip("_")
            if variable_id in seen_ids:
                raise ValueError(
                    "Custom clinical variable IDs must be unique."
                )
            if source_column in seen_source_columns:
                raise ValueError(
                    "Each custom clinical source column may be mapped only once."
                )
            if variable_id in reserved_ids or variable_id.startswith(
                ("cdr.", "metadata.")
            ):
                raise ValueError(
                    f"Custom clinical variable ID {variable.id!r} is reserved."
                )
            if source_column in protected_columns:
                raise ValueError(
                    f"Custom clinical source column {variable.source_column!r} "
                    "is already assigned to an identifier, endpoint or standard covariate."
                )
            direct_identifier_pattern = re.compile(
                r"(?:^|_)(?:patient|sample|case|subject|participant|person|"
                r"individual|donor)_(?:id|identifier|number|barcode)(?:_|$)|"
                r"(?:^|_)(?:mrn|medical_record_number|barcode|email|e_mail|"
                r"phone|telephone|address|full_name|first_name|last_name|"
                r"given_name|family_name|surname|date_of_birth|birth_date|dob)"
                r"(?:_|$)"
            )
            if (
                normalized_source in direct_identifier_columns
                or direct_identifier_pattern.search(normalized_source)
            ):
                raise ValueError(
                    f"Custom clinical source column {variable.source_column!r} "
                    "appears to contain direct identifiers."
                )
            seen_ids.add(variable_id)
            seen_source_columns.add(source_column)
        return self


class UserDatasetOut(BaseModel):
    id: str
    kind: Literal["user"]
    name: str
    cancer_code: str
    tcga_cohort: str
    cancer_name: str
    active_release_id: str
    patient_count: int
    sample_count: int
    gene_count: int
    event_count: int = 0
    endpoint: dict[str, Any] | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)
    expression_layer: dict[str, Any]
    qc: dict[str, Any]
    created_at: datetime
    expires_at: datetime | None
    privacy: dict[str, Any]


class UserDatasetCreatedOut(UserDatasetOut):
    access_token: str = Field(min_length=32, max_length=256)


class GseaAnalysisOut(BaseModel):
    schema_version: Literal[
        "tcga-trace-preranked-gsea-result-v1",
        "tcga-trace-camera-preranked-gsea-result-v2"
    ] = "tcga-trace-camera-preranked-gsea-result-v2"
    gsea_id: str
    status: Literal["completed"]
    pipeline_version: str
    cohort: str
    dataset_id: str | None = None
    dataset_release_id: str | None = None
    expression_scale: str
    expression_scale_label: str
    grouping: dict[str, Any]
    gene_set_collection: dict[str, Any]
    ranking: dict[str, Any]
    inference: dict[str, Any] | None = None
    summary: dict[str, Any]
    pathways: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    downloads: dict[str, str] = Field(default_factory=dict)
    data_provenance: dict[str, Any] = Field(default_factory=dict)
    audit: dict[str, Any] = Field(default_factory=dict)
    cached: bool = False

    @model_validator(mode="after")
    def require_camera_contract_for_v2(self) -> "GseaAnalysisOut":
        if (
            self.schema_version
            == "tcga-trace-camera-preranked-gsea-result-v2"
            and not self.inference
        ):
            raise ValueError("GSEA result schema v2 requires CAMERA inference metadata.")
        return self


class ExpressionComparisonOut(BaseModel):
    schema_version: Literal[
        "tcga-trace-expression-comparison-result-v1"
    ] = "tcga-trace-expression-comparison-result-v1"
    comparison_id: str
    status: Literal["completed"]
    pipeline_version: str
    cohort: str
    dataset_id: str | None = None
    dataset_release_id: str | None = None
    expression_scale: str
    expression_scale_label: str
    grouping: dict[str, Any]
    summary: dict[str, Any]
    statistics: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    downloads: dict[str, str] = Field(default_factory=dict)
    data_provenance: dict[str, Any] = Field(default_factory=dict)
    audit: dict[str, Any] = Field(default_factory=dict)
    cached: bool = False


ComputeJobKind = Literal[
    "analysis",
    "combined",
    "signature_panel",
    "batch",
    "multiverse",
    "pancancer",
    "pancancer_hierarchical",
    "session",
    "gsea",
    "expression_comparison",
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
