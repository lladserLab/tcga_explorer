from __future__ import annotations

import csv
from datetime import datetime, timezone
import html
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import shutil
from typing import Any
import urllib.parse
import zipfile

from app.repository.adapters.cbioportal import download, write_tsv
from app.repository.storage import canonical_json_sha256, sha256_file


CGGA_ADAPTER_VERSION = "cgga_release_v1"


def materialize_cgga_source(
    spec: dict[str, Any],
    source_dir: Path,
) -> tuple[dict[str, Path], str, str | None, dict[str, Any]]:
    source = spec["source"]
    source_dataset_id = _required(source, "dataset_id")
    clinical_url = _required(source, "clinical_url")
    expression_url = _required(source, "expression_url")
    clinical_member = _required(source, "clinical_member")
    expression_member = _required(source, "expression_member")
    license_url = _required(source, "license_evidence_url")
    open_access_url = _required(source, "open_access_evidence_url")

    clinical_archive = source_dir / f"{source_dataset_id}_clinical.zip"
    expression_archive = source_dir / f"{source_dataset_id}_expression.zip"
    license_path = source_dir / "CGGA_OPEN_ACCESS_EVIDENCE.json"
    clinical_path = source_dir / ".cgga_clinical_source.tsv"
    expression_path = source_dir / ".cgga_expression_source.tsv"

    download_with_optional_cache(clinical_url, clinical_archive)
    verify_pinned_archive(
        clinical_archive,
        expected_size=int(source["clinical_size"]),
        expected_sha256=_required(source, "clinical_sha256"),
        label="CGGA clinical archive",
    )
    download_with_optional_cache(expression_url, expression_archive)
    verify_pinned_archive(
        expression_archive,
        expected_size=int(source["expression_size"]),
        expected_sha256=_required(source, "expression_sha256"),
        label="CGGA expression archive",
    )
    materialize_cgga_access_evidence(
        source_dataset_id=source_dataset_id,
        open_access_url=open_access_url,
        download_page_url=license_url,
        reviewed_at=_required(source, "access_review_date"),
        clinical_member=clinical_member,
        expression_member=expression_member,
        output_path=license_path,
    )

    extract_exact_zip_member(
        clinical_archive,
        clinical_member,
        clinical_path,
    )
    extract_exact_zip_member(
        expression_archive,
        expression_member,
        expression_path,
    )

    try:
        clinical_rows = read_cgga_clinical(clinical_path)
        source_sample_ids = read_cgga_expression_sample_ids(
            expression_path
        )
        validate_source_pair(
            clinical_rows,
            source_sample_ids,
            expected_samples=int(source["expected_source_samples"]),
        )

        selected_rows = select_cgga_clinical_rows(
            clinical_rows,
            source.get("cohort_filter") or {},
        )
        selected_rows.sort(key=lambda row: row["CGGA_ID"])
        validate_selected_cohort(
            selected_rows,
            expected_patients=int(source["expected_patients"]),
            expected_events=int(source["expected_events"]),
            expected_censored=int(source["expected_censored"]),
        )
        selected_sample_ids = [
            row["CGGA_ID"] for row in selected_rows
        ]

        patient_table = source_dir / "data_clinical_patient.txt"
        sample_table = source_dir / "data_clinical_sample.txt"
        selected_expression = source_dir / "data_expression_fpkm.tsv"
        write_cgga_clinical_tables(
            selected_rows,
            patient_table,
            sample_table,
            sample_type=str(
                source.get("sample_type")
                or "Primary glioma surgical tumor"
            ),
        )
        expression_summary = materialize_cgga_expression(
            expression_path,
            selected_expression,
            selected_sample_ids,
            expected_gene_rows=int(source["expected_source_gene_rows"]),
        )
    finally:
        clinical_path.unlink(missing_ok=True)
        expression_path.unlink(missing_ok=True)

    source_snapshot = {
        "schema_version": "tcga-trace-cgga-source-snapshot-v1",
        "source_dataset_id": source_dataset_id,
        "snapshot_date": str(source.get("snapshot_date") or ""),
        "clinical_url": clinical_url,
        "clinical_member": clinical_member,
        "clinical_size": clinical_archive.stat().st_size,
        "clinical_sha256": sha256_file(clinical_archive),
        "expression_url": expression_url,
        "expression_member": expression_member,
        "expression_size": expression_archive.stat().st_size,
        "expression_sha256": sha256_file(expression_archive),
        "open_access_evidence_url": open_access_url,
        "license_evidence_url": license_url,
        "license_evidence_sha256": sha256_file(license_path),
    }
    source_snapshot_sha256 = canonical_json_sha256(source_snapshot)
    source_manifest = {
        **source_snapshot,
        "source_snapshot_sha256": source_snapshot_sha256,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source_clinical_rows": len(clinical_rows),
        "source_expression_samples": len(source_sample_ids),
        "cohort_filter": source.get("cohort_filter") or {},
        "selected_patients": len(selected_rows),
        "selected_events": sum(
            int(row["Censor (alive=0; dead=1)"])
            for row in selected_rows
        ),
        "selected_censored": sum(
            1 - int(row["Censor (alive=0; dead=1)"])
            for row in selected_rows
        ),
        "expression": expression_summary,
        "license_boundary": (
            "CGGA labels these datasets open access and asks users to cite "
            "the source publications. The portal does not grant an explicit "
            "redistribution license, so TCGA-TRACE disables matrix downloads."
        ),
    }
    source_manifest_path = source_dir / "cgga_source_manifest.json"
    source_manifest_path.write_text(
        json.dumps(source_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return (
        {
            "patients": patient_table,
            "samples": sample_table,
            "expression": selected_expression,
            "clinical_archive": clinical_archive,
            "expression_archive": expression_archive,
            "license": license_path,
            "source_manifest": source_manifest_path,
        },
        source_snapshot_sha256,
        str(source.get("snapshot_date") or "") or None,
        {
            "source_provider": "Chinese Glioma Genome Atlas",
            "source_dataset_id": source_dataset_id,
            "source_snapshot_manifest": source_manifest,
            "source_clinical_patients": len(clinical_rows),
            "source_expression_samples": len(source_sample_ids),
            "selected_source_patients": len(selected_rows),
            "source_expression_genes": expression_summary["gene_rows"],
            "source_unique_gene_symbols": expression_summary[
                "case_insensitive_unique_symbols"
            ],
            "source_ambiguous_gene_symbols": expression_summary[
                "case_insensitive_ambiguous_symbols"
            ],
        },
    )


def verify_pinned_archive(
    path: Path,
    *,
    expected_size: int,
    expected_sha256: str,
    label: str,
) -> None:
    if path.stat().st_size != expected_size:
        raise ValueError(
            f"{label} size differs from the pinned value "
            f"({path.stat().st_size} versus {expected_size})."
        )
    observed_sha256 = sha256_file(path)
    if observed_sha256 != expected_sha256.lower():
        raise ValueError(
            f"{label} SHA-256 differs from the pinned value."
        )


def download_with_optional_cache(url: str, path: Path) -> None:
    cache_dir = str(os.environ.get("CGGA_DOWNLOAD_CACHE_DIR") or "").strip()
    cache_name = Path(urllib.parse.urlparse(url).path).name
    cached = Path(cache_dir) / cache_name if cache_dir else None
    if cached is not None and cached.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cached, path)
        return
    download(url, path)


def materialize_cgga_access_evidence(
    *,
    source_dataset_id: str,
    open_access_url: str,
    download_page_url: str,
    reviewed_at: str,
    clinical_member: str,
    expression_member: str,
    output_path: Path,
) -> None:
    home_path = output_path.parent / ".cgga_home_evidence.html"
    download_path = output_path.parent / ".cgga_download_evidence.html"
    download(open_access_url, home_path)
    download(download_page_url, download_path)
    try:
        home_text = normalized_html_text(
            home_path.read_text(encoding="utf-8", errors="strict")
        )
        download_text = normalized_html_text(
            download_path.read_text(encoding="utf-8", errors="strict")
        )
        validate_cgga_access_evidence(
            home_text,
            download_text,
            source_dataset_id=source_dataset_id,
            clinical_member=clinical_member,
            expression_member=expression_member,
        )
    finally:
        home_path.unlink(missing_ok=True)
        download_path.unlink(missing_ok=True)

    evidence = {
        "schema_version": "tcga-trace-cgga-access-evidence-v1",
        "source_dataset_id": source_dataset_id,
        "reviewed_at": reviewed_at,
        "open_access_evidence_url": open_access_url,
        "download_page_url": download_page_url,
        "clinical_member": clinical_member,
        "expression_member": expression_member,
        "verified_assertions": [
            "CGGA states that read-count data for mRNAseq_693 and "
            "mRNAseq_325 are open access.",
            "CGGA exposes clinical data and STAR+RSEM FPKM expression for "
            f"{source_dataset_id}.",
            "CGGA asks users of the dataset to cite its source publications.",
            "No explicit matrix-redistribution license was identified; "
            "TCGA-TRACE therefore disables downloads.",
        ],
    }
    output_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_cgga_access_evidence(
    home_text: str,
    download_text: str,
    *,
    source_dataset_id: str,
    clinical_member: str,
    expression_member: str,
) -> None:
    required_home = [
        "open access to read counts data for",
        "mrnaseq_693",
        "mrnaseq_325",
    ]
    required_download = [
        source_dataset_id.lower(),
        "expression data from star+rsem (fpkm value)",
        "please consider to cite",
        clinical_member.lower(),
        expression_member.lower(),
    ]
    if any(value not in home_text for value in required_home):
        raise ValueError(
            "CGGA home page no longer exposes the reviewed open-access "
            "statement for both RNA-seq batches."
        )
    if any(value not in download_text for value in required_download):
        raise ValueError(
            "CGGA download page no longer exposes the reviewed clinical, "
            "FPKM or citation evidence."
        )


def normalized_html_text(payload: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(payload)
    parser.close()
    return " ".join(
        html.unescape(" ".join(parser.parts)).casefold().split()
    )


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        for name, value in attrs:
            if name.casefold() in {"href", "src"} and value:
                self.parts.append(value)


def extract_exact_zip_member(
    archive_path: Path,
    member_name: str,
    output_path: Path,
) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        matches = [
            info
            for info in archive.infolist()
            if info.filename == member_name and not info.is_dir()
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Expected one archive member {member_name!r}; "
                f"found {len(matches)}."
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(matches[0]) as source_handle, output_path.open(
            "wb"
        ) as output_handle:
            shutil.copyfileobj(source_handle, output_handle)


def read_cgga_clinical(path: Path) -> list[dict[str, str]]:
    with path.open(
        newline="", encoding="utf-8-sig", errors="strict"
    ) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {
            "CGGA_ID",
            "PRS_type",
            "Histology",
            "Grade",
            "Gender",
            "Age",
            "OS",
            "Censor (alive=0; dead=1)",
        }
        if reader.fieldnames is None or not required.issubset(
            reader.fieldnames
        ):
            raise ValueError(
                "CGGA clinical file lacks required identifiers, disease "
                "annotations, age or survival fields."
            )
        rows = [
            {
                str(key).strip(): str(value or "").strip()
                for key, value in row.items()
            }
            for row in reader
            if any(str(value or "").strip() for value in row.values())
        ]
    return rows


def read_cgga_expression_sample_ids(path: Path) -> list[str]:
    with path.open(
        newline="", encoding="utf-8-sig", errors="strict"
    ) as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader, [])
    if len(header) < 2 or header[0].strip() != "Gene_Name":
        raise ValueError(
            "CGGA expression file lacks its Gene_Name feature column."
        )
    sample_ids = [value.strip() for value in header[1:]]
    if (
        any(not value for value in sample_ids)
        or len(sample_ids) != len(set(sample_ids))
    ):
        raise ValueError(
            "CGGA expression sample identifiers must be non-empty and unique."
        )
    return sample_ids


def validate_source_pair(
    clinical_rows: list[dict[str, str]],
    expression_sample_ids: list[str],
    *,
    expected_samples: int,
) -> None:
    clinical_ids = [row["CGGA_ID"] for row in clinical_rows]
    if (
        any(not patient_id for patient_id in clinical_ids)
        or len(clinical_ids) != len(set(clinical_ids))
    ):
        raise ValueError(
            "CGGA clinical patient identifiers must be non-empty and unique."
        )
    if (
        len(clinical_ids) != expected_samples
        or len(expression_sample_ids) != expected_samples
    ):
        raise ValueError(
            "CGGA source sample count differs from the pinned specification."
        )
    if set(clinical_ids) != set(expression_sample_ids):
        raise ValueError(
            "CGGA clinical and expression identifiers are not an exact pair."
        )


def select_cgga_clinical_rows(
    rows: list[dict[str, str]],
    cohort_filter: dict[str, Any],
) -> list[dict[str, str]]:
    prs_type = str(cohort_filter.get("prs_type") or "").strip()
    grades = {
        str(value).strip()
        for value in cohort_filter.get("grades") or []
        if str(value).strip()
    }
    histologies = {
        str(value).strip()
        for value in cohort_filter.get("histologies") or []
        if str(value).strip()
    }
    minimum_age = float(cohort_filter.get("minimum_age") or 0)
    if not prs_type or not grades or minimum_age <= 0:
        raise ValueError(
            "CGGA cohort filters require prs_type, grades and minimum_age."
        )

    selected: list[dict[str, str]] = []
    for row in rows:
        if row.get("PRS_type") != prs_type:
            continue
        if row.get("Grade") not in grades:
            continue
        if histologies and row.get("Histology") not in histologies:
            continue
        age = _finite_number(row.get("Age"))
        time = _finite_number(row.get("OS"))
        event = str(row.get("Censor (alive=0; dead=1)") or "").strip()
        if (
            age is None
            or age < minimum_age
            or time is None
            or time <= 0
            or event not in {"0", "1"}
        ):
            continue
        selected.append(row)
    return selected


def validate_selected_cohort(
    rows: list[dict[str, str]],
    *,
    expected_patients: int,
    expected_events: int,
    expected_censored: int,
) -> None:
    patient_ids = [row["CGGA_ID"] for row in rows]
    events = sum(
        int(row["Censor (alive=0; dead=1)"]) for row in rows
    )
    censored = len(rows) - events
    if (
        len(rows) != expected_patients
        or events != expected_events
        or censored != expected_censored
    ):
        raise ValueError(
            "CGGA selected cohort counts differ from the reviewed "
            "specification."
        )
    if len(patient_ids) != len(set(patient_ids)):
        raise ValueError(
            "CGGA selected cohort contains duplicate patient identifiers."
        )


def write_cgga_clinical_tables(
    rows: list[dict[str, str]],
    patient_path: Path,
    sample_path: Path,
    *,
    sample_type: str,
) -> None:
    patient_fields = [
        "PATIENT_ID",
        *[field for field in rows[0] if field != "PATIENT_ID"],
    ]
    write_tsv(
        patient_path,
        [
            {
                "PATIENT_ID": row["CGGA_ID"],
                **row,
            }
            for row in rows
        ],
        patient_fields,
    )
    write_tsv(
        sample_path,
        [
            {
                "SAMPLE_ID": row["CGGA_ID"],
                "PATIENT_ID": row["CGGA_ID"],
                "SAMPLE_TYPE": sample_type,
            }
            for row in rows
        ],
        ["SAMPLE_ID", "PATIENT_ID", "SAMPLE_TYPE"],
    )


def materialize_cgga_expression(
    source_path: Path,
    output_path: Path,
    selected_sample_ids: list[str],
    *,
    expected_gene_rows: int,
) -> dict[str, Any]:
    exact_symbols: set[str] = set()
    normalized_symbol_counts: dict[str, int] = {}
    gene_rows = 0

    with source_path.open(
        newline="", encoding="utf-8-sig", errors="strict"
    ) as source_handle, output_path.open(
        "w", newline="", encoding="utf-8"
    ) as output_handle:
        reader = csv.reader(source_handle, delimiter="\t")
        writer = csv.writer(
            output_handle, delimiter="\t", lineterminator="\n"
        )
        header = next(reader, [])
        if len(header) < 2 or header[0].strip() != "Gene_Name":
            raise ValueError(
                "CGGA expression file lacks its Gene_Name feature column."
            )
        source_sample_ids = [value.strip() for value in header[1:]]
        source_index = {
            sample_id: index
            for index, sample_id in enumerate(source_sample_ids)
        }
        if any(
            sample_id not in source_index
            for sample_id in selected_sample_ids
        ):
            raise ValueError(
                "A selected CGGA patient is absent from the expression matrix."
            )
        selected_indexes = [
            source_index[sample_id] + 1
            for sample_id in selected_sample_ids
        ]
        writer.writerow(["Hugo_Symbol", *selected_sample_ids])

        for row in reader:
            if not row:
                continue
            if len(row) != len(header):
                raise ValueError(
                    "CGGA expression row width differs from the header."
                )
            symbol = row[0].strip()
            if not symbol or symbol in exact_symbols:
                raise ValueError(
                    "CGGA source gene symbols must be non-empty and exactly "
                    "unique."
                )
            exact_symbols.add(symbol)
            normalized = symbol.upper()
            normalized_symbol_counts[normalized] = (
                normalized_symbol_counts.get(normalized, 0) + 1
            )
            selected_values = [row[index].strip() for index in selected_indexes]
            for value in selected_values:
                parsed = _finite_number(value)
                if parsed is None or parsed < 0:
                    raise ValueError(
                        "CGGA selected expression values must be finite and "
                        "non-negative."
                    )
            writer.writerow([symbol, *selected_values])
            gene_rows += 1

    if gene_rows != expected_gene_rows:
        raise ValueError(
            "CGGA expression gene count differs from the pinned "
            "specification."
        )
    ambiguous = sum(
        1 for count in normalized_symbol_counts.values() if count > 1
    )
    return {
        "gene_rows": gene_rows,
        "selected_samples": len(selected_sample_ids),
        "exact_unique_symbols": len(exact_symbols),
        "case_insensitive_unique_symbols": len(normalized_symbol_counts),
        "case_insensitive_ambiguous_symbols": ambiguous,
    }


def _finite_number(value: Any) -> float | None:
    try:
        parsed = float(str(value or "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _required(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"CGGA source requires {key}.")
    return value
