import csv
import json
import math
from array import array
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Sample


class GeneNotFoundError(ValueError):
    pass


EXPRESSION_SCALES: dict[str, dict[str, str]] = {
    "log2_tpm": {
        "label": "log2(TPM + 1)",
        "source": "gdc_cache augmented STAR-count TSV",
        "note": "Recommended normalized RNA-seq scale for single-gene survival analysis.",
    },
    "log2_cpm": {
        "label": "log2(CPM + 1)",
        "source": "Computed from count_matrix.tsv unstranded counts",
        "note": "Library-size normalized fallback when working from raw counts.",
    },
    "log2_fpkm": {
        "label": "log2(FPKM + 1)",
        "source": "gdc_cache augmented STAR-count TSV",
        "note": "Log-transformed FPKM from the original GDC files.",
    },
    "log2_fpkm_uq": {
        "label": "log2(FPKM-UQ + 1)",
        "source": "gdc_cache augmented STAR-count TSV",
        "note": "Log-transformed upper-quartile FPKM from the original GDC files.",
    },
}

GDC_CACHE_SCALE_COLUMNS = {
    "log2_tpm": "tpm_unstranded",
    "log2_fpkm": "fpkm_unstranded",
    "log2_fpkm_uq": "fpkm_uq_unstranded",
}
FINGERPRINT_SIZES = (256, 640, 1200)


def expression_scale_options() -> list[dict[str, str]]:
    return [
        {"value": value, **metadata}
        for value, metadata in EXPRESSION_SCALES.items()
    ]


def expression_scale_label(scale: str) -> str:
    return EXPRESSION_SCALES.get(scale, EXPRESSION_SCALES["log2_tpm"])["label"]


def get_expression_for_gene(
    db: Session,
    tcga_data_dir: Path,
    derived_expression_dir: Path,
    cohort_id: str,
    gene_symbol: str,
    expression_scale: str,
) -> dict[str, float]:
    if expression_scale not in EXPRESSION_SCALES:
        raise ValueError(f"Unsupported expression scale: {expression_scale}")
    if expression_scale in GDC_CACHE_SCALE_COLUMNS:
        return get_gdc_cached_expression(
            tcga_data_dir,
            derived_expression_dir,
            cohort_id,
            gene_symbol,
            expression_scale,
        )
    return get_count_matrix_expression(db, tcga_data_dir, cohort_id, gene_symbol, expression_scale)


def get_count_matrix_expression(
    db: Session,
    tcga_data_dir: Path,
    cohort_id: str,
    gene_symbol: str,
    expression_scale: str,
) -> dict[str, float]:
    samples = db.scalars(select(Sample).where(Sample.cohort == cohort_id)).all()
    if not samples:
        return {}

    if expression_scale != "log2_cpm":
        raise ValueError(f"Unsupported count-matrix expression scale: {expression_scale}")

    library_sizes = {sample.barcode: sample.library_size for sample in samples if sample.library_size and sample.library_size > 0}
    need_library_sizes = len(library_sizes) < len(samples)
    matrix_path = tcga_data_dir / cohort_id / "count_matrix.tsv"
    if not matrix_path.exists():
        raise FileNotFoundError(f"count_matrix.tsv not found for {cohort_id}")

    target_counts, _, computed_sizes = read_count_matrix_gene(
        matrix_path,
        gene_symbol,
        compute_library_sizes=need_library_sizes,
    )

    if target_counts is None:
        raise GeneNotFoundError(f"Gene {gene_symbol} not found in {cohort_id}")

    if need_library_sizes:
        library_sizes = ensure_count_matrix_library_sizes(db, tcga_data_dir, cohort_id, computed_sizes)

    expression: dict[str, float] = {}
    for barcode, count in target_counts.items():
        lib_size = library_sizes.get(barcode)
        if lib_size is None or lib_size <= 0:
            continue
        expression[barcode] = math.log2((count / lib_size) * 1_000_000.0 + 1.0)
    return expression


