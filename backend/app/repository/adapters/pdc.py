from __future__ import annotations

import csv
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import shutil
import time
from typing import Any
import urllib.error
import urllib.request
import zipfile

from app.repository.storage import canonical_json_sha256, sha256_file


PDC_ADAPTER_VERSION = "pdc_pancancer_v1"
PDC_API = "https://pdc.cancer.gov/pdcapi"
USER_AGENT = "TCGA-TRACE-curated-repository/1.0"
NETWORK_ATTEMPTS = 4
RETRYABLE_HTTP_CODES = {408, 429, 500, 502, 503, 504}


def materialize_pdc_pancancer_source(
    spec: dict[str, Any],
    source_dir: Path,
) -> tuple[dict[str, Path], str, str | None, dict[str, Any]]:
    source = spec["source"]
    clinical_file_id = _required(source, "clinical_file_id")
    clinical_member = _required(source, "clinical_archive_member")
    expression_url = _required(source, "expression_mirror_url")
    expression_member = _required(source, "expression_archive_member")
    expression_file_id = _required(source, "expression_file_id")
    mapping_url = _required(source, "mapping_url")
    license_url = _required(source, "license_evidence_url")

    clinical_archive = source_dir / "Clinical_meta_data_v1.zip"
    clinical_path = source_dir / Path(clinical_member).name
    expression_raw_path = source_dir / Path(expression_member).name
    mapping_path = source_dir / "gencode_v34_mapping.tsv.gz"
    license_path = source_dir / "PDC_DATA_USE_GUIDELINES.html"

    signed_payload = request_json(
        f"{PDC_API}/file/signedURLFromUuid/{clinical_file_id}"
    )
    signed_url = str(signed_payload.get("data") or "").strip()
    if signed_payload.get("error") or not signed_url:
        raise ValueError(
            "PDC did not return a public signed URL for the clinical archive."
        )
    download(signed_url, clinical_archive)
    verify_sha256(
        clinical_archive,
        _required(source, "clinical_archive_sha256"),
        "PDC clinical archive",
    )
    extract_zip_member(clinical_archive, clinical_member, clinical_path)
    verify_sha256(
        clinical_path,
        _required(source, "clinical_member_sha256"),
        "PDC clinical member",
    )

    download(expression_url, expression_raw_path)
    verify_sha256(
        expression_raw_path,
        _required(source, "expression_member_sha256"),
        "PDC RNA expression member mirror",
    )
    download(mapping_url, mapping_path)
    verify_sha256(
        mapping_path,
        _required(source, "mapping_sha256"),
        "GENCODE mapping snapshot",
    )
    download(license_url, license_path)

    expression_path = source_dir / "expression_ensembl_hugo.tsv"
    expression_summary = materialize_pdc_expression(
        expression_raw_path,
        mapping_path,
        expression_path,
    )
    clinical_summary = materialize_pdc_clinical(
        clinical_path,
        expression_summary["sample_ids"],
        source_dir / "patients.tsv",
        source_dir / "samples.tsv",
        clinical_id_column=str(
            source.get("clinical_id_column") or "idx"
        ),
    )

    source_snapshot = {
        "schema_version": "tcga-trace-pdc-source-snapshot-v1",
        "pdc_clinical_file_id": clinical_file_id,
        "pdc_clinical_archive_sha256": sha256_file(clinical_archive),
        "pdc_clinical_member": clinical_member,
        "pdc_clinical_member_sha256": sha256_file(clinical_path),
        "pdc_expression_file_id": expression_file_id,
        "pdc_expression_member": expression_member,
        "pdc_expression_member_sha256": sha256_file(expression_raw_path),
        "expression_mirror_url": expression_url,
        "mapping_url": mapping_url,
        "mapping_sha256": sha256_file(mapping_path),
        "mapping_release": str(source.get("mapping_release") or ""),
        "license_url": license_url,
        "license_sha256": sha256_file(license_path),
    }
    source_snapshot_sha256 = canonical_json_sha256(source_snapshot)
    source_manifest = {
        **source_snapshot,
        "source_snapshot_sha256": source_snapshot_sha256,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "clinical": clinical_summary,
        "expression": {
            key: value
            for key, value in expression_summary.items()
            if key != "sample_ids"
        },
        "license_evidence_url": license_url,
        "expression_mirror_note": (
            "The versioned LinkedOmics data-freeze member is accepted only "
            "when its SHA-256 matches the member independently verified in "
            "the official PDC RNA_BCM_v1 archive."
        ),
    }
    source_manifest_path = source_dir / "pdc_source_manifest.json"
    source_manifest_path.write_text(
        json.dumps(source_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return (
        {
            "patients": source_dir / "patients.tsv",
            "samples": source_dir / "samples.tsv",
            "expression": expression_path,
            "clinical_archive": clinical_archive,
            "clinical_member": clinical_path,
            "expression_original": expression_raw_path,
            "gene_mapping": mapping_path,
            "license": license_path,
            "source_manifest": source_manifest_path,
        },
        source_snapshot_sha256,
        str(source.get("snapshot_date") or "") or None,
        {
            "source_provider": "NCI PDC pan-cancer data freeze",
            "source_snapshot_manifest": source_manifest,
            "source_expression_samples": expression_summary[
                "sample_count"
            ],
            "source_expression_genes": expression_summary["gene_count"],
            "source_unique_gene_symbols": expression_summary[
                "unique_gene_symbols"
            ],
            "source_unambiguous_gene_symbols": expression_summary[
                "unambiguous_gene_symbols"
            ],
            "source_clinical_patients": clinical_summary[
                "clinical_patients"
            ],
            "source_expression_clinical_patients": clinical_summary[
                "expression_clinical_patients"
            ],
        },
    )


def materialize_pdc_expression(
    expression_path: Path,
    mapping_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    gene_to_symbol = read_gencode_mapping(mapping_path)
    symbol_to_genes: dict[str, set[str]] = {}
    sample_ids: list[str] = []
    gene_count = 0

    with expression_path.open(
        newline="", encoding="utf-8", errors="strict"
    ) as source_handle, output_path.open(
        "w", newline="", encoding="utf-8"
    ) as output_handle:
        reader = csv.reader(source_handle, delimiter="\t")
        writer = csv.writer(
            output_handle, delimiter="\t", lineterminator="\n"
        )
        header = next(reader)
        if len(header) < 11 or header[0].strip().lower() not in {
            "idx",
            "gene",
            "gene_id",
        }:
            raise ValueError(
                "PDC expression matrix lacks its feature identifier column."
            )
        sample_ids = [value.strip() for value in header[1:]]
        if (
            any(not value for value in sample_ids)
            or len(sample_ids) != len(set(sample_ids))
        ):
            raise ValueError(
                "PDC expression sample identifiers must be non-empty and unique."
            )
        writer.writerow(["gene_id", *sample_ids])

        for row in reader:
            if not row:
                continue
            if len(row) != len(header):
                raise ValueError(
                    "PDC expression row width differs from the header."
                )
            gene_id = row[0].strip()
            symbol = gene_to_symbol.get(gene_id)
            if not symbol:
                raise ValueError(
                    f"GENCODE mapping is missing expression feature {gene_id}."
                )
            writer.writerow([f"{gene_id}|{symbol}", *row[1:]])
            symbol_to_genes.setdefault(symbol, set()).add(gene_id)
            gene_count += 1

    if gene_count != len(gene_to_symbol):
        raise ValueError(
            "PDC expression and GENCODE mapping do not contain the same "
            f"gene set ({gene_count} versus {len(gene_to_symbol)})."
        )
    ambiguous_symbols = {
        symbol
        for symbol, genes in symbol_to_genes.items()
        if len(genes) > 1
    }
    unambiguous_gene_symbols = sum(
        1
        for symbol, genes in symbol_to_genes.items()
        if len(genes) == 1
    )
    if unambiguous_gene_symbols < 10_000:
        raise ValueError(
            "PDC expression contains fewer than 10,000 unambiguous symbols."
        )
    return {
        "sample_ids": sample_ids,
        "sample_count": len(sample_ids),
        "gene_count": gene_count,
        "unique_gene_symbols": len(symbol_to_genes),
        "ambiguous_gene_symbols": len(ambiguous_symbols),
        "unambiguous_gene_symbols": unambiguous_gene_symbols,
    }


def read_gencode_mapping(mapping_path: Path) -> dict[str, str]:
    gene_to_symbol: dict[str, str] = {}
    with gzip.open(
        mapping_path, mode="rt", newline="", encoding="utf-8"
    ) as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            gene_id = str(row.get("gene") or "").strip()
            symbol = str(row.get("gene_name") or "").strip().upper()
            if not gene_id or not symbol:
                continue
            previous = gene_to_symbol.get(gene_id)
            if previous is not None and previous != symbol:
                raise ValueError(
                    f"GENCODE feature {gene_id} maps to conflicting symbols."
                )
            gene_to_symbol[gene_id] = symbol
    if not gene_to_symbol:
        raise ValueError("GENCODE mapping snapshot contains no usable genes.")
    return gene_to_symbol


def materialize_pdc_clinical(
    clinical_path: Path,
    expression_sample_ids: list[str],
    patients_path: Path,
    samples_path: Path,
    *,
    clinical_id_column: str = "idx",
) -> dict[str, Any]:
    with clinical_path.open(
        newline="", encoding="utf-8", errors="strict"
    ) as handle:
        clinical_rows = [
            row
            for row in csv.DictReader(handle, delimiter="\t")
            if str(row.get(clinical_id_column) or "").strip()
            not in {"", "data_type"}
        ]
    clinical_by_id = {
        str(row[clinical_id_column]).strip(): row
        for row in clinical_rows
    }
    if len(clinical_by_id) != len(clinical_rows):
        raise ValueError("PDC clinical identifiers are not unique.")
    missing = [
        sample_id
        for sample_id in expression_sample_ids
        if sample_id not in clinical_by_id
    ]
    if missing:
        raise ValueError(
            "PDC expression samples are absent from clinical metadata: "
            + ", ".join(missing[:10])
        )

    patient_rows = [
        {
            "PATIENT_ID": patient_id,
            "OS_DAYS": clean_value(row.get("OS_days")),
            "OS_STATUS": clean_value(row.get("OS_event")),
            "PFS_DAYS": clean_value(row.get("PFS_days")),
            "PFS_STATUS": clean_value(row.get("PFS_event")),
            "STAGE": clean_value(row.get("Stage")),
            "GRADE": clean_value(row.get("Histologic_Grade")),
            "SEX": clean_value(row.get("Sex")),
            "AGE": clean_value(row.get("Age")),
        }
        for patient_id, row in clinical_by_id.items()
    ]
    sample_rows = [
        {
            "SAMPLE_ID": sample_id,
            "PATIENT_ID": sample_id,
            "SAMPLE_TYPE": "Tumor",
        }
        for sample_id in expression_sample_ids
    ]
    write_tsv(
        patients_path,
        patient_rows,
        [
            "PATIENT_ID",
            "OS_DAYS",
            "OS_STATUS",
            "PFS_DAYS",
            "PFS_STATUS",
            "STAGE",
            "GRADE",
            "SEX",
            "AGE",
        ],
    )
    write_tsv(
        samples_path,
        sample_rows,
        ["SAMPLE_ID", "PATIENT_ID", "SAMPLE_TYPE"],
    )

    endpoint_rows = [
        clinical_by_id[sample_id]
        for sample_id in expression_sample_ids
        if positive_number(clinical_by_id[sample_id].get("OS_days"))
        and clean_value(clinical_by_id[sample_id].get("OS_event"))
        in {"0", "1"}
    ]
    events = sum(
        1
        for row in endpoint_rows
        if clean_value(row.get("OS_event")) == "1"
    )
    pfs_rows = [
        clinical_by_id[sample_id]
        for sample_id in expression_sample_ids
        if positive_number(clinical_by_id[sample_id].get("PFS_days"))
        and clean_value(clinical_by_id[sample_id].get("PFS_event"))
        in {"0", "1"}
    ]
    pfs_events = sum(
        1
        for row in pfs_rows
        if clean_value(row.get("PFS_event")) == "1"
    )
    return {
        "clinical_patients": len(clinical_rows),
        "expression_clinical_patients": len(expression_sample_ids),
        "os_complete_patients": len(endpoint_rows),
        "os_events": events,
        "os_censored": len(endpoint_rows) - events,
        "pfs_complete_patients": len(pfs_rows),
        "pfs_events": pfs_events,
        "pfs_censored": len(pfs_rows) - pfs_events,
    }


def positive_number(value: Any) -> bool:
    text = clean_value(value)
    if text is None:
        return False
    try:
        return float(text) > 0
    except ValueError:
        return False


def clean_value(value: Any) -> str | None:
    text = str(value or "").strip()
    return None if not text or text.upper() in {"NA", "N/A", "NULL"} else text


def extract_zip_member(
    archive_path: Path, member_name: str, target_path: Path
) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        try:
            info = archive.getinfo(member_name)
        except KeyError as exc:
            raise ValueError(
                f"PDC archive is missing required member {member_name!r}."
            ) from exc
        if info.is_dir():
            raise ValueError(
                f"PDC archive member {member_name!r} is not a file."
            )
        with archive.open(info) as source, target_path.open("wb") as target:
            shutil.copyfileobj(source, target)


def verify_sha256(path: Path, expected: str, label: str) -> None:
    actual = sha256_file(path)
    if actual.lower() != expected.strip().lower():
        raise ValueError(
            f"{label} SHA-256 mismatch: expected {expected}, got {actual}."
        )


def request_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    last_error: Exception | None = None
    for attempt in range(NETWORK_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = json.load(response)
            if not isinstance(payload, dict):
                raise ValueError(f"Expected a JSON object from {url}.")
            return payload
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in RETRYABLE_HTTP_CODES:
                raise
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            last_error = exc
        if attempt + 1 < NETWORK_ATTEMPTS:
            time.sleep(2**attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Could not retrieve JSON from {url}.")


def download(url: str, target: Path) -> None:
    temporary = target.with_name(f".{target.name}.part")
    last_error: Exception | None = None
    for attempt in range(NETWORK_ATTEMPTS):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT}
            )
            with urllib.request.urlopen(
                request, timeout=180
            ) as response, temporary.open("wb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
            temporary.replace(target)
            return
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in RETRYABLE_HTTP_CODES:
                raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
        temporary.unlink(missing_ok=True)
        if attempt + 1 < NETWORK_ATTEMPTS:
            time.sleep(2**attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Could not download {url}.")


def write_tsv(
    path: Path, rows: list[dict[str, Any]], fieldnames: list[str]
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def _required(source: dict[str, Any], key: str) -> str:
    value = str(source.get(key) or "").strip()
    if not value:
        raise ValueError(f"PDC source requires {key}.")
    return value
