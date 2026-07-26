#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
API_BASE = "https://www.cbioportal.org/api"
OUTPUT_DIR = (
    ROOT
    / "docs"
    / "publication"
    / "benchmark"
    / "external_concordance_panel"
)
R_SCRIPT = ROOT / "scripts" / "publication" / "external_concordance.R"
USER_AGENT = "TCGA-TRACE-publication-concordance/1.0"


@dataclass(frozen=True)
class ConcordanceCase:
    case_id: str
    cohort: str
    gene: str
    entrez_gene_id: int
    study_id: str
    benchmark_directory: str
    prespecified_role: str


CASES = (
    ConcordanceCase(
        case_id="kirc_ca9_os_median",
        cohort="TCGA-KIRC",
        gene="CA9",
        entrez_gene_id=768,
        study_id="kirc_tcga_pan_can_atlas_2018",
        benchmark_directory="kirc_ca9_cutpoint_benchmark",
        prespecified_role="direction and significance-discordance case",
    ),
    ConcordanceCase(
        case_id="skcm_pdcd1_os_median",
        cohort="TCGA-SKCM",
        gene="PDCD1",
        entrez_gene_id=5133,
        study_id="skcm_tcga_pan_can_atlas_2018",
        benchmark_directory="skcm_pdcd1_os_cutpoint_benchmark",
        prespecified_role="supported immune-marker case",
    ),
    ConcordanceCase(
        case_id="luad_cd274_os_median",
        cohort="TCGA-LUAD",
        gene="CD274",
        entrez_gene_id=29126,
        study_id="luad_tcga_pan_can_atlas_2018",
        benchmark_directory="luad_cd274_os_cutpoint_benchmark",
        prespecified_role="unsupported or weak-signal case",
    ),
)


def main() -> int:
    args = parse_args()
    if args.check_only:
        verify_frozen_outputs()
        print("External concordance panel outputs verified.")
        return 0
    selected = select_cases(args.case)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for case in selected:
        case_dir = OUTPUT_DIR / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = case_dir / "cbioportal_snapshot.json.gz"
        if args.render_existing:
            snapshot = read_gzip_json(snapshot_path)
        else:
            snapshot = fetch_snapshot(case, accessed_date=args.access_date)
            write_gzip_json(snapshot_path, snapshot)
        input_rows, selection = build_external_input(snapshot, case)
        input_path = case_dir / "external_input.csv"
        write_input_csv(input_path, input_rows)
        result_path = case_dir / "external_survival_result.json"
        run_r_analysis(
            input_path,
            result_path,
            rscript_bin=args.rscript_bin,
            docker_compose_service=args.docker_compose_service,
        )
        external = read_json(result_path)
        trace = load_trace_median_result(case)
        result = assemble_case_result(
            case,
            snapshot=snapshot,
            snapshot_path=snapshot_path,
            selection=selection,
            external=external,
            trace=trace,
        )
        write_json(case_dir / "comparison.json", result)
        results.append(result)

    payload = {
        "schema_version": "tcga-trace-external-concordance-panel-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prespecification": {
            "document": "docs/publication/concordance_validation_plan.md",
            "status_date": "2026-07-23",
            "statement": (
                "The three marker-cohort cases and their supported, discordant "
                "and unsupported roles were documented before this panel was run."
            ),
        },
        "external_source": {
            "tool": "cBioPortal",
            "dataset_family": "TCGA PanCancer Atlas",
            "api_base": API_BASE,
            "api_documentation": "https://docs.cbioportal.org/web-api-and-clients/",
        },
        "comparison_contract": {
            "endpoint": "OS",
            "cutoff": "median",
            "contrast": "High vs Low",
            "sample_rule": sample_selection_rule(),
            "external_cox": "univariable Cox with Efron ties",
            "interpretation": (
                "Directional and nominal-support concordance are descriptive "
                "software checks, not independent biomarker validation."
            ),
        },
        "cases": results,
    }
    write_json(OUTPUT_DIR / "panel_results.raw.json", payload)
    write_summary_csv(OUTPUT_DIR / "summary.csv", results)
    write_summary_markdown(OUTPUT_DIR / "summary.md", payload)
    write_manifest()
    verify_frozen_outputs()
    print(f"Wrote {OUTPUT_DIR / 'summary.md'}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a frozen three-case external survival concordance panel "
            "against the official cBioPortal API."
        )
    )
    parser.add_argument(
        "--access-date",
        default=date.today().isoformat(),
        help="Access date recorded with newly downloaded API responses.",
    )
    parser.add_argument(
        "--case",
        action="append",
        choices=[case.case_id for case in CASES],
        help="Run only one registered case; may be repeated.",
    )
    parser.add_argument("--render-existing", action="store_true")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Verify frozen snapshots and generated panel files without rerunning R.",
    )
    parser.add_argument("--rscript-bin", default="Rscript")
    parser.add_argument("--docker-compose-service", default="backend")
    return parser.parse_args()


