"""Human-readable and tabular views of the same recorded survival analysis."""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path


STAGE_LABELS = {
    "molecular_population": "Declared tissue population",
    "filter_sample_type": "Sample type", "filter_stage": "Stage",
    "filter_grade": "Grade", "filter_gender": "Sex", "filter_race": "Race",
    "filter_age_min": "Minimum age", "filter_age_max": "Maximum age",
    "custom_clinical_filters": "Additional clinical filters",
    "endpoint_completeness": "Usable survival endpoint",
    "expression_completeness": "Complete requested expression",
    "one_sample_per_patient": "One sample per patient",
}


def selection_manifest(selection: dict, grouped: list[dict], continuous: list[dict] | None) -> list[dict]:
    group_by_barcode = {row["sample_barcode"]: row.get("group") for row in grouped}
    continuous_barcodes = {row["sample_barcode"] for row in continuous or []}
    ledger = (selection.get("selection_audit") or {}).get("records") or []
    result = []
    for entry in ledger:
        row = dict(entry)
        barcode = row["sample_barcode"]
        row.update(
            in_grouped_analysis=barcode in group_by_barcode,
            in_continuous_input=(barcode in continuous_barcodes if continuous is not None else None),
            group=group_by_barcode.get(barcode),
            grouping_exclusion=("not_assigned_to_a_retained_group" if row["status"] == "retained" and barcode not in group_by_barcode else None),
        )
        result.append(row)
    return result


def write_audit_tables(directory: Path, manifest: list[dict], provenance: dict) -> dict[str, str]:
    tables = {
        "cohort_manifest": (manifest, ["patient_id", "sample_barcode", "sample_type", "status", "excluded_at", "patient_retained", "in_grouped_analysis", "in_continuous_input", "group", "grouping_exclusion"]),
        "source_files": (provenance.get("selected_gdc_file_identifiers") or [], ["sample_barcode", "gdc_file_uuid", "gdc_filename_prefix", "gdc_filename"]),
    }
    paths = {}
    for name, (records, fields) in tables.items():
        path = directory / f"{name}.csv"
        if not records:
            path.unlink(missing_ok=True)
            continue
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(records)
        paths[name] = str(path)
    return paths


def esc(value) -> str:
    if value is None:
        return "Not recorded"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return html.escape(str(value), quote=True)


def table_rows(items) -> str:
    return "".join(f'<tr><th scope="row">{esc(label)}</th><td>{esc(value)}</td></tr>' for label, value in items)


def render_cohort_section(report: dict) -> str:
    cohort = report.get("cohort_selection") or {}
    selection = cohort.get("sample_selection") or {}
    trail = selection.get("selection_audit") or {}
    stages = trail.get("stages") or []
    body = "".join(
        '<tr>' + f'<th scope="row">{esc(STAGE_LABELS.get(row["stage"], row["stage"]))}</th>'
        + "".join(f'<td>{esc(row.get(key))}</td>' for key in ("input_samples", "removed_samples", "retained_samples", "removed_patients", "retained_patients")) + '</tr>'
        for row in stages
    )
    if not stages:
        # Legacy reports have counts but cannot reconstruct individual exclusion reasons.
        body = '<tr><td colspan="6">Step-level records were not captured for this analysis. Original selection counts are retained in the full audit JSON.</td></tr>'
    manifest = cohort.get("selection_manifest") or []
    preview = "".join(
        '<tr>' + ''.join(f'<td>{esc(row.get(key))}</td>' for key in ("patient_id", "sample_barcode", "status", "excluded_at", "patient_retained", "group")) + '</tr>'
        for row in manifest[:50]
    )
    ledger_view = (
        f'<details><summary>Sample decisions: first {min(50, len(manifest))} of {len(manifest)} records</summary>'
        '<p>The complete cohort_manifest.csv is included in Bundle ZIP. A removed sample may belong to a patient retained through another sample.</p>'
        '<div class="table-scroll" tabindex="0" role="region" aria-label="Sample decisions"><table><thead><tr><th>Patient</th><th>Sample</th><th>Decision</th><th>First exclusion step</th><th>Patient retained</th><th>Group</th></tr></thead>'
        f'<tbody>{preview}</tbody></table></div></details>' if manifest else ''
    )
    return f'''<section id="cohort"><h2>2. Cohort construction</h2>
    <p>Steps are sequential. Patient exclusions count people with no sample remaining after that step.</p>
    <div class="table-scroll" tabindex="0" role="region" aria-label="Cohort construction"><table>
    <thead><tr><th scope="col">Step</th><th scope="col">Samples in</th><th scope="col">Samples removed</th><th scope="col">Samples left</th><th scope="col">Patients removed</th><th scope="col">Patients left</th></tr></thead><tbody>{body}</tbody></table></div>
    <p><strong>Selection rule:</strong> {esc(selection.get("rule_description"))}</p>
    <p>Grouped analysis: {esc(cohort.get("patient_record_count"))} patients. Continuous input: {esc(cohort.get("continuous_patient_record_count"))} patients. Adjusted models can use smaller complete-case populations; their counts are reported with each model.</p>
    {ledger_view}</section>'''


