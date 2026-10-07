from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from app import file_lock as fcntl
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterable

from app.gsea import ExpressionMatrix
from app.repository.capabilities import (
    RANK_SIGNATURE_MAXIMUM_MATRIX_ENTRIES,
    RANK_SIGNATURE_MINIMUM_GENES,
)


SIGNATURE_SCORING_SCHEMA = "trace-signature-scoring-v2"
SIGNATURE_SCORING_ENGINE_SCHEMA = "trace-bioconductor-signature-engine-v1"
SIGNATURE_SCORING_CONTRACT_VERSION = "bioconductor-single-sample-scoring-v2.0"
RANK_BASED_METHODS = frozenset({"singscore", "ssgsea", "aucell"})
EXPECTED_PACKAGE_VERSIONS = {
    "singscore": "1.26.0",
    "ssgsea": "2.0.7",
    "aucell": "1.28.0",
}
ENGINE_PACKAGES = {
    "singscore": "singscore",
    "ssgsea": "GSVA",
    "aucell": "AUCell",
}
SIGNATURE_METHOD_LABELS = {
    "single": "Single gene",
    "mean": "Mean",
    "zscore": "Z-score",
    "weighted": "Weighted",
    "singscore": "singscore",
    "ssgsea": "ssGSEA",
    "aucell": "AUCell",
}
MIN_TRANSCRIPTOME_GENES = RANK_SIGNATURE_MINIMUM_GENES
MAX_MATRIX_ENTRIES = RANK_SIGNATURE_MAXIMUM_MATRIX_ENTRIES
SSGSEA_ALPHA = 0.25
SSGSEA_MIN_SIZE = 2
AUCELL_TOP_RANK_FRACTION = 0.05
AUCELL_SEED = 1


class SignatureScoringTimeout(RuntimeError):
    """Safe, actionable timeout that can be returned by the job worker."""


def r_binary_endian(byte_order: str) -> str:
    """Translate TRACE matrix byte order to a value accepted by R readBin."""

    normalized = str(byte_order or "").strip().casefold()
    if normalized in {"little", "big"}:
        return normalized
    if normalized == "native":
        return sys.byteorder
    raise ValueError(f"Unsupported expression matrix byte order: {byte_order}.")


def signature_method_label(method: str) -> str:
    """Return the publication-facing spelling for a scoring method."""

    normalized = str(method or "").strip().casefold()
    return SIGNATURE_METHOD_LABELS.get(normalized, normalized or "Signature")


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def _exclusive_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def scoring_parameters(method: str, universe_n: int) -> dict[str, Any]:
    if method == "singscore":
        return {
            "rank_ties_method": "min",
            "center_score": True,
            "known_direction": True,
            "direction_combination": "up_minus_down",
        }
    if method == "ssgsea":
        return {
            "alpha": SSGSEA_ALPHA,
            "normalize": False,
            "min_size": SSGSEA_MIN_SIZE,
            "max_size": "Inf",
            "check_na": "yes",
            "missing_value_policy": "all.obs",
            "direction_combination": "up_minus_down",
        }
    if method == "aucell":
        return {
            "auc_max_rank": max(
                1, math.ceil(AUCELL_TOP_RANK_FRACTION * universe_n)
            ),
            "auc_max_rank_fraction": AUCELL_TOP_RANK_FRACTION,
            "normalize_auc": True,
            "split_by_blocks": False,
            "keep_zeroes_as_na": False,
            "tie_seed_base": AUCELL_SEED,
            "tie_seed_derivation": (
                "sha256('<contract>|<base>|<stable_sample_id>') first 8 hex, "
                "modulo 2147483646, plus 1"
            ),
            "tie_seed_scope": "stable per sample",
            "direction_combination": "up_minus_down",
        }
    raise ValueError(f"Unsupported rank-based signature method: {method}.")


def aucell_sample_seed(sample_id: str) -> int:
    digest = sha256(
        (
            f"{SIGNATURE_SCORING_CONTRACT_VERSION}|"
            f"{AUCELL_SEED}|{sample_id}"
        ).encode("utf-8")
    ).hexdigest()
    return int(digest[:8], 16) % 2_147_483_646 + 1


def effective_direction(entry: dict[str, Any]) -> str:
    explicit = str(entry.get("direction") or "").strip().casefold()
    if explicit in {"up", "down"}:
        return explicit
    return "down" if float(entry.get("weight", 1.0)) < 0 else "up"


