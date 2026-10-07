from __future__ import annotations

import asyncio
import csv
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import threading
import time
import zipfile

import httpx
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import Base
from app.main import app
from app.models import CancerType
from app.schemas import UserDatasetMapping
import app.tutorial_assets as tutorial_assets_module
from app.tutorial_assets import (
    TutorialAsset,
    TutorialAssetNotFound,
    build_tutorial_asset,
    tutorial_asset_catalog,
)
from app.user_datasets import (
    UserDatasetError,
    create_user_dataset,
)


EXPECTED_ASSETS = {
    "format-only-upload-v1": {
        "filename": "trace-format-only-upload-v1.zip",
        "clinical": "clinical.csv",
        "expression": "expression.csv",
        "samples": 12,
        "genes": 3,
    },
    "private-quickstart-kirc-log2-v1": {
        "filename": "trace-private-quickstart-kirc-log2-v1.zip",
        "clinical": "clinical.csv",
        "expression": "expression_log2_genes_by_samples.csv",
        "samples": 48,
        "genes": 32,
    },
    "private-transcriptome-kirc-gsea-v1": {
        "filename": "trace-private-transcriptome-kirc-gsea-v1.zip",
        "clinical": "clinical.csv",
        "expression": "expression_log2_tpm_plus_1.csv",
        "samples": 96,
        "genes": 18_000,
    },
    "private-full-counts-normalization-v1": {
        "filename": "trace-private-full-counts-normalization-v1.zip",
        "clinical": "clinical.csv",
        "expression": "raw_counts.csv",
        "samples": 64,
        "genes": 6_000,
    },
    "private-upload-validation-lab-v1": {
        "filename": "trace-private-upload-validation-lab-v1.zip",
        "clinical": "base/clinical.csv",
        "expression": "base/expression.csv",
        "samples": 48,
        "genes": 32,
    },
}