def ensure_count_matrix_library_sizes(
    db: Session,
    tcga_data_dir: Path,
    cohort_id: str,
    precomputed_sizes: dict[str, float] | None = None,
) -> dict[str, float]:
    samples = db.scalars(select(Sample).where(Sample.cohort == cohort_id)).all()
    if not samples:
        return {}

    existing = {
        sample.barcode: sample.library_size
        for sample in samples
        if sample.library_size is not None and sample.library_size > 0
    }
    if len(existing) == len(samples):
        return {barcode: float(value) for barcode, value in existing.items()}

    matrix_path = tcga_data_dir / cohort_id / "count_matrix.tsv"
    if not matrix_path.exists():
        raise FileNotFoundError(f"count_matrix.tsv not found for {cohort_id}")

    library_sizes = precomputed_sizes or read_count_matrix_library_sizes(matrix_path)
    for sample in samples:
        sample.library_size = library_sizes.get(sample.barcode)
    db.commit()
    return {
        barcode: float(size)
        for barcode, size in library_sizes.items()
        if size is not None and size > 0
    }


def read_count_matrix_library_sizes(matrix_path: Path) -> dict[str, float]:
    with matrix_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader)
        barcodes = header[1:]
        library_sizes = {barcode: 0.0 for barcode in barcodes}
        for row in reader:
            if not row:
                continue
            for barcode, raw in zip(barcodes, row[1:], strict=False):
                library_sizes[barcode] += _to_float(raw)
    return library_sizes


def get_gdc_cached_expression(
    tcga_data_dir: Path,
    derived_expression_dir: Path,
    cohort_id: str,
    gene_symbol: str,
    expression_scale: str,
) -> dict[str, float]:
    matrix_expression = read_gdc_expression_matrix_cache(derived_expression_dir, cohort_id, gene_symbol, expression_scale)
    if matrix_expression is not None:
        return matrix_expression

    cache = load_gene_cache(derived_expression_dir, cohort_id, gene_symbol)
    source_column = GDC_CACHE_SCALE_COLUMNS[expression_scale]
    if cache and source_column in cache.get("values", {}):
        return log2p_values(cache["values"][source_column])

    gene_cache = build_gene_cache(tcga_data_dir, derived_expression_dir, cohort_id, gene_symbol)
    return log2p_values(gene_cache["values"][source_column])


def build_gene_cache(
    tcga_data_dir: Path,
    derived_expression_dir: Path,
    cohort_id: str,
    gene_symbol: str,
) -> dict[str, Any]:
    matrix_path = tcga_data_dir / cohort_id / "count_matrix.tsv"
    target_counts, barcodes, _ = read_count_matrix_gene(matrix_path, gene_symbol)
    if target_counts is None:
        raise GeneNotFoundError(f"Gene {gene_symbol} not found in {cohort_id}")

    file_map = load_or_build_cache_file_map(tcga_data_dir, derived_expression_dir, cohort_id)
    missing_barcodes = [barcode for barcode in barcodes if barcode not in file_map]
    if missing_barcodes:
        raise ValueError(f"GDC cache file map is missing {len(missing_barcodes)} sample barcodes for {cohort_id}.")

    target = gene_symbol.strip().upper()
    candidates: dict[str, dict[str, dict[str, float]]] = {}
    for barcode in barcodes:
        cache_file = Path(file_map[barcode])
        rows = read_gdc_gene_rows(cache_file, target)
        for row in rows:
            gene_id = row["gene_id"]
            values = candidates.setdefault(
                gene_id,
                {
                    "unstranded": {},
                    "tpm_unstranded": {},
                    "fpkm_unstranded": {},
                    "fpkm_uq_unstranded": {},
                },
            )
            for key in values:
                values[key][barcode] = row[key]

    if not candidates:
        raise GeneNotFoundError(f"Gene {gene_symbol} not found in cached GDC STAR-count files for {cohort_id}")

    selected_gene_id = select_matching_gene_id(candidates, target_counts, barcodes, gene_symbol, cohort_id)
    selected = candidates[selected_gene_id]
    gene_cache = {
        "cohort": cohort_id,
        "gene_symbol": target,
        "gene_id": selected_gene_id,
        "values": {
            "tpm_unstranded": selected["tpm_unstranded"],
            "fpkm_unstranded": selected["fpkm_unstranded"],
            "fpkm_uq_unstranded": selected["fpkm_uq_unstranded"],
        },
    }
    write_gene_cache(derived_expression_dir, cohort_id, target, gene_cache)
    return gene_cache