def frozen_gene_universe(matrix: ExpressionMatrix) -> dict[str, Any]:
    """Return the deterministic, first-row-wins feature universe."""

    seen: set[str] = set()
    genes: list[dict[str, Any]] = []
    duplicate_symbols: list[str] = []
    for gene in sorted(matrix.genes, key=lambda item: int(item.row_number)):
        symbol = str(gene.symbol or "").strip().upper()
        if not symbol:
            continue
        if symbol in seen:
            duplicate_symbols.append(symbol)
            continue
        seen.add(symbol)
        genes.append({"symbol": symbol, "row_number": int(gene.row_number)})
    if len(genes) < MIN_TRANSCRIPTOME_GENES:
        raise ValueError(
            "Rank-based signature scoring requires a broad "
            f"expression layer with at least {MIN_TRANSCRIPTOME_GENES:,} "
            f"unique genes; this layer contains {len(genes):,}."
        )
    return {
        "genes": genes,
        "gene_count": len(genes),
        "sha256": _stable_hash([item["symbol"] for item in genes]),
        "duplicate_symbol_count": len(duplicate_symbols),
        "duplicate_symbols_sha256": (
            _stable_hash(sorted(duplicate_symbols))
            if duplicate_symbols
            else None
        ),
        "duplicate_policy": "first matrix row by row_number",
    }


def validate_signature_membership(
    *,
    method: str,
    entries: list[dict[str, Any]],
    universe_symbols: set[str],
) -> tuple[list[str], list[str]]:
    if method not in RANK_BASED_METHODS:
        raise ValueError(f"Unsupported rank-based signature method: {method}.")
    if len(entries) < 2:
        raise ValueError(f"{method} signatures require at least two genes.")
    up: list[str] = []
    down: list[str] = []
    missing: list[str] = []
    seen: dict[str, str] = {}
    for entry in entries:
        symbol = str(entry.get("resolved_symbol") or "").strip().upper()
        if not symbol:
            missing.append(str(entry.get("gene_symbol") or "").strip().upper())
            continue
        direction = effective_direction(entry)
        previous = seen.get(symbol)
        if previous is not None:
            if previous != direction:
                raise ValueError(
                    f"Gene {symbol} appears in both up and down signature components."
                )
            continue
        seen[symbol] = direction
        if symbol not in universe_symbols:
            missing.append(symbol)
        elif direction == "down":
            down.append(symbol)
        else:
            up.append(symbol)
    if missing:
        raise ValueError(
            "Rank-based signature scoring failed closed because the frozen "
            "expression universe is missing: " + ", ".join(sorted(set(missing))) + "."
        )
    if len(up) + len(down) < 2:
        raise ValueError(
            "Rank-based signature scoring requires at least two distinct resolved genes."
        )
    if method == "ssgsea":
        too_small = [
            label
            for label, genes in (("up", up), ("down", down))
            if genes and len(genes) < SSGSEA_MIN_SIZE
        ]
        if too_small:
            raise ValueError(
                "ssGSEA requires at least two genes in each non-empty "
                f"directional component; undersized component(s): {', '.join(too_small)}."
            )
    return up, down


def _validate_source_matrix(
    matrix: ExpressionMatrix,
    *,
    gene_rows: Iterable[int],
) -> int:
    if matrix.dtype != "float32":
        raise ValueError(
            "Rank-based signature scoring currently requires a float32 "
            "expression matrix."
        )
    if not matrix.path.is_file():
        raise FileNotFoundError(
            f"The expression matrix is unavailable: {matrix.path}."
        )
    sample_count = len(matrix.sample_ids)
    if sample_count == 0:
        raise ValueError("The expression matrix contains no samples.")
    row_bytes = sample_count * 4
    file_size = matrix.path.stat().st_size
    if file_size % row_bytes != 0:
        raise ValueError("The expression matrix has an invalid binary size.")
    source_row_count = file_size // row_bytes
    if any(row < 0 or row >= source_row_count for row in gene_rows):
        raise ValueError("The expression matrix gene index is out of bounds.")
    return int(source_row_count)


