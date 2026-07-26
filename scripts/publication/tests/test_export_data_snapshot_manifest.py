from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "export_data_snapshot_manifest.py"
SPEC = importlib.util.spec_from_file_location("export_data_snapshot_manifest", MODULE_PATH)
assert SPEC is not None
exporter = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(exporter)


def test_stable_payload_removes_volatile_fields_recursively() -> None:
    payload = {
        "generated_at": "2026-07-22T00:00:00Z",
        "manifest_hash": "old",
        "duration_seconds": 1.23,
        "rna_snapshot": {
            "cohorts": [
                {
                    "cohort": "TCGA-TEST",
                    "count_matrix": {
                        "bytes": 10,
                        "mtime": "2026-07-22T00:00:00Z",
                        "sha256": "abc",
                    },
                }
            ],
        },
    }

    stable = exporter.stable_payload(payload)

    assert "generated_at" not in stable
    assert "manifest_hash" not in stable
    assert "duration_seconds" not in stable
    assert "mtime" not in stable["rna_snapshot"]["cohorts"][0]["count_matrix"]
    assert stable["rna_snapshot"]["cohorts"][0]["count_matrix"]["sha256"] == "abc"


def test_stable_hash_ignores_export_time_mtime_and_existing_hash() -> None:
    payload = {
        "schema_version": "tcga-trace-data-snapshot-manifest-v1",
        "generated_at": "2026-07-22T00:00:00Z",
        "manifest_hash": "previous",
        "rna_snapshot": {
            "cohorts": [
                {
                    "cohort": "TCGA-TEST",
                    "count_matrix": {
                        "bytes": 12,
                        "mtime": "2026-07-22T00:00:00Z",
                        "sha256": "abc",
                    },
                }
            ]
        },
    }
    changed_volatile_fields = deepcopy(payload)
    changed_volatile_fields["generated_at"] = "2026-07-23T00:00:00Z"
    changed_volatile_fields["manifest_hash"] = "new"
    changed_volatile_fields["duration_seconds"] = 9.87
    changed_volatile_fields["rna_snapshot"]["cohorts"][0]["count_matrix"]["mtime"] = (
        "2026-07-23T00:00:00Z"
    )

    assert exporter.stable_hash(payload) == exporter.stable_hash(changed_volatile_fields)


def test_stable_hash_changes_when_pinned_file_content_changes() -> None:
    payload = {
        "schema_version": "tcga-trace-data-snapshot-manifest-v1",
        "rna_snapshot": {
            "cohorts": [
                {
                    "cohort": "TCGA-TEST",
                    "count_matrix": {
                        "bytes": 12,
                        "sha256": "abc",
                    },
                }
            ]
        },
    }
    changed_content = deepcopy(payload)
    changed_content["rna_snapshot"]["cohorts"][0]["count_matrix"]["sha256"] = "def"

    assert exporter.stable_hash(payload) != exporter.stable_hash(changed_content)
