from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CancerType,
    RepositoryDataset,
    RepositoryExpressionLayer,
    RepositoryRelease,
)
from app.repository.service import (
    RepositoryContext,
    repository_expression_layer_paths,
)
from app.repository.storage import (
    read_matrix_metadata,
    scan_float32le_matrix,
    sha256_file,
)


RANK_LAYER_ATTESTATION_SCHEMA = "trace-rank-layer-attestation-v1"
RANK_LAYER_SCANNER = "scan_float32le_matrix-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scan_layer(
    context: RepositoryContext,
    layer: RepositoryExpressionLayer,
) -> dict[str, Any]:
    matrix_path, metadata_path = repository_expression_layer_paths(
        context,
        layer,
    )
    metadata = read_matrix_metadata(metadata_path)
    metadata_gene_count = int(metadata.get("gene_count") or 0)
    metadata_sample_ids = [
        str(value) for value in metadata.get("sample_ids") or []
    ]
    if metadata_gene_count != int(layer.gene_count):
        raise ValueError(
            f"Layer {layer.layer_id!r} gene count does not match its frozen metadata."
        )
    if len(metadata_sample_ids) != int(layer.sample_count):
        raise ValueError(
            f"Layer {layer.layer_id!r} sample count does not match its frozen metadata."
        )
    if len(metadata_sample_ids) != len(set(metadata_sample_ids)):
        raise ValueError(
            f"Layer {layer.layer_id!r} contains duplicate sample IDs."
        )
    expected_bytes = int(layer.gene_count) * int(layer.sample_count) * 4
    if matrix_path.stat().st_size != expected_bytes:
        raise ValueError(
            f"Layer {layer.layer_id!r} matrix size does not match its frozen dimensions."
        )
    matrix_sha256 = sha256_file(matrix_path)
    if matrix_sha256 != layer.matrix_sha256:
        raise ValueError(
            f"Layer {layer.layer_id!r} matrix checksum does not match the database record."
        )
    numerical_qc = scan_float32le_matrix(
        matrix_path,
        gene_count=int(layer.gene_count),
        sample_count=int(layer.sample_count),
    )
    return {
        "schema_version": RANK_LAYER_ATTESTATION_SCHEMA,
        "scanner": RANK_LAYER_SCANNER,
        "expression_layer_id": layer.layer_id,
        "gene_count": int(layer.gene_count),
        "sample_count": int(layer.sample_count),
        "matrix_entry_count": int(layer.gene_count) * int(layer.sample_count),
        "matrix_sha256": matrix_sha256,
        "metadata_sha256": sha256_file(metadata_path),
        **numerical_qc,
    }


def attest_legacy_rank_layers(
    db: Session,
    *,
    release_id: str,
    apply: bool = False,
) -> dict[str, Any]:
    """Scan one explicit public release; persist only after every check passes.

    Dry-run is the default. Existing numerical QC is never overwritten. This
    command exists for historical releases whose matrices predate the finite-
    value attestation; normal imports already perform the same bounded scan.
    """

    release = db.get(RepositoryRelease, release_id)
    if release is None:
        raise ValueError(f"Repository release {release_id!r} was not found.")
    dataset = db.get(RepositoryDataset, release.dataset_id)
    if dataset is None or (dataset.visibility or "public") != "public":
        raise ValueError("Legacy rank-layer attestation is limited to public releases.")
    cancer = db.get(CancerType, dataset.cancer_code)
    if cancer is None:
        raise ValueError(
            f"Cancer type {dataset.cancer_code!r} is not registered."
        )
    layers = list(
        db.scalars(
            select(RepositoryExpressionLayer)
            .where(RepositoryExpressionLayer.release_id == release.id)
            .order_by(RepositoryExpressionLayer.layer_id)
        ).all()
    )
    if not layers:
        raise ValueError(f"Release {release_id!r} contains no expression layers.")

    original_qc = deepcopy(release.qc_json or {})
    original_manifest_hash = release.manifest_hash
    qc_layers = original_qc.get("layers") or {}
    if not isinstance(qc_layers, dict):
        raise ValueError("Release QC layers are malformed; no attestation was written.")
    context = RepositoryContext(dataset=dataset, release=release, cancer=cancer)
    reports: list[dict[str, Any]] = []
    patches: dict[str, dict[str, Any]] = {}
    for layer in layers:
        current = qc_layers.get(layer.layer_id) or {}
        if not isinstance(current, dict):
            raise ValueError(
                f"Layer {layer.layer_id!r} QC is malformed; no attestation was written."
            )
        if "nonfinite_values" in current:
            reports.append(
                {
                    "expression_layer_id": layer.layer_id,
                    "action": "already_attested",
                    "nonfinite_values": int(
                        current.get("nonfinite_values") or 0
                    ),
                }
            )
            continue
        attestation = _scan_layer(context, layer)
        patches[layer.layer_id] = {
            **current,
            "genes": int(layer.gene_count),
            "samples": int(layer.sample_count),
            "is_default": bool(layer.is_default),
            "missing_value_policy": "forbid_non_finite",
            "finite_values": int(attestation["finite_values"]),
            "nonfinite_values": int(attestation["nonfinite_values"]),
            "constant_genes": int(attestation["constant_genes"]),
            "variable_genes": int(attestation["variable_genes"]),
            "rank_scoring_attestation": attestation,
        }
        reports.append(
            {
                **attestation,
                "action": "would_attest" if not apply else "attested",
            }
        )

    if apply and patches:
        locked = db.scalar(
            select(RepositoryRelease)
            .where(RepositoryRelease.id == release_id)
            .with_for_update()
        )
        if (
            locked is None
            or locked.manifest_hash != original_manifest_hash
            or (locked.qc_json or {}) != original_qc
        ):
            db.rollback()
            raise ValueError(
                "The release changed while it was being scanned; no attestation was written."
            )
        updated_qc = deepcopy(original_qc)
        updated_layers = deepcopy(qc_layers)
        updated_layers.update(patches)
        updated_qc["layers"] = updated_layers
        updated_qc.setdefault(
            "default_expression_layer_id",
            next(
                (layer.layer_id for layer in layers if layer.is_default),
                None,
            ),
        )
        updated_qc["rank_scoring_attestation"] = {
            "schema_version": RANK_LAYER_ATTESTATION_SCHEMA,
            "attested_at": _utc_now(),
            "release_id": release_id,
            "manifest_hash": original_manifest_hash,
            "layer_ids": sorted(patches),
        }
        locked.qc_json = updated_qc
        db.commit()

    return {
        "schema_version": RANK_LAYER_ATTESTATION_SCHEMA,
        "release_id": release_id,
        "dataset_id": dataset.id,
        "apply": bool(apply),
        "updated_layers": len(patches) if apply else 0,
        "pending_layers": len(patches) if not apply else 0,
        "layers": reports,
    }