def _validated_scores(
    payload: Any, *, method: str, sample_ids: list[str], cache_key: str,
) -> tuple[dict[str, float], dict[str, dict[str, float]], str]:
    if not isinstance(payload, dict) or payload.get("schema_version") != SIGNATURE_SCORING_ENGINE_SCHEMA:
        raise RuntimeError("The signature-scoring engine returned an unknown schema.")
    if payload.get("cache_identity_sha256") != cache_key:
        raise RuntimeError("The signature-scoring cache identity does not match.")
    if payload.get("method") != method:
        raise RuntimeError("The signature-scoring engine returned a different method than requested.")
    if payload.get("package") != ENGINE_PACKAGES[method]:
        raise RuntimeError("The signature-scoring engine returned an unexpected package identity.")
    version = str(payload.get("package_version") or "")
    if version != EXPECTED_PACKAGE_VERSIONS[method]:
        raise RuntimeError(
            f"{method} returned package version {version or '<missing>'}; "
            f"expected {EXPECTED_PACKAGE_VERSIONS[method]}."
        )
    rows = payload.get("scores")
    if not isinstance(rows, list):
        raise RuntimeError("The signature-scoring engine returned invalid scores.")
    expected = set(sample_ids)
    scores: dict[str, float] = {}
    components: dict[str, dict[str, float]] = {}
    for row in rows:
        try:
            sample_id = str(row.get("sample_id") or "")
            values = [float(row[key]) for key in ("score", "up_score", "down_score")]
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
            raise RuntimeError("The signature-scoring engine returned invalid scores.") from exc
        if sample_id in scores or sample_id not in expected or not all(map(math.isfinite, values)):
            raise RuntimeError("The signature-scoring engine returned invalid scores.")
        scores[sample_id] = values[0]
        components[sample_id] = {"up_score": values[1], "down_score": values[2]}
    if set(scores) != expected:
        raise RuntimeError("The signature-scoring engine did not return every canonical sample.")
    return scores, components, version