def ensure_gdc_expression_matrix_cache(
    tcga_data_dir: Path,
    derived_expression_dir: Path,
    cohort_id: str,
) -> dict[str, Any]:
    existing = load_gdc_expression_matrix_metadata(derived_expression_dir, cohort_id)
    if existing and gdc_expression_matrix_files_exist(derived_expression_dir, cohort_id, existing):
        return summarize_gdc_expression_matrix_metadata(existing)

    matrix_path = tcga_data_dir / cohort_id / "count_matrix.tsv"
    file_map = load_or_build_cache_file_map(tcga_data_dir, derived_expression_dir, cohort_id)
    if not file_map:
        raise ValueError(f"GDC cache file map is empty for {cohort_id}.")

    reference_file = Path(next(iter(file_map.values())))
    unique_symbols = unique_gdc_symbols(reference_file)
    genes, barcodes = count_matrix_genes_and_barcodes(matrix_path, unique_symbols)
    missing_barcodes = [barcode for barcode in barcodes if barcode not in file_map]
    if missing_barcodes:
        raise ValueError(f"GDC cache file map is missing {len(missing_barcodes)} sample barcodes for {cohort_id}.")

    gene_count = len(genes)
    sample_count = len(barcodes)
    gene_to_row = {gene: index for index, gene in enumerate(genes)}
    total_values = gene_count * sample_count
    values_by_scale = {
        scale: array("f", [0.0]) * total_values
        for scale in GDC_CACHE_SCALE_COLUMNS
    }

    for sample_index, barcode in enumerate(barcodes):
        cache_file = Path(file_map[barcode])
        with cache_file.open(newline="", encoding="utf-8", errors="replace") as handle:
            reader = csv.DictReader(skip_comment_lines(handle), delimiter="\t")
            for row in reader:
                symbol = (row.get("gene_name") or "").strip().upper()
                row_index = gene_to_row.get(symbol)
                if row_index is None:
                    continue
                offset = row_index * sample_count + sample_index
                for scale, source_column in GDC_CACHE_SCALE_COLUMNS.items():
                    values_by_scale[scale][offset] = math.log2(_to_float(row.get(source_column, "")) + 1.0)

    cache_dir = gdc_expression_matrix_dir(derived_expression_dir, cohort_id)
    cache_dir.mkdir(parents=True, exist_ok=True)
    scales: dict[str, dict[str, Any]] = {}
    for scale, values in values_by_scale.items():
        file_name = f"{scale}.float32.bin"
        tmp_path = cache_dir / f"{file_name}.tmp"
        final_path = cache_dir / file_name
        with tmp_path.open("wb") as handle:
            values.tofile(handle)
        tmp_path.replace(final_path)
        scales[scale] = {
            "file": file_name,
            "source_column": GDC_CACHE_SCALE_COLUMNS[scale],
        }

    metadata = {
        "cohort": cohort_id,
        "status": "ready",
        "dtype": "float32_native",
        "layout": "row_major_gene_by_sample",
        "gene_count": gene_count,
        "sample_count": sample_count,
        "genes": genes,
        "gene_to_row": gene_to_row,
        "barcodes": barcodes,
        "scales": scales,
    }
    write_gdc_expression_matrix_metadata(derived_expression_dir, cohort_id, metadata)
    return summarize_gdc_expression_matrix_metadata(metadata)