def _archive_files(content: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _csv_dimensions(content: bytes) -> tuple[int, int]:
    reader = csv.reader(io.StringIO(content.decode("utf-8")))
    header = next(reader)
    return sum(1 for _ in reader), len(header) - 1


def _assert_archive_checksums(files: dict[str, bytes]) -> None:
    declared = {}
    for line in files["SHA256SUMS.txt"].decode("utf-8").splitlines():
        digest, name = line.split("  ", 1)
        declared[name] = digest
    payload_names = set(files).difference({"SHA256SUMS.txt"})
    assert set(declared) == payload_names
    assert {
        name: hashlib.sha256(files[name]).hexdigest()
        for name in payload_names
    } == declared


@pytest.fixture(scope="module")
def generated_assets() -> tuple[dict, dict[str, tuple[bytes, str]]]:
    catalog = tutorial_asset_catalog()
    generated = {}
    for asset_id in EXPECTED_ASSETS:
        tutorial_assets_module._build_tutorial_asset_cached.cache_clear()
        first = build_tutorial_asset(asset_id)
        tutorial_assets_module._build_tutorial_asset_cached.cache_clear()
        second = build_tutorial_asset(asset_id)
        assert first[0] == second[0]
        assert first[1] == second[1]
        generated[asset_id] = second
    return catalog, generated


def test_catalog_exposes_exact_versioned_synthetic_assets_without_patient_data(
    generated_assets,
):
    catalog, _ = generated_assets

    assert catalog["schema_version"] == "tutorial-assets-v1"
    assert "no patient data" in catalog["privacy"]
    assert {asset["id"] for asset in catalog["assets"]} == set(
        EXPECTED_ASSETS
    )
    assert all(asset["synthetic"] is True for asset in catalog["assets"])
    assert all(asset["seed"] == 17291 for asset in catalog["assets"])
    assert all(
        asset["download_url"].startswith("/api/v1/tutorial-assets/")
        for asset in catalog["assets"]
    )


@pytest.mark.parametrize("asset_id", EXPECTED_ASSETS)
def test_every_archive_matches_catalog_manifest_dimensions_and_checksums(
    asset_id,
    generated_assets,
):
    catalog, generated = generated_assets
    content, filename = generated[asset_id]
    expected = EXPECTED_ASSETS[asset_id]
    record = next(
        asset for asset in catalog["assets"] if asset["id"] == asset_id
    )
    files = _archive_files(content)
    manifest = json.loads(files["manifest.json"])

    assert filename == expected["filename"]
    assert manifest["asset_id"] == asset_id
    assert manifest["sample_count"] == expected["samples"]
    assert manifest["gene_count"] == expected["genes"]
    assert record["sample_count"] == expected["samples"]
    assert record["gene_count"] == expected["genes"]
    clinical_rows, _ = _csv_dimensions(files[expected["clinical"]])
    gene_rows, expression_samples = _csv_dimensions(
        files[expected["expression"]]
    )
    assert clinical_rows == expected["samples"]
    assert gene_rows == expected["genes"]
    assert expression_samples == expected["samples"]
    assert {"README_EN.md", "README_ES.md", "SHA256SUMS.txt"} <= set(
        files
    )
    _assert_archive_checksums(files)


def test_quickstart_archive_documents_that_the_panel_is_not_for_gsea(
    generated_assets,
):
    _, generated = generated_assets
    files = _archive_files(
        generated["private-quickstart-kirc-log2-v1"][0]
    )

    assert b"not appropriate for GSEA" in files["README_EN.md"]


def _validation_database():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _validation_settings(root: Path) -> Settings:
    return Settings(
        _env_file=None,
        user_dataset_dir=root / "user_uploads",
        artifact_dir=root / "artifacts",
        user_dataset_retention_hours=24,
        user_dataset_max_active_per_client=20,
    )


def test_validation_lab_case_contracts_match_the_real_upload_validator(
    generated_assets,
    tmp_path,
):
    _, generated = generated_assets
    files = _archive_files(
        generated["private-upload-validation-lab-v1"][0]
    )
    index = json.loads(files["cases/index.json"])
    assert index["schema_version"] == (
        "trace-tutorial-upload-case-index-v1"
    )
    assert len(index["cases"]) == 15

    factory = _validation_database()
    settings = _validation_settings(tmp_path)
    with factory() as db:
        db.add(
            CancerType(
                code="KIRC",
                tcga_cohort="TCGA-KIRC",
                name="Kidney Renal Clear Cell Carcinoma",
                primary_site="Kidney",
                sort_order=0,
                coverage_status="available",
            )
        )
        db.commit()
        for index_record in index["cases"]:
            case = json.loads(files[index_record["metadata"]])
            case_id = case["case_id"]
            prefix = f"cases/{case_id}"
            expected = case["expected"]
            mapping = UserDatasetMapping.model_validate(case["mapping"])
            sources = {
                "clinical_source": io.BytesIO(files[f"{prefix}/clinical.csv"]),
                "expression_source": io.BytesIO(
                    files[f"{prefix}/expression.csv"]
                ),
            }

            if expected["outcome"] == "rejected":
                with pytest.raises(UserDatasetError) as error:
                    create_user_dataset(
                        db,
                        settings,
                        mapping=mapping,
                        owner_key_hash=f"tutorial-{case_id}",
                        **sources,
                    )
                assert error.value.code == expected["error_code"], case_id
                continue

            result = create_user_dataset(
                db,
                settings,
                mapping=mapping,
                owner_key_hash=f"tutorial-{case_id}",
                **sources,
            )
            notice_codes = {
                notice["code"] for notice in result["qc"]["notices"]
            }
            assert set(expected["notice_codes"]) <= notice_codes, case_id
            assert result["patient_count"] == 48

    semantic_cases = {
        record["case_id"]
        for record in index["cases"]
        if record["semantic_review_required"]
    }
    assert semantic_cases == {
        "semantic-traps/tpm-declared-log2",
        "semantic-traps/days-declared-months",
    }
    notices_case = next(
        record
        for record in index["cases"]
        if record["case_id"] == "valid-with-qc-notices"
    )
    assert notices_case["notice_codes"] == [
        "UNMATCHED_IDENTIFIERS_EXCLUDED"
    ]


def test_bundled_gene_universe_fails_before_catalog_can_overclaim(
    monkeypatch,
):
    required = [
        "CDC20", "BIRC5", "UBE2C", "MKI67", "FOXM1", "VEGFA",
        "EPAS1", "HIF1A", "KDR", "CXCL9", "CXCL10", "CD3D", "CD8A",
        "GZMB", "NKG7", "PRF1", "PDCD1", "CD274",
    ]
    tutorial_assets_module._transcriptome_gene_design.cache_clear()
    monkeypatch.setattr(
        tutorial_assets_module,
        "_gmt_rows",
        lambda: [("undersized", required)],
    )

    with pytest.raises(RuntimeError, match="at least 18,000"):
        tutorial_asset_catalog()

    tutorial_assets_module._transcriptome_gene_design.cache_clear()


def test_concurrent_first_build_is_coalesced(monkeypatch):
    asset_id = "concurrency-fixture"
    calls = 0
    calls_lock = threading.Lock()

    def generator() -> bytes:
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return b"one deterministic archive"

    asset = TutorialAsset(
        asset_id=asset_id,
        filename="fixture.zip",
        title={"en": "Fixture", "es": "Fixture"},
        description={"en": "Fixture", "es": "Fixture"},
        intended_uses=("test",),
        sample_count=0,
        gene_count=0,
        expression_scale="fixture",
        generator=generator,
    )
    tutorial_assets_module._build_tutorial_asset_cached.cache_clear()
    monkeypatch.setitem(tutorial_assets_module._ASSET_BY_ID, asset_id, asset)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(
                lambda _: build_tutorial_asset(asset_id),
                range(8),
            )
        )

    assert calls == 1
    assert results == [(b"one deterministic archive", "fixture.zip")] * 8
    tutorial_assets_module._build_tutorial_asset_cached.cache_clear()


def test_tutorial_asset_http_catalog_download_headers_digest_and_404():
    async def fetch():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return (
                await client.get("/api/v1/tutorial-assets"),
                await client.get(
                    "/api/v1/tutorial-assets/format-only-upload-v1"
                ),
                await client.get(
                    "/api/v1/tutorial-assets/does-not-exist"
                ),
            )

    catalog_response, download_response, missing_response = asyncio.run(
        fetch()
    )
    content_digest = hashlib.sha256(download_response.content).hexdigest()

    assert catalog_response.status_code == 200
    assert catalog_response.headers["cache-control"] == (
        "public, max-age=3600"
    )
    assert {
        asset["id"] for asset in catalog_response.json()["assets"]
    } == set(EXPECTED_ASSETS)
    assert download_response.status_code == 200
    assert download_response.headers["content-type"] == "application/zip"
    assert download_response.headers["content-disposition"] == (
        'attachment; filename="trace-format-only-upload-v1.zip"'
    )
    assert download_response.headers["cache-control"] == (
        "public, max-age=86400, immutable"
    )
    assert download_response.headers["x-content-sha256"] == content_digest
    assert download_response.headers["etag"] == (
        f'"sha256-{content_digest}"'
    )
    assert missing_response.status_code == 404
    assert missing_response.json()["error"]["code"] == (
        "TUTORIAL_ASSET_NOT_FOUND"
    )


def test_missing_tutorial_asset_raises_typed_error():
    with pytest.raises(TutorialAssetNotFound):
        build_tutorial_asset("not-an-asset")
