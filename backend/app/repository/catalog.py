from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CancerType


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return payload


def sync_repository_catalog(db: Session, registry_dir: Path) -> dict[str, int]:
    cancer_payload = load_json(registry_dir / "cancer_types.json")
    coverage_payload = load_json(registry_dir / "coverage.json")
    discovery_payload, discovery_path = latest_discovery_snapshot(registry_dir)
    coverage = {
        str(row["code"]): row
        for row in coverage_payload.get("cancers", [])
        if isinstance(row, dict) and row.get("code")
    }
    discovered = {
        str(row["code"]): row
        for row in (discovery_payload or {}).get("cancers", [])
        if isinstance(row, dict) and row.get("code")
    }
    rows = cancer_payload.get("cancer_types") or []
    seen: set[str] = set()
    for index, raw in enumerate(rows):
        code = str(raw["code"]).strip().upper()
        seen.add(code)
        row = db.get(CancerType, code)
        if row is None:
            row = CancerType(
                code=code,
                tcga_cohort=str(raw["tcga_cohort"]),
                name=str(raw["name"]),
                primary_site=raw.get("primary_site"),
                sort_order=index,
                coverage_status="unsearched",
            )
            db.add(row)
        row.tcga_cohort = str(raw["tcga_cohort"])
        row.name = str(raw["name"])
        row.primary_site = raw.get("primary_site")
        row.sort_order = index
        coverage_row = coverage.get(code) or {}
        row.coverage_status = str(coverage_row.get("status") or "unsearched")
        discovery_row = discovered.get(code) or {}
        row.coverage_metadata = {
            **coverage_row,
            "discovery": {
                "snapshot": (
                    str(discovery_path.relative_to(registry_dir))
                    if discovery_path
                    else None
                ),
                "generated_at": (
                    (discovery_payload or {}).get("generated_at")
                ),
                "candidate_count": int(
                    discovery_row.get("candidate_count") or 0
                ),
                "candidates": discovery_row.get("candidates") or [],
            },
        }

    existing = set(db.scalars(select(CancerType.code)).all())
    unexpected = sorted(existing - seen)
    if unexpected:
        raise ValueError(
            "Database contains cancer types absent from the registry: "
            + ", ".join(unexpected)
        )
    db.commit()
    return {
        "cancer_types": len(rows),
        "available": sum(
            (coverage.get(str(row["code"])) or {}).get("status")
            in {"available", "candidate_validated"}
            for row in rows
        ),
        "gaps": sum(
            (coverage.get(str(row["code"])) or {}).get("status")
            == "evidence_gap"
            for row in rows
        ),
        "screening_candidates": sum(
            int((discovered.get(str(row["code"])) or {}).get("candidate_count") or 0)
            for row in rows
        ),
    }


def latest_discovery_snapshot(
    registry_dir: Path,
) -> tuple[dict[str, Any] | None, Path | None]:
    paths = sorted((registry_dir / "discovery").glob("cbioportal-*.json"))
    if not paths:
        return None, None
    path = paths[-1]
    return load_json(path), path