def read_gdc_expression_matrix_cache(
    derived_expression_dir: Path,
    cohort_id: str,
    gene_symbol: str,
    expression_scale: str,
) -> dict[str, float] | None:
    metadata = load_gdc_expression_matrix_metadata(derived_expression_dir, cohort_id)
    if not metadata or metadata.get("status") != "ready":
        return None
    scale_info = (metadata.get("scales") or {}).get(expression_scale)
    if scale_info is None:
        return None
    row_index = (metadata.get("gene_to_row") or {}).get(gene_symbol.strip().upper())
    if row_index is None:
        return None

    barcodes = metadata.get("barcodes") or []
    sample_count = int(metadata.get("sample_count") or len(barcodes))
    path = gdc_expression_matrix_dir(derived_expression_dir, cohort_id) / scale_info["file"]
    if not path.exists():
        return None

    values = array("f")
    with path.open("rb") as handle:
        handle.seek(int(row_index) * sample_count * values.itemsize)
        values.fromfile(handle, sample_count)
    return {
        barcode: float(value)
        for barcode, value in zip(barcodes, values, strict=False)
    }


def count_matrix_genes_and_barcodes(matrix_path: Path, allowed_symbols: set[str]) -> tuple[list[str], list[str]]:
    genes: list[str] = []
    seen: set[str] = set()
    with matrix_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader)
        barcodes = header[1:]
        for row in reader:
            if not row:
                continue
            symbol = row[0].strip().upper()
            if not symbol or symbol in seen or symbol not in allowed_symbols:
                continue
            seen.add(symbol)
            genes.append(symbol)
    return genes, barcodes


def load_gdc_expression_matrix_metadata(derived_expression_dir: Path, cohort_id: str) -> dict[str, Any] | None:
    path = gdc_expression_matrix_metadata_path(derived_expression_dir, cohort_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_gdc_expression_matrix_metadata(
    derived_expression_dir: Path,
    cohort_id: str,
    metadata: dict[str, Any],
) -> None:
    path = gdc_expression_matrix_metadata_path(derived_expression_dir, cohort_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")


def gdc_expression_matrix_files_exist(
    derived_expression_dir: Path,
    cohort_id: str,
    metadata: dict[str, Any],
) -> bool:
    cache_dir = gdc_expression_matrix_dir(derived_expression_dir, cohort_id)
    sample_count = int(metadata.get("sample_count") or 0)
    gene_count = int(metadata.get("gene_count") or 0)
    scales = metadata.get("scales") or {}
    if not sample_count or not gene_count or set(scales) != set(GDC_CACHE_SCALE_COLUMNS):
        return False
    expected_size = sample_count * gene_count * array("f").itemsize
    for scale_info in scales.values():
        path = cache_dir / scale_info["file"]
        if not path.exists() or path.stat().st_size != expected_size:
            return False
    return True


def summarize_gdc_expression_matrix_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": metadata.get("status"),
        "gene_count": metadata.get("gene_count"),
        "sample_count": metadata.get("sample_count"),
        "scales": sorted((metadata.get("scales") or {}).keys()),
    }


def gdc_expression_matrix_dir(derived_expression_dir: Path, cohort_id: str) -> Path:
    return derived_expression_dir / "matrices" / cohort_id


def gdc_expression_matrix_metadata_path(derived_expression_dir: Path, cohort_id: str) -> Path:
    return gdc_expression_matrix_dir(derived_expression_dir, cohort_id) / "metadata.json"


def select_matching_gene_id(
    candidates: dict[str, dict[str, dict[str, float]]],
    target_counts: dict[str, float],
    barcodes: list[str],
    gene_symbol: str,
    cohort_id: str,
) -> str:
    perfect: list[str] = []
    scored: list[tuple[int, str]] = []
    for gene_id, values in candidates.items():
        matches = sum(
            count_key(values["unstranded"].get(barcode)) == count_key(target_counts.get(barcode))
            for barcode in barcodes
        )
        scored.append((matches, gene_id))
        if matches == len(barcodes):
            perfect.append(gene_id)
    if len(perfect) == 1:
        return perfect[0]
    if len(perfect) > 1:
        return sorted(perfect)[0]

    best_matches, best_gene_id = max(scored, key=lambda item: item[0])
    if best_matches >= max(10, int(len(barcodes) * 0.98)):
        return best_gene_id
    raise ValueError(
        f"Could not align cached GDC rows for {gene_symbol} in {cohort_id}: "
        f"best candidate matched {best_matches}/{len(barcodes)} samples."
    )


def read_count_matrix_gene(
    matrix_path: Path,
    gene_symbol: str,
    compute_library_sizes: bool = False,
) -> tuple[dict[str, float] | None, list[str], dict[str, float]]:
    target = gene_symbol.strip().upper()
    target_counts: dict[str, float] | None = None
    computed_sizes: dict[str, float] = {}
    with matrix_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader)
        barcodes = header[1:]
        if compute_library_sizes:
            computed_sizes = {barcode: 0.0 for barcode in barcodes}
        for row in reader:
            if not row:
                continue
            symbol = row[0].strip().upper()
            values = row[1:]
            if compute_library_sizes:
                for barcode, raw in zip(barcodes, values, strict=False):
                    computed_sizes[barcode] += _to_float(raw)
            if symbol == target and target_counts is None:
                target_counts = {barcode: _to_float(raw) for barcode, raw in zip(barcodes, values, strict=False)}
                if not compute_library_sizes:
                    break
    return target_counts, barcodes, computed_sizes