def render_source_metadata(report: dict) -> str:
    provenance = (report.get("data") or {}).get("provenance") or {}
    metadata = provenance.get("source_metadata") or {}
    completeness = provenance.get("provenance_completeness") or {}
    labels = [("data_release", "Source data release"), ("retrieval_date", "Source retrieval date"), ("genome_assembly", "Genome assembly"), ("gene_annotation", "Gene annotation"), ("workflow_type", "Upstream workflow"), ("expression_source_column", "Expression source column"), ("download_query", "Download query")]
    status = lambda key: "Recorded" if completeness.get(key) is True else "Not recorded"
    return '<details><summary>Source metadata and coverage</summary><table>' + table_rows(
        [(label, metadata.get(key)) for key, label in labels] + [
            ("Exact expression matrix checksum", status("exact_expression_artifact_hashed")),
            ("GDC file IDs for all selected samples", status("selected_gdc_identifiers_recorded")),
        ]
    ) + '</table><p>Missing metadata is not inferred from current provider data or local file timestamps. File checksums identify the bytes used; they do not ensure future access to the source files.</p></details>'


def render_analysis_section(report: dict) -> str:
    design = report.get("analysis_design") or {}
    endpoint = (report.get("data") or {}).get("endpoint") or {}
    selection = (report.get("cohort_selection") or {}).get("sample_selection") or {}
    filters = design.get("filters") or {}
    filter_items = []
    for key, label in [("sample_types", "Sample types"), ("stages", "Stages"), ("grades", "Grades"), ("genders", "Sex"), ("races", "Race"), ("age_min", "Minimum age"), ("age_max", "Maximum age")]:
        value = filters.get(key)
        if value is not None and value != []:
            filter_items.append((label, ", ".join(map(str, value)) if isinstance(value, list) else value))
    for item in selection.get("custom_clinical_filters") or []:
        criterion = item.get("filter") or {}
        value = ", ".join(map(str, criterion["levels"])) if "levels" in criterion else criterion
        filter_items.append((item.get("variable_label") or item.get("variable_id"), value))
    if filters.get("custom_filters") and not selection.get("custom_clinical_filters"):
        filter_items.append(("Additional filters", filters["custom_filters"]))
    population = (selection.get("sample_population") or {}).get("label") or filters.get("sample_population")
    return '<section id="analysis"><h2>3. Analysis specification</h2><table>' + table_rows([
        ("Endpoint definition", endpoint.get("definition")),
        ("Tissue population", population),
        *(filter_items or [("Additional clinical filters", "None selected")]),
        ("Administrative follow-up cutoff (days)", filters.get("max_time_days") if filters.get("max_time_days") is not None else "None selected"),
        ("Grouping method", design.get("cutpoint_method")),
        ("Actual cutpoints", design.get("cutpoint_details")),
        ("Clinical covariates", design.get("adjustment_covariates") or []),
        ("Additional covariates", design.get("external_adjustment_covariates") or []),
        ("Time unit", design.get("time_unit")),
    ]) + '</table></section>'


def render_reproduction_section(report: dict) -> str:
    pipeline = report.get("pipeline") or {}
    return '<section id="reproduce"><h2>5. Reproduce and verify</h2><p>Download Bundle ZIP and follow REPRODUCE.md to rerun the statistical analysis from the retained processed inputs. The bundle contains the available scripts, patient data and environment specification. Rebuilding the original upstream expression dataset is outside this capsule.</p><table>' + table_rows([
        ("Analysis method version", pipeline.get("version")),
        ("Application release commit", pipeline.get("release_commit")),
        ("Application release ref", pipeline.get("release_ref")),
        ("Software versions", pipeline.get("software_versions")),
    ]) + '</table><p>Output filenames and checksums below link the generated results to this record. Figures assembled outside TRACE require their own link to these outputs.</p></section>'
