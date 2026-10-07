from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import random
import re
import threading
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable


TUTORIAL_ASSET_SCHEMA_VERSION = "tutorial-assets-v1"
TUTORIAL_ASSET_RELEASE = "2026-08-05"
TUTORIAL_SEED = 17291
_ARCHIVE_TIMESTAMP = (2026, 8, 5, 0, 0, 0)
_HGNC_LIKE = re.compile(r"^[A-Z][A-Z0-9-]{1,19}$")
_TRANSCRIPTOME_GENE_COUNT = 18_000
_COUNTS_GENE_COUNT = 6_000


class TutorialAssetNotFound(KeyError):
    pass


@dataclass(frozen=True)
class TutorialAsset:
    asset_id: str
    filename: str
    title: dict[str, str]
    description: dict[str, str]
    intended_uses: tuple[str, ...]
    sample_count: int
    gene_count: int
    expression_scale: str
    generator: Callable[[], bytes]
    limitations: tuple[str, ...] = ()

    def public_record(self) -> dict:
        return {
            "id": self.asset_id,
            "version": "1.0.0",
            "released_at": TUTORIAL_ASSET_RELEASE,
            "title": self.title,
            "description": self.description,
            "intended_uses": list(self.intended_uses),
            "sample_count": self.sample_count,
            "gene_count": self.gene_count,
            "expression_scale": self.expression_scale,
            "synthetic": True,
            "seed": TUTORIAL_SEED,
            "limitations": list(self.limitations),
            "download_url": f"/api/v1/tutorial-assets/{self.asset_id}",
            "filename": self.filename,
        }