def load_or_build_cache_file_map(tcga_data_dir: Path, derived_expression_dir: Path, cohort_id: str) -> dict[str, str]:
    map_path = derived_expression_dir / "maps" / f"{cohort_id}.json"
    if map_path.exists():
        payload = json.loads(map_path.read_text(encoding="utf-8"))
        mapping = payload.get("barcode_to_file", {})
        if mapping and all(Path(path).exists() for path in mapping.values()):
            return mapping

    mapping = build_cache_file_map(tcga_data_dir, cohort_id)
    map_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_text(
        json.dumps({"cohort": cohort_id, "barcode_to_file": mapping}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return mapping


def build_cache_file_map(tcga_data_dir: Path, cohort_id: str) -> dict[str, str]:
    cache_files = list_cache_gene_files(tcga_data_dir, cohort_id)
    if not cache_files:
        raise FileNotFoundError(f"No cached GDC STAR-count files found for {cohort_id}")

    matrix_path = tcga_data_dir / cohort_id / "count_matrix.tsv"
    last_error = "No fingerprint attempt was executed."
    for fingerprint_size in FINGERPRINT_SIZES:
        selected_genes, fingerprints = count_matrix_fingerprints(matrix_path, cache_files[0], fingerprint_size)
        if not selected_genes:
            continue
        duplicates = duplicate_fingerprints(fingerprints)
        if duplicates:
            last_error = f"{len(duplicates)} duplicate count-matrix fingerprints with {fingerprint_size} genes."
            continue
        barcode_by_fingerprint = {fingerprint: barcode for barcode, fingerprint in fingerprints.items()}
        mapping: dict[str, str] = {}
        unmatched = 0
        for cache_file in cache_files:
            fingerprint = gdc_file_fingerprint(cache_file, selected_genes)
            barcode = barcode_by_fingerprint.get(fingerprint)
            if barcode is None:
                unmatched += 1
                continue
            mapping[barcode] = str(cache_file)
        if len(mapping) == len(fingerprints):
            return mapping
        last_error = (
            f"Matched {len(mapping)}/{len(fingerprints)} cache files with "
            f"{fingerprint_size} fingerprint genes; unmatched files: {unmatched}."
        )
    raise ValueError(f"Could not map GDC cache files to TCGA barcodes for {cohort_id}. {last_error}")


def count_matrix_fingerprints(
    matrix_path: Path,
    reference_cache_file: Path,
    fingerprint_size: int,
) -> tuple[list[str], dict[str, tuple[str, ...]]]:
    unique_symbols = unique_gdc_symbols(reference_cache_file)
    selected_genes: list[str] = []
    values_by_gene: list[list[str]] = []
    barcodes: list[str] = []

    with matrix_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader)
        barcodes = header[1:]
        for row in reader:
            if not row:
                continue
            symbol = row[0].strip().upper()
            if symbol not in unique_symbols:
                continue
            values = [count_key(value) for value in row[1:]]
            if len(set(values)) < 2:
                continue
            selected_genes.append(symbol)
            values_by_gene.append(values)
            if len(selected_genes) >= fingerprint_size:
                break

    fingerprints = {
        barcode: tuple(gene_values[index] for gene_values in values_by_gene)
        for index, barcode in enumerate(barcodes)
    }
    return selected_genes, fingerprints


def unique_gdc_symbols(cache_file: Path) -> set[str]:
    counts: dict[str, int] = {}
    with cache_file.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(skip_comment_lines(handle), delimiter="\t")
        for row in reader:
            symbol = (row.get("gene_name") or "").strip().upper()
            if not symbol:
                continue
            counts[symbol] = counts.get(symbol, 0) + 1
    return {symbol for symbol, count in counts.items() if count == 1}


def gdc_file_fingerprint(cache_file: Path, selected_genes: list[str]) -> tuple[str, ...]:
    wanted = set(selected_genes)
    values: dict[str, str] = {}
    with cache_file.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(skip_comment_lines(handle), delimiter="\t")
        for row in reader:
            symbol = (row.get("gene_name") or "").strip().upper()
            if symbol in wanted:
                values[symbol] = count_key(row.get("unstranded"))
                if len(values) == len(wanted):
                    break
    return tuple(values.get(symbol, "") for symbol in selected_genes)


def read_gdc_gene_rows(cache_file: Path, target_symbol: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with cache_file.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(skip_comment_lines(handle), delimiter="\t")
        for row in reader:
            symbol = (row.get("gene_name") or "").strip().upper()
            if symbol != target_symbol:
                continue
            rows.append(
                {
                    "gene_id": strip_ensembl_version(row.get("gene_id") or ""),
                    "unstranded": _to_float(row.get("unstranded", "")),
                    "tpm_unstranded": _to_float(row.get("tpm_unstranded", "")),
                    "fpkm_unstranded": _to_float(row.get("fpkm_unstranded", "")),
                    "fpkm_uq_unstranded": _to_float(row.get("fpkm_uq_unstranded", "")),
                }
            )
    return rows


def skip_comment_lines(handle):
    for line in handle:
        if line.startswith("#"):
            continue
        yield line


def list_cache_gene_files(tcga_data_dir: Path, cohort_id: str) -> list[Path]:
    cache_dir = tcga_data_dir / "gdc_cache" / cohort_id
    return sorted(cache_dir.glob("**/*.rna_seq.augmented_star_gene_counts.tsv"))


def load_gene_cache(derived_expression_dir: Path, cohort_id: str, gene_symbol: str) -> dict[str, Any] | None:
    path = gene_cache_path(derived_expression_dir, cohort_id, gene_symbol)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_gene_cache(derived_expression_dir: Path, cohort_id: str, gene_symbol: str, payload: dict[str, Any]) -> None:
    path = gene_cache_path(derived_expression_dir, cohort_id, gene_symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def gene_cache_path(derived_expression_dir: Path, cohort_id: str, gene_symbol: str) -> Path:
    safe_gene = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in gene_symbol.upper())
    return derived_expression_dir / "gene_cache" / cohort_id / f"{safe_gene}.json"


def duplicate_fingerprints(fingerprints: dict[str, tuple[str, ...]]) -> set[tuple[str, ...]]:
    seen: set[tuple[str, ...]] = set()
    duplicates: set[tuple[str, ...]] = set()
    for fingerprint in fingerprints.values():
        if fingerprint in seen:
            duplicates.add(fingerprint)
        seen.add(fingerprint)
    return duplicates


def count_key(value: Any) -> str:
    number = _to_float(value)
    return str(int(round(number)))


def log2p_values(values_by_barcode: dict[str, Any]) -> dict[str, float]:
    return {
        barcode: math.log2(_to_float(value) + 1.0)
        for barcode, value in values_by_barcode.items()
    }


def strip_ensembl_version(gene_id: str) -> str:
    return gene_id.split(".", 1)[0]


def _to_float(value: Any) -> float:
    if value is None or value == "" or value == "NA":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
