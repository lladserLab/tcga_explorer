from __future__ import annotations

from array import array
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Iterable


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_sha256(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def safe_bundle_path(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise ValueError(f"Bundle path must be relative: {relative!r}")
    root_resolved = root.resolve()
    candidate = (root / relative).resolve()
    if root_resolved != candidate and root_resolved not in candidate.parents:
        raise ValueError(f"Bundle path escapes its root: {relative!r}")
    return candidate


def write_float32le_matrix(path: Path, rows: Iterable[Iterable[float]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("wb") as handle:
        for row in rows:
            values = array("f", (float(value) for value in row))
            if sys.byteorder != "little":
                values.byteswap()
            values.tofile(handle)
            written += len(values)
    return written


def read_float32le_row(
    matrix_path: Path,
    *,
    row_number: int,
    sample_ids: list[str],
) -> dict[str, float]:
    sample_count = len(sample_ids)
    item_size = array("f").itemsize
    values = array("f")
    with matrix_path.open("rb") as handle:
        handle.seek(row_number * sample_count * item_size)
        values.fromfile(handle, sample_count)
    if sys.byteorder != "little":
        values.byteswap()
    if len(values) != sample_count:
        raise ValueError(
            f"Expression row {row_number} is truncated in {matrix_path}."
        )
    return {
        sample_id: float(value)
        for sample_id, value in zip(sample_ids, values, strict=True)
        if math.isfinite(float(value))
    }


def read_matrix_metadata(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("dtype") != "float32_le":
        raise ValueError(f"Unsupported repository matrix dtype in {path}.")
    if payload.get("layout") != "row_major_gene_by_sample":
        raise ValueError(f"Unsupported repository matrix layout in {path}.")
    return payload