def _csv_text(rows: Iterable[Iterable[object]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerows(rows)
    return stream.getvalue()


def _stable_archive(files: dict[str, str | bytes]) -> bytes:
    prepared: dict[str, bytes] = {
        name: value.encode("utf-8") if isinstance(value, str) else value
        for name, value in files.items()
    }
    checksums = {
        name: hashlib.sha256(content).hexdigest()
        for name, content in sorted(prepared.items())
    }
    prepared["SHA256SUMS.txt"] = "".join(
        f"{digest}  {name}\n" for name, digest in checksums.items()
    ).encode("utf-8")

    archive = io.BytesIO()
    with zipfile.ZipFile(
        archive,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as bundle:
        for name, content in sorted(prepared.items()):
            info = zipfile.ZipInfo(name, date_time=_ARCHIVE_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 3
            bundle.writestr(info, content)
    return archive.getvalue()


def _manifest(
    *,
    asset_id: str,
    sample_count: int,
    gene_count: int,
    expression_scale: str,
    recipes: list[dict],
    expected_qc: list[str],
    notes: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "schema_version": TUTORIAL_ASSET_SCHEMA_VERSION,
            "asset_id": asset_id,
            "asset_version": "1.0.0",
            "released_at": TUTORIAL_ASSET_RELEASE,
            "synthetic": True,
            "seed": TUTORIAL_SEED,
            "sample_count": sample_count,
            "gene_count": gene_count,
            "expression_scale": expression_scale,
            "recipes": recipes,
            "expected_qc": expected_qc,
            "notes": notes or [],
        },
        indent=2,
        sort_keys=True,
    ) + "\n"


def _format_only_archive() -> bytes:
    samples = [f"S{index:02d}" for index in range(1, 13)]
    expression_rows: list[list[object]] = [["gene_symbol", *samples]]
    for gene, base, slope in (("TP53", 2.0, 0.15), ("MKI67", 4.1, 0.08), ("BAX", 3.7, -0.05)):
        expression_rows.append(
            [gene, *[f"{base + index * slope:.2f}" for index in range(12)]]
        )
    clinical_rows: list[list[object]] = [
        ["sample_id", "os_months", "os_status", "age", "stage", "grade"]
    ]
    for index, sample in enumerate(samples, start=1):
        clinical_rows.append(
            [
                sample,
                8 + index * 4,
                "event" if index <= 6 else "censored",
                45 + index,
                f"Stage {1 + (index % 4)}",
                f"G{1 + (index % 3)}",
            ]
        )
    recipes = [{"module": "upload", "purpose": "column mapping only"}]
    files = {
        "expression.csv": _csv_text(expression_rows),
        "clinical.csv": _csv_text(clinical_rows),
        "README_EN.md": (
            "# Format-only upload example\n\n"
            "Synthetic, de-identified data for learning the upload mapper. It is deliberately "
            "too small and too narrow for scientific analysis or GSEA. Select **Other normalized "
            "log scale**. Do not interpret estimates from this pack.\n"
        ),
        "README_ES.md": (
            "# Ejemplo de formato para carga\n\n"
            "Datos sintéticos y desidentificados para aprender el mapeo de columnas. Es "
            "deliberadamente pequeño y angosto: no sirve para inferencia científica ni GSEA. "
            "Seleccione **Otra escala logarítmica normalizada**. No interprete sus estimaciones.\n"
        ),
        "manifest.json": _manifest(
            asset_id="format-only-upload-v1",
            sample_count=12,
            gene_count=3,
            expression_scale="other_normalized_log",
            recipes=recipes,
            expected_qc=["Mapping preview is available", "Scientific sample-size gates may fail"],
        ),
    }
    return _stable_archive(files)


_QUICKSTART_GENES = (
    "CA9", "VHL", "VEGFA", "EPAS1", "MKI67", "BIRC5", "UBE2C", "CXCL9",
    "CXCL10", "CXCR3", "CD3D", "CD8A", "GZMB", "NKG7", "PDCD1", "CD274",
    "TP53", "EPCAM", "VIM", "ACTB", "GAPDH", "BAX", "BCL2", "CCNB1",
    "CDC20", "FOXM1", "KDR", "HIF1A", "PRF1", "LAG3", "HAVCR2", "STAT1",
)


def _quickstart_values() -> tuple[list[str], list[list[object]], dict[str, list[float]]]:
    rng = random.Random(TUTORIAL_SEED)
    samples = [f"KIRC_SYN_{index:03d}" for index in range(1, 49)]
    stages = ["Stage I", "Stage II", "Stage III", "Stage IV"]
    grades = ["G1", "G2", "G3", "G4"]
    molecular_classes = ["ccA", "ccB", "immune-high", "angiogenic", "unclassified"]
    clinical: list[list[object]] = [[
        "sample_id", "os_months", "os_status", "age", "stage", "grade",
        "molecular_subtype", "immune_score", "collection_timing",
    ]]
    expression: dict[str, list[float]] = {gene: [] for gene in _QUICKSTART_GENES}
    proliferative = {"MKI67", "BIRC5", "UBE2C", "CCNB1", "CDC20", "FOXM1"}
    immune = {"CXCL9", "CXCL10", "CXCR3", "CD3D", "CD8A", "GZMB", "NKG7", "PDCD1", "CD274", "PRF1", "LAG3", "HAVCR2", "STAT1"}
    hypoxia = {"CA9", "VEGFA", "EPAS1", "KDR", "HIF1A"}
    for index, sample in enumerate(samples):
        stage_index = index % 4
        event = index % 2 == 0
        immune_score = -1.6 + (index % 12) * 0.28
        clinical.append([
            sample,
            f"{10 + index * 1.65 + (8 if not event else 0):.1f}",
            "event" if event else "censored",
            42 + (index * 7) % 37,
            stages[stage_index],
            grades[(index // 3) % 4],
            molecular_classes[index % len(molecular_classes)],
            f"{immune_score:.2f}",
            "baseline",
        ])
        for gene_index, gene in enumerate(_QUICKSTART_GENES):
            value = 3.1 + (gene_index % 9) * 0.31 + rng.gauss(0, 0.36)
            if gene in proliferative:
                value += stage_index * 0.30
            if gene in hypoxia:
                value += stage_index * 0.23
            if gene in immune:
                value += immune_score * 0.24
            expression[gene].append(round(max(0.05, value), 4))
    return samples, clinical, expression


def _quickstart_archive() -> bytes:
    samples, clinical, expression = _quickstart_values()
    genes_by_samples: list[list[object]] = [["gene_symbol", *samples]]
    for gene in _QUICKSTART_GENES:
        genes_by_samples.append([gene, *[f"{value:.4f}" for value in expression[gene]]])
    samples_by_genes: list[list[object]] = [["sample_id", *_QUICKSTART_GENES]]
    for sample_index, sample in enumerate(samples):
        samples_by_genes.append([
            sample,
            *[f"{expression[gene][sample_index]:.4f}" for gene in _QUICKSTART_GENES],
        ])
    tpm_rows: list[list[object]] = [["gene_symbol", *samples]]
    for gene in _QUICKSTART_GENES:
        tpm_rows.append([
            gene,
            *[f"{max(0.0, math.pow(2.0, value) - 1.0):.4f}" for value in expression[gene]],
        ])
    recipes = [
        {"module": "survival", "gene": "CDC20", "endpoint": "OS", "cutpoint": "median"},
        {"module": "expression", "genes": ["CA9", "MKI67", "CD8A"], "grouping": "stage I+II vs III+IV"},
        {"module": "compare", "genes": ["CDC20", "CA9"], "endpoint": "OS"},
        {"module": "multiverse", "genes": ["CDC20"], "endpoint": "OS"},
    ]
    files = {
        "clinical.csv": _csv_text(clinical),
        "expression_log2_genes_by_samples.csv": _csv_text(genes_by_samples),
        "alternatives/expression_log2_samples_by_genes.csv": _csv_text(samples_by_genes),
        "alternatives/expression_tpm_genes_by_samples.csv": _csv_text(tpm_rows),
        "data_dictionary.csv": _csv_text([
            ["column", "type", "timing", "description_en", "description_es"],
            ["molecular_subtype", "categorical", "baseline", "Synthetic molecular class", "Clase molecular sintética"],
            ["immune_score", "numeric", "baseline", "Synthetic immune score", "Puntaje inmune sintético"],
            ["collection_timing", "categorical", "baseline", "Measurement timing", "Momento de medición"],
        ]),
        "README_EN.md": (
            "# Private-data quickstart: synthetic KIRC-like cohort\n\n"
            "Use `clinical.csv` with `expression_log2_genes_by_samples.csv`; map expression as "
            "log2(TPM + 1). The alternate files teach matrix orientation and TPM mapping. The pack "
            "supports upload, Survival, Expression, Compare, and Multiverse tutorials. Its 32-gene "
            "matrix is **not appropriate for GSEA**. Effects are seeded for teaching and are not "
            "biological findings.\n"
        ),
        "README_ES.md": (
            "# Inicio rápido con datos privados: cohorte sintética tipo KIRC\n\n"
            "Use `clinical.csv` con `expression_log2_genes_by_samples.csv` y mapee la expresión "
            "como log2(TPM + 1). Los archivos alternativos enseñan orientación y escala TPM. El "
            "paquete sirve para los tutoriales de carga, Survival, Expression, Compare y Multiverse. "
            "Su matriz de 32 genes **no es apropiada para GSEA**. Los efectos fueron sembrados con "
            "fines docentes y no constituyen hallazgos biológicos.\n"
        ),
        "manifest.json": _manifest(
            asset_id="private-quickstart-kirc-log2-v1",
            sample_count=48,
            gene_count=len(_QUICKSTART_GENES),
            expression_scale="log2_tpm_plus_1",
            recipes=recipes,
            expected_qc=[
                "48 linked patients", "24 events and 24 censored observations",
                "Stage I-IV and grade G1-G4 retained", "32 unique HGNC-like symbols",
            ],
            notes=["Teaching-only synthetic truth", "Do not use the narrow matrix for GSEA"],
        ),
    }
    return _stable_archive(files)


def _gmt_rows() -> list[tuple[str, list[str]]]:
    root = Path(__file__).resolve().parents[1] / "gene_sets"
    rows: list[tuple[str, list[str]]] = []
    for filename in ("go-bp-20260619.gmt", "immport-current-20260730.gmt"):
        path = root / filename
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            fields = line.split("\t")
            if len(fields) >= 3:
                rows.append((fields[0], fields[2:]))
    return rows


@lru_cache(maxsize=1)
def _transcriptome_gene_design() -> tuple[list[str], set[str], set[str]]:
    rows = _gmt_rows()
    symbols = sorted({
        gene
        for _, genes in rows
        for gene in genes
        if _HGNC_LIKE.fullmatch(gene) and not gene.endswith("_HUMAN")
    })
    required = {
        "CDC20", "BIRC5", "UBE2C", "MKI67", "FOXM1", "VEGFA", "EPAS1",
        "HIF1A", "KDR", "CXCL9", "CXCL10", "CD3D", "CD8A", "GZMB", "NKG7",
        "PRF1", "PDCD1", "CD274",
    }
    missing_required = sorted(required.difference(symbols))
    if missing_required:
        raise RuntimeError(
            "The bundled GO BP and ImmPort gene universes are missing required "
            f"teaching symbols: {', '.join(missing_required)}."
        )
    if len(symbols) < _TRANSCRIPTOME_GENE_COUNT:
        raise RuntimeError(
            "The bundled GO BP and ImmPort gene universes must supply at least "
            f"{_TRANSCRIPTOME_GENE_COUNT:,} unique HGNC-like symbols; found "
            f"{len(symbols):,}. Tutorial catalog counts would otherwise be false."
        )
    ordered = sorted(required) + [gene for gene in symbols if gene not in required]
    genes = ordered[:_TRANSCRIPTOME_GENE_COUNT]
    if len(genes) != _TRANSCRIPTOME_GENE_COUNT:
        raise RuntimeError(
            "Transcriptome tutorial construction did not produce exactly "
            f"{_TRANSCRIPTOME_GENE_COUNT:,} genes."
        )
    gene_set = set(genes)
    advanced_patterns = ("cell cycle", "hypoxia", "angiogenesis")
    early_patterns = ("t cell", "cytotoxic")
    advanced = {
        gene for name, members in rows
        if any(pattern in name.lower() for pattern in advanced_patterns)
        for gene in members if gene in gene_set
    }
    early = {
        gene for name, members in rows
        if any(pattern in name.lower() for pattern in early_patterns)
        for gene in members if gene in gene_set
    } - advanced
    return genes, advanced, early


def _transcriptome_archive() -> bytes:
    genes, advanced, early = _transcriptome_gene_design()
    rng = random.Random(TUTORIAL_SEED)
    samples = [f"KIRC_GSEA_{index:03d}" for index in range(1, 97)]
    clinical: list[list[object]] = [[
        "sample_id", "os_months", "os_status", "age", "stage", "grade",
        "stage_binary", "collection_timing",
    ]]
    stage_names = ("Stage I", "Stage II", "Stage III", "Stage IV")
    for index, sample in enumerate(samples):
        stage_index = index // 24
        event = index % 2 == 0
        clinical.append([
            sample,
            f"{12 + index * 0.9 + (9 if not event else 0):.1f}",
            "event" if event else "censored",
            41 + (index * 11) % 39,
            stage_names[stage_index],
            f"G{1 + (index // 12) % 4}",
            "Early (I+II)" if stage_index < 2 else "Advanced (III+IV)",
            "baseline",
        ])
    expression = io.StringIO(newline="")
    writer = csv.writer(expression, lineterminator="\n")
    writer.writerow(["gene_symbol", *samples])
    for gene_index, gene in enumerate(genes):
        baseline = 2.1 + (gene_index % 31) * 0.105
        values: list[str] = []
        for sample_index in range(len(samples)):
            advanced_sample = sample_index >= 48
            shift = 0.0
            if gene in advanced:
                shift = 0.48 if advanced_sample else -0.08
            elif gene in early:
                shift = -0.43 if advanced_sample else 0.08
            value = max(0.0, baseline + shift + rng.gauss(0, 0.72))
            values.append(f"{value:.4f}")
        writer.writerow([gene, *values])
    recipes = [
        {
            "module": "gsea",
            "grouping": "stage I+II vs III+IV",
            "collections": ["GO Biological Process", "ImmPort"],
            "ranking": "Welch B-A",
            "min_set_size": 15,
            "max_set_size": 500,
            "permutations": 1000,
            "seed": TUTORIAL_SEED,
        }
    ]
    files = {
        "clinical.csv": _csv_text(clinical),
        "expression_log2_tpm_plus_1.csv": expression.getvalue(),
        "README_EN.md": (
            "# Transcriptome-scale synthetic GSEA cohort\n\n"
            "A deterministic, de-identified teaching matrix with 96 patients and 18,000 "
            "HGNC-like symbols drawn from the bundled GO BP and ImmPort universes. Compare "
            "Stage I+II (A) with Stage III+IV (B), rank with Welch B-A, and run GO BP and "
            "ImmPort separately (15-500 genes, 1,000 permutations, seed 17291). Moderate "
            "cell-cycle/hypoxia/angiogenesis signal is seeded toward advanced disease and "
            "T-cell/cytotoxic signal toward early disease. Thousands of genes are null.\n"
        ),
        "README_ES.md": (
            "# Cohorte transcriptómica sintética para GSEA\n\n"
            "Matriz docente determinista y desidentificada con 96 pacientes y 18.000 símbolos "
            "tipo HGNC tomados de los universos GO BP e ImmPort incluidos. Compare Stage I+II "
            "(A) con Stage III+IV (B), ordene con Welch B-A y ejecute GO BP e ImmPort por "
            "separado (15-500 genes, 1.000 permutaciones, semilla 17291). Se sembró una señal "
            "moderada de ciclo celular/hipoxia/angiogénesis hacia enfermedad avanzada y de "
            "células T/citotoxicidad hacia enfermedad temprana. Miles de genes son nulos.\n"
        ),
        "synthetic_truth.json": json.dumps({
            "seed": TUTORIAL_SEED,
            "advanced_positive_families": ["cell cycle", "hypoxia", "angiogenesis"],
            "early_positive_families": ["T cell", "cytotoxicity"],
            "advanced_seeded_genes": len(advanced),
            "early_seeded_genes": len(early),
            "completion_rule": "Completion never depends on statistical significance.",
        }, indent=2, sort_keys=True) + "\n",
        "manifest.json": _manifest(
            asset_id="private-transcriptome-kirc-gsea-v1",
            sample_count=96,
            gene_count=len(genes),
            expression_scale="log2_tpm_plus_1",
            recipes=recipes,
            expected_qc=[
                "96 linked patients", "48 events and 48 censored observations",
                "18,000 unique HGNC-like symbols", "48 early and 48 advanced samples",
            ],
            notes=[
                "Synthetic effects are intentionally moderate and do not guarantee significance",
                "Fixed teaching truth is not a biological claim",
            ],
        ),
    }
    return _stable_archive(files)


def _full_counts_archive() -> bytes:
    rng = random.Random(TUTORIAL_SEED)
    samples = [f"COUNT_SYN_{index:03d}" for index in range(1, 65)]
    genes, _, _ = _transcriptome_gene_design()
    genes = genes[:_COUNTS_GENE_COUNT]
    if len(genes) != _COUNTS_GENE_COUNT:
        raise RuntimeError(
            "Raw-count tutorial construction did not produce exactly "
            f"{_COUNTS_GENE_COUNT:,} genes."
        )
    clinical = [["sample_id", "os_days", "os_status", "stage"]]
    for index, sample in enumerate(samples):
        clinical.append([
            sample,
            180 + index * 19,
            "event" if index % 2 == 0 else "censored",
            f"Stage {1 + index % 4}",
        ])
    expression = io.StringIO(newline="")
    writer = csv.writer(expression, lineterminator="\n")
    writer.writerow(["gene_symbol", *samples])
    for gene_index, gene in enumerate(genes):
        mean = 12 + (gene_index % 47) * 3
        writer.writerow([gene, *[max(0, int(rng.gauss(mean, math.sqrt(mean) * 1.8))) for _ in samples]])
    files = {
        "clinical.csv": _csv_text(clinical),
        "raw_counts.csv": expression.getvalue(),
        "README_EN.md": (
            "# Raw-count normalization practice\n\nThis optional synthetic pack is for the "
            "count-normalization path. Do not label counts as TPM or log expression.\n"
        ),
        "README_ES.md": (
            "# Práctica de normalización de conteos\n\nEste paquete sintético opcional sirve "
            "para la ruta de normalización de conteos. No declare los conteos como TPM ni log.\n"
        ),
        "manifest.json": _manifest(
            asset_id="private-full-counts-normalization-v1",
            sample_count=len(samples),
            gene_count=len(genes),
            expression_scale="raw_counts",
            recipes=[{"module": "upload", "purpose": "count normalization"}],
            expected_qc=["64 linked patients", "6,000 integer-valued genes"],
        ),
    }
    return _stable_archive(files)


def _validation_lab_archive() -> bytes:
    samples, clinical, expression = _quickstart_values()
    valid_expression = [["gene_symbol", *samples]] + [
        [gene, *[f"{value:.4f}" for value in expression[gene]]]
        for gene in _QUICKSTART_GENES
    ]

    def upload_mapping(
        *,
        expression_orientation: str = "genes_by_rows",
        expression_id_column: str = "gene_symbol",
        expression_unit: str = "log2_tpm",
        time_unit: str = "months",
    ) -> dict:
        return {
            "name": "Synthetic KIRC upload-validation case",
            "cancer_code": "KIRC",
            "expression_orientation": expression_orientation,
            "expression_id_column": expression_id_column,
            "clinical_id_column": "sample_id",
            "time_column": "os_months",
            "event_column": "os_status",
            "event_value": "event",
            "censored_value": "censored",
            "time_unit": time_unit,
            "endpoint": "OS",
            "expression_unit": expression_unit,
            "covariates": {
                "age_at_index": "age",
                "stage": "stage",
                "grade": "grade",
                "gender": None,
                "race": None,
            },
            "custom_clinical_variables": [],
            "confirm_deidentified": True,
        }

    base_mapping = upload_mapping()
    files: dict[str, str] = {
        "README_EN.md": (
            "# Upload validation lab\n\nEach numbered directory isolates one structural "
            "error. Every directory contains a machine-readable `case.json` with the exact "
            "mapping and expected parser outcome. `valid-with-qc-notices` is accepted and "
            "emits the declared notice. The two semantic traps pass structural checks and "
            "must be caught by the analyst. Never combine directories in one upload.\n"
        ),
        "README_ES.md": (
            "# Laboratorio de validación de carga\n\nCada directorio numerado aísla un error "
            "estructural. Cada directorio contiene un `case.json` legible por máquina con el "
            "mapeo exacto y el resultado esperado del parser. `valid-with-qc-notices` es "
            "aceptable y emite el aviso declarado. Las dos trampas semánticas superan la "
            "validación estructural y debe detectarlas el analista. Nunca combine directorios "
            "en una misma carga.\n"
        ),
        "base/clinical.csv": _csv_text(clinical),
        "base/expression.csv": _csv_text(valid_expression),
        "base/mapping.json": json.dumps(
            base_mapping,
            indent=2,
            sort_keys=True,
        ) + "\n",
    }
    case_index: list[dict] = []

    def add_case(
        case_id: str,
        *,
        clinical_rows: list[list[object]] | None = None,
        expression_rows: list[list[object]] | None = None,
        mapping: dict | None = None,
        outcome: str,
        error_code: str | None = None,
        notice_codes: list[str] | None = None,
        semantic_review_required: bool = False,
        rationale_en: str,
        rationale_es: str,
    ) -> None:
        case_mapping = mapping or base_mapping
        case_record = {
            "schema_version": "trace-tutorial-upload-case-v1",
            "case_id": case_id,
            "input_files": {
                "clinical": "clinical.csv",
                "expression": "expression.csv",
            },
            "mapping": case_mapping,
            "expected": {
                "outcome": outcome,
                "error_code": error_code,
                "notice_codes": notice_codes or [],
                "semantic_review_required": semantic_review_required,
                "rationale": {
                    "en": rationale_en,
                    "es": rationale_es,
                },
            },
        }
        prefix = f"cases/{case_id}"
        files[f"{prefix}/clinical.csv"] = _csv_text(
            clinical_rows if clinical_rows is not None else clinical
        )
        files[f"{prefix}/expression.csv"] = _csv_text(
            expression_rows if expression_rows is not None else valid_expression
        )
        files[f"{prefix}/case.json"] = json.dumps(
            case_record,
            indent=2,
            sort_keys=True,
        ) + "\n"
        case_index.append(
            {
                "case_id": case_id,
                "metadata": f"{prefix}/case.json",
                "outcome": outcome,
                "error_code": error_code,
                "notice_codes": notice_codes or [],
                "semantic_review_required": semantic_review_required,
            }
        )

    third_state = [row[:] for row in clinical]
    third_state[4][2] = "progressed"
    add_case(
        "01-third-event-state",
        clinical_rows=third_state,
        outcome="rejected",
        error_code="UNMAPPED_EVENT_VALUE",
        rationale_en="A non-missing third event state is not mapped to event or censored.",
        rationale_es="Un tercer estado no ausente no está mapeado como evento o censura.",
    )
    duplicate_clinical = [row[:] for row in clinical] + [clinical[1][:]]
    add_case(
        "02-duplicate-clinical-id",
        clinical_rows=duplicate_clinical,
        outcome="rejected",
        error_code="DUPLICATE_CLINICAL_ID",
        rationale_en="One clinical patient identifier occurs twice.",
        rationale_es="Un identificador clínico de paciente aparece dos veces.",
    )
    case_mismatch = [row[:] for row in clinical]
    for row in case_mismatch[1:]:
        row[0] = str(row[0]).lower()
    add_case(
        "03-case-mismatch-ids",
        clinical_rows=case_mismatch,
        outcome="rejected",
        error_code="INSUFFICIENT_MATCHED_PATIENTS",
        rationale_en="All clinical IDs differ in case from expression IDs, yielding zero exact matches.",
        rationale_es="Todos los ID clínicos difieren en mayúsculas/minúsculas y producen cero coincidencias exactas.",
    )
    four_events = [row[:] for row in clinical]
    for index, row in enumerate(four_events[1:]):
        row[2] = "event" if index < 4 else "censored"
    add_case(
        "04-only-four-events",
        clinical_rows=four_events,
        outcome="accepted",
        notice_codes=["SURVIVAL_NOT_AVAILABLE"],
        rationale_en="Only four matched events remain. Molecular analyses stay available, while survival is reported as unavailable.",
        rationale_es="Solo quedan cuatro eventos pareados. Los análisis moleculares siguen disponibles y supervivencia se reporta como no disponible.",
    )
    gene_case_duplicate = [row[:] for row in valid_expression]
    gene_case_duplicate.append(["tp53", *gene_case_duplicate[17][1:]])
    add_case(
        "05-gene-case-duplicate",
        expression_rows=gene_case_duplicate,
        outcome="rejected",
        error_code="DUPLICATE_GENE",
        rationale_en="TP53 and tp53 collide after required upper-case normalization.",
        rationale_es="TP53 y tp53 colisionan tras la normalización obligatoria a mayúsculas.",
    )
    ensembl_rows = [["gene_symbol", *samples]] + [
        [f"ENSG{index:011d}", *row[1:]]
        for index, row in enumerate(valid_expression[1:], start=1)
    ]
    add_case(
        "06-mostly-ensembl",
        expression_rows=ensembl_rows,
        outcome="rejected",
        error_code="ENSEMBL_IDS_REQUIRE_SYMBOLS",
        rationale_en="The selected identifier column contains Ensembl IDs rather than HGNC symbols.",
        rationale_es="La columna seleccionada contiene ID Ensembl en vez de símbolos HGNC.",
    )
    negative_tpm = [row[:] for row in valid_expression]
    negative_tpm[2][3] = "-4.5"
    add_case(
        "07-negative-tpm",
        expression_rows=negative_tpm,
        mapping=upload_mapping(expression_unit="tpm"),
        outcome="rejected",
        error_code="NEGATIVE_EXPRESSION",
        rationale_en="TPM is declared as the source unit, but one value is negative.",
        rationale_es="Se declara TPM como unidad de origen, pero un valor es negativo.",
    )
    short_counts = [["gene_symbol", *samples]] + [
        [f"GENE{index:04d}", *[20 + (index + sample_index) % 15 for sample_index in range(len(samples))]]
        for index in range(1, 101)
    ]
    add_case(
        "08-counts-only-100-genes",
        expression_rows=short_counts,
        mapping=upload_mapping(expression_unit="counts"),
        outcome="rejected",
        error_code="COUNT_MATRIX_TOO_NARROW",
        rationale_en="Raw-count normalization requires at least 5,000 genes; this panel has 100.",
        rationale_es="La normalización de conteos exige al menos 5.000 genes; este panel tiene 100.",
    )
    samples_by_genes: list[list[object]] = [["sample_id", *_QUICKSTART_GENES]]
    for sample_index, sample in enumerate(samples):
        samples_by_genes.append([
            sample,
            *[
                f"{expression[gene][sample_index]:.4f}"
                for gene in _QUICKSTART_GENES
            ],
        ])
    duplicate_expression_id = [row[:] for row in samples_by_genes]
    duplicate_expression_id.append(samples_by_genes[1][:])
    add_case(
        "09-duplicate-expression-id",
        expression_rows=duplicate_expression_id,
        mapping=upload_mapping(
            expression_orientation="samples_by_rows",
            expression_id_column="sample_id",
        ),
        outcome="rejected",
        error_code="DUPLICATE_EXPRESSION_ID",
        rationale_en="The samples-by-rows matrix repeats one expression sample identifier.",
        rationale_es="La matriz con muestras por filas repite un identificador de expresión.",
    )
    duplicate_header = [row[:] for row in clinical]
    duplicate_header[0][4] = duplicate_header[0][3]
    add_case(
        "10-duplicate-header",
        clinical_rows=duplicate_header,
        outcome="rejected",
        error_code="DUPLICATE_COLUMN",
        rationale_en="The clinical header contains the age column name twice.",
        rationale_es="El encabezado clínico contiene dos veces el nombre de la columna de edad.",
    )
    nonpositive_time = [row[:] for row in clinical]
    for row in nonpositive_time[1:41]:
        row[1] = 0
    add_case(
        "11-nonpositive-time",
        clinical_rows=nonpositive_time,
        outcome="accepted",
        notice_codes=["SURVIVAL_NOT_AVAILABLE"],
        rationale_en="Forty non-positive times are excluded from survival, leaving eight complete outcomes; all matched patients remain available to molecular analyses.",
        rationale_es="Cuarenta tiempos no positivos se excluyen de supervivencia y quedan ocho desenlaces completos; todos los pacientes pareados siguen disponibles para análisis moleculares.",
    )
    long_rows = [["sample_id", "gene_symbol", "expression"]]
    for gene in _QUICKSTART_GENES[:4]:
        for sample_index, sample in enumerate(samples[:8]):
            long_rows.append([sample, gene, expression[gene][sample_index]])
    add_case(
        "12-long-format",
        expression_rows=long_rows,
        outcome="rejected",
        error_code="DUPLICATE_GENE",
        rationale_en="Long-form rows repeat gene symbols; TRACE requires a wide expression matrix.",
        rationale_es="Las filas en formato largo repiten genes; TRACE exige una matriz de expresión ancha.",
    )
    semantic_scale: list[list[object]] = [["gene_symbol", *samples]]
    for row in valid_expression[1:]:
        semantic_scale.append([
            row[0],
            *[
                f"{max(0.0, math.pow(2.0, float(value)) - 1.0):.4f}"
                for value in row[1:]
            ],
        ])
    add_case(
        "semantic-traps/tpm-declared-log2",
        expression_rows=semantic_scale,
        outcome="accepted",
        semantic_review_required=True,
        rationale_en="Values are TPM, but the supplied mapping declares log2(TPM + 1), so no required log transform is applied.",
        rationale_es="Los valores son TPM, pero el mapeo declara log2(TPM + 1), por lo que no se aplica la transformación logarítmica necesaria.",
    )
    semantic_time = [row[:] for row in clinical]
    for row in semantic_time[1:]:
        row[1] = f"{float(row[1]) * 30.4375:.4f}"
    add_case(
        "semantic-traps/days-declared-months",
        clinical_rows=semantic_time,
        outcome="accepted",
        semantic_review_required=True,
        rationale_en="Time values are days, but the os_months header and mapping declare months, inflating analysis time by 30.4375-fold.",
        rationale_es="Los tiempos están en días, pero el encabezado os_months y el mapeo declaran meses, inflando el tiempo analítico 30,4375 veces.",
    )
    qc_notices = [row[:] for row in clinical]
    qc_notices.extend([
        [
            "KIRC_CLINICAL_ONLY_001", 38, "event", 58, "Stage II", "G2",
            "ccA", "0.25", "baseline",
        ],
        [
            "KIRC_CLINICAL_ONLY_002", 51, "censored", 63, "Stage III", "G3",
            "ccB", "-0.35", "baseline",
        ],
    ])
    add_case(
        "valid-with-qc-notices",
        clinical_rows=qc_notices,
        outcome="accepted",
        notice_codes=["UNMATCHED_IDENTIFIERS_EXCLUDED"],
        rationale_en="Two complete clinical-only IDs are excluded and reported without blocking the 48 matched patients.",
        rationale_es="Se excluyen y reportan dos ID clínicos sin expresión sin bloquear los 48 pacientes pareados.",
    )
    files["cases/index.json"] = json.dumps(
        {
            "schema_version": "trace-tutorial-upload-case-index-v1",
            "cases": case_index,
        },
        indent=2,
        sort_keys=True,
    ) + "\n"
    files["manifest.json"] = _manifest(
        asset_id="private-upload-validation-lab-v1",
        sample_count=48,
        gene_count=len(_QUICKSTART_GENES),
        expression_scale="mixed_by_case",
        recipes=[{"module": "upload", "purpose": "isolated validation and semantic errors"}],
        expected_qc=[
            "Each case declares whether upload is rejected or accepted with survival unavailable",
            "Valid-with-qc-notices is accepted with UNMATCHED_IDENTIFIERS_EXCLUDED",
        ],
        notes=[
            "Semantic traps are structurally accepted and require human review",
            "cases/index.json is the machine-readable case inventory",
        ],
    )
    return _stable_archive(files)


_ASSETS = (
    TutorialAsset(
        asset_id="format-only-upload-v1",
        filename="trace-format-only-upload-v1.zip",
        title={"en": "Format-only upload example", "es": "Ejemplo de formato para carga"},
        description={"en": "Small mapper demonstration; not for inference.", "es": "Demostración pequeña del mapeador; no sirve para inferencia."},
        intended_uses=("upload_mapping",),
        sample_count=12,
        gene_count=3,
        expression_scale="other_normalized_log",
        generator=_format_only_archive,
        limitations=("Too small for scientific analysis", "Not appropriate for GSEA"),
    ),
    TutorialAsset(
        asset_id="private-quickstart-kirc-log2-v1",
        filename="trace-private-quickstart-kirc-log2-v1.zip",
        title={"en": "Private-data quickstart", "es": "Inicio rápido con datos privados"},
        description={"en": "48-patient, 32-gene synthetic KIRC-like teaching cohort.", "es": "Cohorte docente sintética tipo KIRC de 48 pacientes y 32 genes."},
        intended_uses=("upload", "survival", "expression", "compare", "multiverse"),
        sample_count=48,
        gene_count=32,
        expression_scale="log2_tpm_plus_1",
        generator=_quickstart_archive,
        limitations=("Not appropriate for GSEA", "Seeded effects are not biological evidence"),
    ),
    TutorialAsset(
        asset_id="private-transcriptome-kirc-gsea-v1",
        filename="trace-private-transcriptome-kirc-gsea-v1.zip",
        title={"en": "Transcriptome GSEA practice", "es": "Práctica transcriptómica de GSEA"},
        description={"en": "96-patient, 18,000-gene synthetic matrix with moderate pathway truth.", "es": "Matriz sintética de 96 pacientes y 18.000 genes con verdad de vías moderada."},
        intended_uses=("upload", "expression", "gsea"),
        sample_count=96,
        gene_count=_TRANSCRIPTOME_GENE_COUNT,
        expression_scale="log2_tpm_plus_1",
        generator=_transcriptome_archive,
        limitations=("Teaching-only synthetic truth", "Significance is not guaranteed"),
    ),
    TutorialAsset(
        asset_id="private-full-counts-normalization-v1",
        filename="trace-private-full-counts-normalization-v1.zip",
        title={"en": "Raw-count normalization practice", "es": "Práctica de normalización de conteos"},
        description={"en": "Optional 64-patient, 6,000-gene raw-count matrix.", "es": "Matriz opcional de conteos crudos con 64 pacientes y 6.000 genes."},
        intended_uses=("upload", "normalization"),
        sample_count=64,
        gene_count=_COUNTS_GENE_COUNT,
        expression_scale="raw_counts",
        generator=_full_counts_archive,
        limitations=("Counts require normalization", "Teaching-only synthetic data"),
    ),
    TutorialAsset(
        asset_id="private-upload-validation-lab-v1",
        filename="trace-private-upload-validation-lab-v1.zip",
        title={"en": "Upload validation lab", "es": "Laboratorio de validación de carga"},
        description={"en": "Isolated structural errors, semantic traps, and a valid-with-notices case.", "es": "Errores estructurales aislados, trampas semánticas y un caso válido con avisos."},
        intended_uses=("upload", "validation", "troubleshooting"),
        sample_count=48,
        gene_count=32,
        expression_scale="mixed_by_case",
        generator=_validation_lab_archive,
        limitations=("Intentionally contains invalid files", "Never combine cases into one upload"),
    ),
)
_ASSET_BY_ID = {asset.asset_id: asset for asset in _ASSETS}
_ASSET_BUILD_LOCK = threading.Lock()


def tutorial_asset_catalog() -> dict:
    # Refuse to advertise transcriptome/count assets if the bundled source
    # universes no longer support the exact versioned dimensions below.
    _transcriptome_gene_design()
    return {
        "schema_version": TUTORIAL_ASSET_SCHEMA_VERSION,
        "released_at": TUTORIAL_ASSET_RELEASE,
        "privacy": "All assets are synthetic and contain no patient data.",
        "assets": [asset.public_record() for asset in _ASSETS],
    }


@lru_cache(maxsize=len(_ASSETS))
def _build_tutorial_asset_cached(asset_id: str) -> tuple[bytes, str]:
    asset = _ASSET_BY_ID[asset_id]
    return asset.generator(), asset.filename


def build_tutorial_asset(asset_id: str) -> tuple[bytes, str]:
    if asset_id not in _ASSET_BY_ID:
        raise TutorialAssetNotFound(asset_id)
    # functools.lru_cache is threadsafe for its internal state, but it may call
    # the wrapped function more than once when identical misses race. The
    # archive generator is deliberately held behind one lock so concurrent
    # first downloads coalesce into a single memory-intensive construction.
    with _ASSET_BUILD_LOCK:
        return _build_tutorial_asset_cached(asset_id)