def select_cases(requested: list[str] | None) -> tuple[ConcordanceCase, ...]:
    if not requested:
        return CASES
    selected_ids = set(requested)
    return tuple(case for case in CASES if case.case_id in selected_ids)


def fetch_snapshot(
    case: ConcordanceCase,
    *,
    accessed_date: str,
) -> dict[str, Any]:
    study = api_get(f"/studies/{case.study_id}")
    profiles = api_get(f"/studies/{case.study_id}/molecular-profiles")
    sample_lists = api_get(f"/studies/{case.study_id}/sample-lists")
    samples = api_get(
        f"/studies/{case.study_id}/samples",
        query={"pageSize": 10_000_000},
    )
    clinical = api_get(
        f"/studies/{case.study_id}/clinical-data",
        query={
            "clinicalDataType": "PATIENT",
            "projection": "SUMMARY",
            "pageSize": 10_000_000,
        },
    )
    profile = select_expression_profile(profiles, case.study_id)
    sample_list = select_expression_sample_list(sample_lists, case.study_id)
    expression = api_post(
        f"/molecular-profiles/{profile['molecularProfileId']}/molecular-data/fetch",
        {
            "sampleListId": sample_list["sampleListId"],
            "entrezGeneIds": [case.entrez_gene_id],
        },
        query={"projection": "DETAILED"},
    )
    return {
        "schema_version": "tcga-trace-cbioportal-source-snapshot-v1",
        "accessed_date": accessed_date,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "api_base": API_BASE,
        "case": case.__dict__,
        "requests": {
            "study": f"/studies/{case.study_id}",
            "profiles": f"/studies/{case.study_id}/molecular-profiles",
            "sample_lists": f"/studies/{case.study_id}/sample-lists",
            "samples": f"/studies/{case.study_id}/samples?pageSize=10000000",
            "clinical": (
                f"/studies/{case.study_id}/clinical-data?"
                "clinicalDataType=PATIENT&projection=SUMMARY&pageSize=10000000"
            ),
            "expression": (
                f"/molecular-profiles/{profile['molecularProfileId']}/"
                "molecular-data/fetch?projection=DETAILED"
            ),
        },
        "study": study,
        "selected_profile": profile,
        "selected_sample_list": sample_list,
        "samples": samples,
        "clinical_data": clinical,
        "expression_data": expression,
    }


def api_get(path: str, *, query: dict[str, Any] | None = None) -> Any:
    url = f"{API_BASE}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:
        return json.load(response)


def api_post(
    path: str,
    payload: dict[str, Any],
    *,
    query: dict[str, Any] | None = None,
) -> Any:
    url = f"{API_BASE}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urlopen(request, timeout=120) as response:
        return json.load(response)


