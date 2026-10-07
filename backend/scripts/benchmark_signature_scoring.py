#!/usr/bin/env python3
"""Reproducible cold-cache benchmark for TRACE signature scoring.

This utility creates a deterministic row-major float32 expression matrix and
runs each pinned rank-based method through the same Python-to-R boundary used
by the service.  It is intentionally independent of patient data.
"""

from __future__ import annotations

import argparse
from array import array
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import time

from app.gsea import ExpressionMatrix, MatrixGene
from app.signature_scoring import run_rank_based_signature_score


METHODS = ("singscore", "ssgsea", "aucell")
BRCA_BENCHMARK_SIGNATURE = (
    ("ESR1", "up"),
    ("PGR", "up"),
    ("GATA3", "up"),
    ("FOXA1", "up"),
    ("XBP1", "up"),
    ("BCL2", "up"),
    ("TFF1", "up"),
    ("TFF3", "up"),
    ("MLPH", "up"),
    ("AGR2", "up"),
    ("EGFR", "down"),
    ("KRT5", "down"),
    ("KRT14", "down"),
    ("KRT17", "down"),
    ("FOXC1", "down"),
    ("ITGA6", "down"),
    ("SOX10", "down"),
    ("TP63", "down"),
    ("CDH3", "down"),
    ("MYC", "down"),
)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_matrix(path: Path, gene_count: int, sample_count: int) -> str:
    digest = sha256()
    with path.open("wb") as handle:
        for gene_index in range(gene_count):
            # The co-prime modular terms give reproducible, non-constant rows
            # without allocating the full matrix in Python memory.
            row = array(
                "f",
                (
                    (
                        ((gene_index * 37 + sample_index * 101) % 1009)
                        / 1009.0
                    )
                    + (gene_index % 17) / 1000.0
                    for sample_index in range(sample_count)
                ),
            )
            if sys.byteorder != "little":
                row.byteswap()
            encoded = row.tobytes()
            handle.write(encoded)
            digest.update(encoded)
    return digest.hexdigest()