def run_rank_based_signature_score(
    *,
    matrix: ExpressionMatrix,
    canonical_sample_ids: list[str],
    entries: list[dict[str, Any]],
    method: str,
    cache_root: Path,
    dataset_identity: dict[str, Any],
    resolution_summary: dict[str, Any] | None = None,
    r_script_path: Path | None = None,
) -> tuple[dict[str, float], dict[str, Any], list[str]]:
    """Score a signature once on a release's canonical molecular population."""

    if method not in RANK_BASED_METHODS:
        raise ValueError(f"Unsupported rank-based signature method: {method}.")
    if len(canonical_sample_ids) < 2:
        raise ValueError(
            "Rank-based signature scoring requires at least two canonical samples."
        )
    if len(canonical_sample_ids) != len(set(canonical_sample_ids)):
        raise ValueError("Canonical signature-scoring sample IDs must be unique.")

    sample_index = {sample_id: index for index, sample_id in enumerate(matrix.sample_ids)}
    missing_samples = [
        sample_id for sample_id in canonical_sample_ids if sample_id not in sample_index
    ]
    if missing_samples:
        raise ValueError(
            "The canonical molecular population contains samples absent from "
            "the frozen expression matrix."
        )
    canonical_sample_set = set(canonical_sample_ids)
    ordered_sample_ids = [
        sample_id
        for sample_id in matrix.sample_ids
        if sample_id in canonical_sample_set
    ]
    universe = frozen_gene_universe(matrix)
    universe_symbols = {item["symbol"] for item in universe["genes"]}
    up_genes, down_genes = validate_signature_membership(
        method=method,
        entries=entries,
        universe_symbols=universe_symbols,
    )
    source_row_count = _validate_source_matrix(
        matrix,
        gene_rows=(item["row_number"] for item in universe["genes"]),
    )
    if universe["gene_count"] * len(ordered_sample_ids) > MAX_MATRIX_ENTRIES:
        raise ValueError(
            "Rank-based signature scoring exceeds the "
            f"{MAX_MATRIX_ENTRIES:,}-entry limit for the canonical population."
        )

    script_path = (
        r_script_path
        or Path(__file__).resolve().parent.parent / "scripts" / "signature_scoring.R"
    ).resolve()
    if not script_path.is_file():
        raise RuntimeError("The pinned signature-scoring engine is unavailable.")
    source_sha256 = matrix.source_sha256 or _sha256_file(matrix.path)
    params = scoring_parameters(method, int(universe["gene_count"]))
    if method == "singscore":
        params["direction_combination"] = (
            "singscore_total_score"
            if up_genes and down_genes
            else (
                "singscore_up_total_score"
                if up_genes
                else "negated_singscore_total_score"
            )
        )
    engine_sha256 = _sha256_file(script_path)
    identity = {
        "contract_version": SIGNATURE_SCORING_CONTRACT_VERSION,
        "dataset": dataset_identity,
        "matrix_sha256": source_sha256,
        "expression_scale": matrix.expression_scale,
        "universe_sha256": universe["sha256"],
        "canonical_samples_sha256": _stable_hash(ordered_sample_ids),
        "method": method,
        "up_genes": sorted(up_genes),
        "down_genes": sorted(down_genes),
        "parameters": params,
        "availability_rule": {
            "minimum_broad_layer_genes": MIN_TRANSCRIPTOME_GENES,
            "maximum_matrix_entries": MAX_MATRIX_ENTRIES,
        },
        "package_version": EXPECTED_PACKAGE_VERSIONS[method],
        "engine_sha256": engine_sha256,
    }
    cache_key = _stable_hash(identity)
    cache_dir = cache_root / SIGNATURE_SCORING_CONTRACT_VERSION / cache_key[:2]
    cache_dir.mkdir(parents=True, exist_ok=True)
    result_path = cache_dir / f"{cache_key}.json"
    lock_path = cache_dir / f"{cache_key}.lock"
    with _exclusive_lock(lock_path):
        payload: dict[str, Any] | None = None
        if result_path.is_file():
            try:
                candidate = json.loads(result_path.read_text(encoding="utf-8"))
                _validated_scores(candidate, method=method, sample_ids=ordered_sample_ids, cache_key=cache_key)
                payload = candidate
            except (OSError, json.JSONDecodeError, RuntimeError):
                # Reject under the same lock used to publish replacements.
                result_path.unlink(missing_ok=True)
                payload = None
        if payload is None:
            fd, raw_input_path = tempfile.mkstemp(
                prefix="signature-scoring-", suffix=".input.json", dir=cache_dir
            )
            os.close(fd)
            input_path = Path(raw_input_path)
            output_path = input_path.with_suffix(".output.json")
            input_payload = {
                "schema_version": SIGNATURE_SCORING_ENGINE_SCHEMA,
                "cache_identity_sha256": cache_key,
                "matrix_path": str(matrix.path.resolve()),
                "output_path": str(output_path.resolve()),
                "source_row_count": source_row_count,
                "source_sample_count": len(matrix.sample_ids),
                "source_endian": r_binary_endian(matrix.byte_order),
                "gene_symbols": [item["symbol"] for item in universe["genes"]],
                "gene_row_indices_zero_based": [
                    item["row_number"] for item in universe["genes"]
                ],
                "sample_ids": ordered_sample_ids,
                "sample_indices_zero_based": [
                    sample_index[sample_id] for sample_id in ordered_sample_ids
                ],
                "sample_tie_seeds": [
                    aucell_sample_seed(sample_id)
                    for sample_id in ordered_sample_ids
                ],
                "up_genes": up_genes,
                "down_genes": down_genes,
                "method": method,
                "parameters": params,
                "expected_package_version": EXPECTED_PACKAGE_VERSIONS[method],
            }
            temporary = result_path.with_suffix(f".{os.getpid()}.tmp")
            try:
                input_path.write_text(
                    json.dumps(input_payload, ensure_ascii=True, allow_nan=False),
                    encoding="utf-8",
                )
                started = time.perf_counter()
                try:
                    completed = subprocess.run(
                        ["Rscript", str(script_path), str(input_path)],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=900,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise SignatureScoringTimeout(
                        f"{signature_method_label(method)} signature scoring reached "
                        "the 15-minute execution limit. No new result was produced. "
                        "Use a local deployment for this expression layer, or choose "
                        "a smaller molecular population if it fits your question. "
                        "Clinical filters alone do not reduce rank-scoring work."
                    ) from exc
                wall_seconds = time.perf_counter() - started
                if completed.returncode != 0 or not output_path.is_file():
                    detail = (completed.stderr or completed.stdout or "").strip()
                    raise RuntimeError(
                        f"{method} signature scoring failed. "
                        f"{detail[-2000:] if detail else 'No R output was produced.'}"
                    )
                payload = json.loads(output_path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise RuntimeError("The signature-scoring engine returned an unknown schema.")
                payload["cache_identity_sha256"] = cache_key
                payload["process_wall_seconds"] = wall_seconds
                _validated_scores(payload, method=method, sample_ids=ordered_sample_ids, cache_key=cache_key)
                temporary.write_text(
                    json.dumps(payload, ensure_ascii=True, allow_nan=False),
                    encoding="utf-8",
                )
                os.replace(temporary, result_path)
            finally:
                input_path.unlink(missing_ok=True)
                output_path.unlink(missing_ok=True)
                temporary.unlink(missing_ok=True)

    scores, component_scores, package_version = _validated_scores(
        payload, method=method, sample_ids=ordered_sample_ids, cache_key=cache_key,
    )

    coverage = {
        "requested_n": len(entries),
        "mapped_n": len(entries),
        "unique_resolved_n": len(up_genes) + len(down_genes),
        "resolved_n": len(up_genes) + len(down_genes),
        "missing_n": 0,
        "fraction": 1.0,
        "missing_queries": [],
        "duplicate_queries": [],
        "duplicate_resolutions": [],
        "fail_closed_on_missing": True,
        "up_n": len(up_genes),
        "down_n": len(down_genes),
    }
    if resolution_summary is not None:
        coverage.update(resolution_summary)
        coverage["up_n"] = len(up_genes)
        coverage["down_n"] = len(down_genes)
        coverage["resolved_n"] = coverage.get(
            "unique_resolved_n", len(up_genes) + len(down_genes)
        )
        coverage["fail_closed_on_missing"] = True
    provenance = {
        "schema_version": SIGNATURE_SCORING_SCHEMA,
        "contract_version": SIGNATURE_SCORING_CONTRACT_VERSION,
        "method": method,
        "engine": {
            "name": f"Bioconductor {ENGINE_PACKAGES[method]}",
            "package": ENGINE_PACKAGES[method],
            "version": package_version,
            "bioconductor_release": "3.20",
            "r_version": str(payload.get("r_version") or ""),
            "script_sha256": engine_sha256,
        },
        "parameters": params,
        "gene_universe": {
            key: value for key, value in universe.items() if key != "genes"
        }
        | {
            "matrix_sha256": source_sha256,
            "expression_scale": matrix.expression_scale,
            "expression_scale_label": matrix.expression_scale_label,
        },
        "coverage": coverage,
        "direction": {
            "up_genes": up_genes,
            "down_genes": down_genes,
            "combination": params["direction_combination"],
        },
        "scoring_population": {
            "timing": "before endpoint and clinical filters",
            "rule": (
                "release-specific molecular population followed by one "
                "deterministically selected RNA sample per patient"
            ),
            "canonical_barcode_count": len(ordered_sample_ids),
            "canonical_barcodes_sha256": _stable_hash(ordered_sample_ids),
            "aucell_tie_seeds_sha256": (
                _stable_hash(
                    [
                        {
                            "sample_id": sample_id,
                            "seed": aucell_sample_seed(sample_id),
                        }
                        for sample_id in ordered_sample_ids
                    ]
                )
                if method == "aucell"
                else None
            ),
        },
        "cache": {
            "key_sha256": cache_key,
        },
        "constant_signature_genes": list(
            payload.get("constant_signature_genes") or []
        ),
        "canonical_score_values_sha256": _stable_hash(
            [
                {"sample_id": sample_id, "score": scores[sample_id]}
                for sample_id in ordered_sample_ids
            ]
        ),
        "canonical_component_score_values_sha256": _stable_hash(
            [
                {
                    "sample_id": sample_id,
                    **component_scores[sample_id],
                }
                for sample_id in ordered_sample_ids
            ]
        ),
    }
    warnings: list[str] = []
    if universe["duplicate_symbol_count"]:
        warnings.append(
            f"{universe['duplicate_symbol_count']} duplicate gene-symbol rows "
            "were collapsed by keeping the first indexed matrix row."
        )
    if provenance["constant_signature_genes"]:
        warnings.append(
            "Signature genes constant across the canonical scoring population: "
            + ", ".join(provenance["constant_signature_genes"])
            + "."
        )
    return scores, provenance, warnings