def select_expression_profile(
    profiles: list[dict[str, Any]],
    study_id: str,
) -> dict[str, Any]:
    expected = f"{study_id}_rna_seq_v2_mrna"
    matches = [
        profile
        for profile in profiles
        if profile.get("molecularProfileId") == expected
        and profile.get("datatype") == "CONTINUOUS"
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one continuous RSEM profile {expected}.")
    return matches[0]


def select_expression_sample_list(
    sample_lists: list[dict[str, Any]],
    study_id: str,
) -> dict[str, Any]:
    expected = f"{study_id}_rna_seq_v2_mrna"
    matches = [
        sample_list
        for sample_list in sample_lists
        if sample_list.get("sampleListId") == expected
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one expression sample list {expected}.")
    return matches[0]


def build_external_input(
    snapshot: dict[str, Any],
    case: ConcordanceCase,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sample_metadata = {
        str(sample["sampleId"]): sample for sample in snapshot.get("samples") or []
    }
    clinical_by_patient: dict[str, dict[str, str]] = {}
    for record in snapshot.get("clinical_data") or []:
        patient_id = str(record.get("patientId") or "")
        attribute = str(record.get("clinicalAttributeId") or "")
        if patient_id and attribute:
            clinical_by_patient.setdefault(patient_id, {})[attribute] = str(
                record.get("value") or ""
            )

    candidates_by_patient: dict[str, list[dict[str, Any]]] = {}
    for record in snapshot.get("expression_data") or []:
        if int(record.get("entrezGeneId") or 0) != case.entrez_gene_id:
            continue
        sample_id = str(record.get("sampleId") or "")
        sample = sample_metadata.get(sample_id) or {}
        patient_id = str(record.get("patientId") or sample.get("patientId") or "")
        expression = finite_float(record.get("value"))
        clinical = clinical_by_patient.get(patient_id) or {}
        time_months = finite_float(clinical.get("OS_MONTHS"))
        event = parse_os_event(clinical.get("OS_STATUS"))
        if (
            not patient_id
            or expression is None
            or time_months is None
            or time_months < 0
            or event is None
        ):
            continue
        candidates_by_patient.setdefault(patient_id, []).append(
            {
                "patient_id": patient_id,
                "sample_id": sample_id,
                "sample_type": str(sample.get("sampleType") or ""),
                "expression": expression,
                "time_months": time_months,
                "event": event,
            }
        )

    selected = []
    patients_with_multiple = 0
    for patient_id in sorted(candidates_by_patient):
        candidates = candidates_by_patient[patient_id]
        if len(candidates) > 1:
            patients_with_multiple += 1
        selected.append(min(candidates, key=sample_priority_key))
    if len(selected) < 10 or sum(row["event"] for row in selected) < 5:
        raise RuntimeError(f"{case.case_id} failed external endpoint QC.")
    return selected, {
        "expression_records": len(snapshot.get("expression_data") or []),
        "patients_with_complete_os_and_expression": len(selected),
        "events": sum(row["event"] for row in selected),
        "patients_with_multiple_eligible_samples": patients_with_multiple,
        "rule": sample_selection_rule(),
    }


def sample_priority_key(row: dict[str, Any]) -> tuple[int, str]:
    sample_id = str(row.get("sample_id") or "")
    sample_code = sample_id.split("-")[3][:2] if len(sample_id.split("-")) >= 4 else ""
    code_priority = {
        "01": 0,
        "03": 0,
        "09": 0,
        "02": 10,
        "04": 10,
        "40": 10,
        "05": 20,
        "06": 30,
        "07": 30,
        "08": 40,
    }.get(sample_code, 90)
    return code_priority, sample_id


def sample_selection_rule() -> str:
    return (
        "Among cBioPortal samples with the requested expression value and complete "
        "OS_MONTHS/OS_STATUS, select one sample per patient using TCGA sample-code "
        "priority: primary, recurrent, additional primary, metastatic, other; "
        "resolve ties lexicographically by sample ID."
    )


def parse_os_event(value: Any) -> int | None:
    normalized = str(value or "").strip().upper()
    if normalized.startswith("1:") or normalized in {"1", "DECEASED", "DEAD"}:
        return 1
    if normalized.startswith("0:") or normalized in {"0", "LIVING", "ALIVE"}:
        return 0
    return None


def finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in {float("inf"), float("-inf")}:
        return None
    return number


def write_input_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ("patient_id", "sample_id", "sample_type", "expression", "time_months", "event")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run_r_analysis(
    input_path: Path,
    output_path: Path,
    *,
    rscript_bin: str,
    docker_compose_service: str,
) -> None:
    executable = shutil.which(rscript_bin)
    if executable:
        command = [executable, str(R_SCRIPT), str(input_path), str(output_path)]
    else:
        command = [
            "docker",
            "compose",
            "run",
            "--rm",
            "--no-deps",
            "-v",
            f"{ROOT}:/workspace",
            "-w",
            "/workspace",
            docker_compose_service,
            "Rscript",
            "/workspace/scripts/publication/external_concordance.R",
            f"/workspace/{input_path.relative_to(ROOT)}",
            f"/workspace/{output_path.relative_to(ROOT)}",
        ]
    subprocess.run(command, cwd=ROOT, check=True)


def load_trace_median_result(case: ConcordanceCase) -> dict[str, Any]:
    path = (
        ROOT
        / "docs"
        / "publication"
        / "benchmark"
        / case.benchmark_directory
        / "summary.csv"
    )
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    matches = [row for row in rows if row.get("method") == "median"]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one median row in {path}.")
    row = matches[0]
    return {
        "analysis_id": row["analysis_id"],
        "cohort": row["cohort"],
        "gene": row["gene_symbol"],
        "endpoint": row["endpoint"],
        "endpoint_source": row["endpoint_source"],
        "expression_scale": "log2(TPM + 1)",
        "n_patients": int(row["n_patients"]),
        "n_events": int(row["n_events"]),
        "cutoff_value": float(row["threshold"]),
        "group_counts": json.loads(row["group_counts"]),
        "event_counts": json.loads(row["event_counts"]),
        "median_survival_days": json.loads(row["median_survival_days"]),
        "logrank_p_value": float(row["logrank_p_value"]),
        "grouped_holm_p_value": float(row["grouped_holm_p_value"]),
        "cox": {
            "hazard_ratio": float(row["univariable_hr"]),
            "conf_low": float(row["univariable_hr_conf_low"]),
            "conf_high": float(row["univariable_hr_conf_high"]),
            "p_value": float(row["univariable_p_value"]),
        },
        "age_adjusted_cox": {
            "hazard_ratio": float(row["adjusted_hr"]),
            "conf_low": float(row["adjusted_hr_conf_low"]),
            "conf_high": float(row["adjusted_hr_conf_high"]),
            "p_value": float(row["adjusted_p_value"]),
        },
        "reproducibility_hash": row["audit_reproducibility_hash"],
        "patient_records_sha256": row["patient_records_sha256"],
    }


def assemble_case_result(
    case: ConcordanceCase,
    *,
    snapshot: dict[str, Any],
    snapshot_path: Path,
    selection: dict[str, Any],
    external: dict[str, Any],
    trace: dict[str, Any],
) -> dict[str, Any]:
    external_hr = float(external["cox"]["hazard_ratio"])
    trace_hr = float(trace["cox"]["hazard_ratio"])
    external_direction = direction_from_hr(external_hr)
    trace_direction = direction_from_hr(trace_hr)
    external_supported = float(external["cox"]["p_value"]) < 0.05
    trace_nominal_supported = float(trace["cox"]["p_value"]) < 0.05
    trace_holm_supported = float(trace["grouped_holm_p_value"]) < 0.05
    if (
        external_direction != trace_direction
        and not external_supported
        and not trace_nominal_supported
    ):
        decision = "both_unsupported_point_direction_differs"
    elif external_direction != trace_direction:
        decision = "direction_discordant"
    elif external_supported == trace_nominal_supported:
        decision = (
            "direction_and_nominal_support_concordant"
            if external_supported
            else "direction_concordant_null"
        )
    else:
        decision = "direction_concordant_nominal_support_discordant"
    return {
        "case_id": case.case_id,
        "prespecified_role": case.prespecified_role,
        "accessed_date": snapshot["accessed_date"],
        "cohort": case.cohort,
        "gene": case.gene,
        "endpoint": "OS",
        "cutoff": "median",
        "external": {
            "tool": "cBioPortal",
            "study": snapshot["study"],
            "molecular_profile": snapshot["selected_profile"],
            "sample_list": snapshot["selected_sample_list"],
            "expression_processing": (
                "Batch-normalized RSEM from Illumina HiSeq RNASeqV2 as labelled "
                "by cBioPortal PanCancer Atlas."
            ),
            "selection": selection,
            "result": external,
            "source_snapshot": str(snapshot_path.relative_to(ROOT)),
            "source_snapshot_sha256": file_sha256(snapshot_path),
        },
        "tcga_trace": trace,
        "comparison": {
            "external_direction": external_direction,
            "tcga_trace_direction": trace_direction,
            "external_nominal_supported": external_supported,
            "tcga_trace_nominal_supported": trace_nominal_supported,
            "tcga_trace_holm_supported": trace_holm_supported,
            "decision": decision,
            "independent_validation": False,
            "limitations": [
                "Both resources derive from TCGA and therefore are not independent biological validation.",
                "cBioPortal PanCancer Atlas RSEM and TCGA-TRACE GDC STAR-count TPM are different expression pipelines and releases.",
                "cBioPortal OS fields and TCGA-TRACE TCGA-CDR OS may differ in endpoint curation and eligible participants.",
                "The external model is unadjusted; TCGA-TRACE additionally reports an exact age-adjusted model.",
                "A median split is rank-comparable but its numerical expression threshold is not comparable across pipelines.",
            ],
        },
    }


def direction_from_hr(hr: float) -> str:
    if hr < 1:
        return "higher expression protective"
    if hr > 1:
        return "higher expression adverse"
    return "null"


def write_summary_csv(path: Path, results: list[dict[str, Any]]) -> None:
    rows = []
    for result in results:
        external = result["external"]["result"]
        trace = result["tcga_trace"]
        rows.append(
            {
                "case_id": result["case_id"],
                "accessed_date": result["accessed_date"],
                "cohort": result["cohort"],
                "gene": result["gene"],
                "external_study": result["external"]["study"]["studyId"],
                "external_n": external["n_patients"],
                "external_events": external["n_events"],
                "external_hr": external["cox"]["hazard_ratio"],
                "external_conf_low": external["cox"]["conf_low"],
                "external_conf_high": external["cox"]["conf_high"],
                "external_cox_p": external["cox"]["p_value"],
                "external_logrank_p": external["logrank"]["p_value"],
                "trace_n": trace["n_patients"],
                "trace_events": trace["n_events"],
                "trace_hr": trace["cox"]["hazard_ratio"],
                "trace_conf_low": trace["cox"]["conf_low"],
                "trace_conf_high": trace["cox"]["conf_high"],
                "trace_cox_p": trace["cox"]["p_value"],
                "trace_logrank_p": trace["logrank_p_value"],
                "trace_grouped_holm_p": trace["grouped_holm_p_value"],
                "decision": result["comparison"]["decision"],
                "snapshot_sha256": result["external"]["source_snapshot_sha256"],
                "trace_reproducibility_hash": trace["reproducibility_hash"],
            }
        )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_summary_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# External Concordance Panel",
        "",
        "Status: completed.",
        "",
        (
            "These three cases were listed in "
            "`docs/publication/concordance_validation_plan.md` on 2026-07-23, "
            "before this panel was executed. The comparison is a cross-pipeline "
            "software check, not independent validation because both resources use TCGA."
        ),
        "",
        "| Case | cBioPortal n/events | cBioPortal HR (95% CI) | p | TCGA-TRACE n/events | TCGA-TRACE HR (95% CI) | p / Holm p | Decision |",
        "| --- | ---: | --- | ---: | ---: | --- | --- | --- |",
    ]
    for result in payload["cases"]:
        external = result["external"]["result"]
        trace = result["tcga_trace"]
        lines.append(
            f"| {result['gene']}/{result['cohort'].removeprefix('TCGA-')} OS | "
            f"{external['n_patients']}/{external['n_events']} | "
            f"{format_hr(external['cox'])} | {format_p(external['cox']['p_value'])} | "
            f"{trace['n_patients']}/{trace['n_events']} | "
            f"{format_hr(trace['cox'])} | {format_p(trace['cox']['p_value'])} / "
            f"{format_p(trace['grouped_holm_p_value'])} | "
            f"{result['comparison']['decision'].replace('_', ' ')} |"
        )
    lines.extend(
        [
            "",
            "## Contract and limits",
            "",
            f"- External source: {payload['external_source']['tool']} "
            f"{payload['external_source']['dataset_family']}.",
            f"- Cutoff/model: {payload['comparison_contract']['cutoff']}; "
            f"{payload['comparison_contract']['external_cox']}.",
            f"- Sample rule: {payload['comparison_contract']['sample_rule']}",
            "- Expression is not on a common numerical scale: cBioPortal uses its PanCancer Atlas RSEM profile; TCGA-TRACE uses GDC STAR-count log2(TPM + 1).",
            "- Endpoint and patient sets can differ because cBioPortal clinical OS and TCGA-CDR OS are curated separately.",
            "- No result is described as an exact replication or independent validation.",
            "",
            "Each case directory contains the gzipped API snapshot, selected patient-level input, external survival output and comparison JSON.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def format_hr(cox: dict[str, Any]) -> str:
    return (
        f"{float(cox['hazard_ratio']):.2f} "
        f"({float(cox['conf_low']):.2f}-{float(cox['conf_high']):.2f})"
    )


def format_p(value: Any) -> str:
    number = float(value)
    return f"{number:.2e}" if number < 0.001 else f"{number:.3f}"


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_gzip_json(path: Path, payload: Any) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def read_gzip_json(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest() -> None:
    manifest_path = OUTPUT_DIR / "manifest.json"
    paths = [
        path
        for path in OUTPUT_DIR.rglob("*")
        if path.is_file() and path != manifest_path
    ]
    write_json(
        manifest_path,
        {
            "schema_version": "tcga-trace-external-concordance-manifest-v1",
            "files": {
                str(path.relative_to(OUTPUT_DIR)): {
                    "bytes": path.stat().st_size,
                    "sha256": file_sha256(path),
                }
                for path in sorted(paths)
            },
        },
    )


def verify_frozen_outputs() -> None:
    manifest_path = OUTPUT_DIR / "manifest.json"
    panel_path = OUTPUT_DIR / "panel_results.raw.json"
    if not manifest_path.is_file() or not panel_path.is_file():
        raise FileNotFoundError("External concordance panel outputs are incomplete.")
    manifest = read_json(manifest_path)
    if (
        manifest.get("schema_version")
        != "tcga-trace-external-concordance-manifest-v1"
    ):
        raise RuntimeError("Unexpected external concordance manifest schema.")
    for relative, expected in (manifest.get("files") or {}).items():
        path = OUTPUT_DIR / relative
        if (
            not path.is_file()
            or path.stat().st_size != expected.get("bytes")
            or file_sha256(path) != expected.get("sha256")
        ):
            raise RuntimeError(f"Frozen concordance file failed integrity: {relative}")

    payload = read_json(panel_path)
    if payload.get("schema_version") != "tcga-trace-external-concordance-panel-v1":
        raise RuntimeError("Unexpected external concordance panel schema.")
    cases = payload.get("cases") or []
    if [case.get("case_id") for case in cases] != [
        registered.case_id for registered in CASES
    ]:
        raise RuntimeError("Frozen concordance cases differ from the registered panel.")
    for case in cases:
        external = case.get("external") or {}
        snapshot = ROOT / str(external.get("source_snapshot") or "")
        if (
            not snapshot.is_file()
            or file_sha256(snapshot) != external.get("source_snapshot_sha256")
        ):
            raise RuntimeError(
                f"Source snapshot hash mismatch for {case.get('case_id')}."
            )
        result = external.get("result") or {}
        trace = case.get("tcga_trace") or {}
        if (
            result.get("status") != "completed"
            or int(result.get("n_patients") or 0) < 10
            or int(result.get("n_events") or 0) < 5
            or not str(trace.get("reproducibility_hash") or "")
            or not str((case.get("comparison") or {}).get("decision") or "")
        ):
            raise RuntimeError(
                f"Incomplete concordance evidence for {case.get('case_id')}."
            )


if __name__ == "__main__":
    sys.exit(main())