def _run_methods(
    *,
    matrix: ExpressionMatrix,
    sample_ids: list[str],
    entries: list[dict[str, object]],
    methods: tuple[str, ...],
    cache_root: Path,
    dataset_identity: dict[str, object],
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for method in methods:
        started = time.perf_counter()
        scores, provenance, warnings = run_rank_based_signature_score(
            matrix=matrix,
            canonical_sample_ids=sample_ids,
            entries=entries,
            method=method,
            cache_root=cache_root / method,
            dataset_identity=dataset_identity,
        )
        elapsed = time.perf_counter() - started
        results.append(
            {
                "method": method,
                "wall_seconds": round(elapsed, 6),
                "package": provenance["engine"]["package"],
                "package_version": provenance["engine"]["version"],
                "score_count": len(scores),
                "finite": all(value == value for value in scores.values()),
                "nonconstant": len(set(scores.values())) > 1,
                "warning_count": len(warnings),
            }
        )
    return results


def benchmark(
    gene_count: int,
    sample_count: int,
    methods: tuple[str, ...],
) -> dict[str, object]:
    sample_ids = [f"S{index:05d}" for index in range(sample_count)]
    genes = [
        MatrixGene(symbol=f"G{index:05d}", row_number=index)
        for index in range(gene_count)
    ]
    entries = [
        {
            "gene_symbol": f"G{index:05d}",
            "resolved_symbol": f"G{index:05d}",
            "direction": "up" if index < 10 else "down",
            "weight": 1.0 if index < 10 else -1.0,
        }
        for index in range(20)
    ]
    with tempfile.TemporaryDirectory(prefix="trace-signature-benchmark-") as raw:
        root = Path(raw)
        matrix_path = root / "expression.float32.bin"
        generated_at = time.perf_counter()
        matrix_sha256 = _write_matrix(matrix_path, gene_count, sample_count)
        generation_seconds = time.perf_counter() - generated_at
        matrix = ExpressionMatrix(
            path=matrix_path,
            sample_ids=sample_ids,
            genes=genes,
            dtype="float32",
            byte_order="little",
            expression_scale="synthetic_benchmark",
            expression_scale_label="Synthetic benchmark",
            source_sha256=matrix_sha256,
        )
        results = _run_methods(
            matrix=matrix,
            sample_ids=sample_ids,
            entries=entries,
            methods=methods,
            cache_root=root / "cache",
            dataset_identity={
                "dataset_id": "synthetic-signature-benchmark",
                "release_id": f"{gene_count}x{sample_count}",
            },
        )
        return {
            "schema_version": "trace-signature-scoring-benchmark-v1",
            "genes": gene_count,
            "samples": sample_count,
            "matrix_entries": gene_count * sample_count,
            "matrix_bytes": matrix_path.stat().st_size,
            "matrix_generation_seconds": round(generation_seconds, 6),
            "methods": results,
        }


def _tcga_primary_sample_ids(barcodes: list[str]) -> list[str]:
    by_patient: dict[str, list[str]] = {}
    for barcode in barcodes:
        fields = barcode.split("-")
        if len(fields) < 4 or fields[3][:2] != "01":
            continue
        by_patient.setdefault("-".join(fields[:3]), []).append(barcode)

    def selection_key(barcode: str) -> tuple[int, int, str]:
        fields = barcode.split("-")
        vial = fields[4] if len(fields) > 4 else ""
        analyte = vial[-1:].upper()
        analyte_rank = {"R": 0, "T": 1, "H": 2}.get(analyte, 8)
        portion = vial[:2]
        portion_rank = int(portion) if portion.isdigit() else 99
        return analyte_rank, portion_rank, barcode

    retained = {
        min(patient_barcodes, key=selection_key)
        for patient_barcodes in by_patient.values()
    }
    return [barcode for barcode in barcodes if barcode in retained]


def benchmark_tcga_brca(
    matrix_dir: Path,
    methods: tuple[str, ...],
) -> dict[str, object]:
    metadata = json.loads((matrix_dir / "metadata.json").read_text())
    barcodes = [str(value) for value in metadata["barcodes"]]
    gene_symbols = [str(value).strip().upper() for value in metadata["genes"]]
    sample_ids = _tcga_primary_sample_ids(barcodes)
    matrix_path = matrix_dir / str(metadata["scales"]["log2_tpm"]["file"])
    hashed_at = time.perf_counter()
    matrix_sha256 = _sha256_file(matrix_path)
    hash_seconds = time.perf_counter() - hashed_at
    matrix = ExpressionMatrix(
        path=matrix_path,
        sample_ids=barcodes,
        genes=[
            MatrixGene(symbol=symbol, row_number=index)
            for index, symbol in enumerate(gene_symbols)
        ],
        dtype="float32",
        byte_order="little",
        expression_scale="log2_tpm",
        expression_scale_label="log2(TPM + 1)",
        source_sha256=matrix_sha256,
    )
    universe = set(gene_symbols)
    absent = [gene for gene, _ in BRCA_BENCHMARK_SIGNATURE if gene not in universe]
    if absent:
        raise ValueError("BRCA benchmark genes missing: " + ", ".join(absent))
    entries = [
        {
            "gene_symbol": gene,
            "resolved_symbol": gene,
            "direction": direction,
            "weight": 1.0 if direction == "up" else -1.0,
        }
        for gene, direction in BRCA_BENCHMARK_SIGNATURE
    ]
    with tempfile.TemporaryDirectory(prefix="trace-brca-signature-benchmark-") as raw:
        results = _run_methods(
            matrix=matrix,
            sample_ids=sample_ids,
            entries=entries,
            methods=methods,
            cache_root=Path(raw) / "cache",
            dataset_identity={
                "dataset_id": "TCGA-BRCA",
                "release_id": "local-frozen-matrix",
                "population": "primary_solid",
            },
        )
    return {
        "schema_version": "trace-signature-scoring-benchmark-v1",
        "dataset": "TCGA-BRCA",
        "population": "primary_solid",
        "one_sample_per_patient": True,
        "genes": len(gene_symbols),
        "source_samples": len(barcodes),
        "canonical_samples": len(sample_ids),
        "matrix_entries_scored": len(gene_symbols) * len(sample_ids),
        "source_matrix_bytes": matrix_path.stat().st_size,
        "source_matrix_hash_seconds": round(hash_seconds, 6),
        "signature_genes": len(entries),
        "methods": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--genes", type=int, default=20_000)
    parser.add_argument("--samples", type=int)
    parser.add_argument("--tcga-brca-matrix-dir", type=Path)
    parser.add_argument(
        "--methods",
        nargs="+",
        choices=METHODS,
        default=list(METHODS),
    )
    arguments = parser.parse_args()
    methods = tuple(arguments.methods)
    if arguments.tcga_brca_matrix_dir is not None:
        result = benchmark_tcga_brca(arguments.tcga_brca_matrix_dir, methods)
    else:
        if arguments.samples is None:
            parser.error("--samples is required for a synthetic benchmark.")
        if arguments.genes < 1_000 or arguments.samples < 2:
            parser.error("Use at least 1,000 genes and two samples.")
        result = benchmark(arguments.genes, arguments.samples, methods)
    print(
        json.dumps(
            result,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
