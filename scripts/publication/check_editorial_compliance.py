#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import struct
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANUSCRIPT_DIR = ROOT / "manuscript/bioinformatics_app_note"
MAIN = MANUSCRIPT_DIR / "main.tex"
SUPPLEMENT = MANUSCRIPT_DIR / "supplementary.tex"
DEFAULT_OUP_PDF = MANUSCRIPT_DIR / "build/tcga-trace-bioinformatics-oup-preview.pdf"
OUP_SOURCE = MANUSCRIPT_DIR / "build/oup_preview.tex"
MAX_OUP_PAGES = 4
EXPECTED_OUP_PAGE_SIZE = (595.276, 782.362)
OUP_PAGE_SIZE_TOLERANCE = 1.0
MIN_FULL_WIDTH_PIXELS = 2450
EXPECTED_SUPPLEMENT_TABLES = 8
EXPECTED_SUPPLEMENT_FIGURES = 0
EXPECTED_AUTHORS = [
    "Sergio Hernández-Galaz",
    "Andrés Hernández-Oliveras",
    "Ignacio Pezoa-Soto",
    "Javiera Reyes-Alvarez",
    "Vincenzo Benedetti",
    "Alberto J. M. Martin",
    "Alvaro Lladser",
]
EXPECTED_AFFILIATIONS = 4
ABSTRACT_HEADINGS = [
    "Summary",
    "Availability and Implementation",
    "Contact",
    "Supplementary information",
]
PAPER_EXAMPLE_IDENTIFIERS = [
    "LIHC/CDC20/OS",
    "LUAD/BIRC5/OS",
    "UVM/BAP1/DSS",
    "SKCM/TMEM176B/OS",
    "LGG/EMP3/OS",
    "KIRC/CA9/OS",
    "BRCA/MKI67/OS",
    "BRCA/MKI67/PFI",
    "SKCM/PDCD1/OS",
    "LUAD/CD274/OS",
    "LUAD/CD274/PFI",
    "ACC/BUB1B-PINK1/OS",
    "UVM/BAP1xPRAME/DSS",
    "PAN-CANCER/BIRC5/OS",
    "KIRC/HYPOXIA/OS",
    "SKCM/EFFECTORxEXHAUSTION/OS",
    "PAN-CANCER/CA9/OS",
]
MAIN_SECTION_SEQUENCE = [
    r"\section{Introduction}",
    r"\section{Methods}",
    r"\section{Case Studies and Evaluation}",
    r"\section{Future Plans}",
]
METHOD_SUBSECTIONS = [
    r"\subsection{Data and cohort construction}",
    r"\subsection{Survival analyses}",
    r"\subsection{Web server and run record}",
]
EXPECTED_CASE_TITLES = [
    "Case 1: CDC20 in Hepatocellular Cancer",
    "Case 2: BUB1B--PINK1 in ACC",
    "Case 3: BIRC5 Across TCGA Cohorts",
    "Case 4: BAP1/PRAME in Uveal Melanoma",
]
COMPARATOR_CITATION_KEYS = [
    "gepia22019",
    "kmplotter2021",
    "ualcan2022",
    "csurvival2022",
    "dousurvive2023",
    "pessa2024",
    "xena2020",
    "cbioportal2012",
    "timer2020",
    "survexpress2013",
    "tcgabiolinks2016",
    "tcgaplot2023",
    "prognoscan2009",
    "oncolnc2016",
    "capssa2019",
    "esurv2020",
    "gsca2023",
    "tcgex2025",
    "survboard2025",
    "survivalGenie2026",
]
SCREENSHOTS = [
    MANUSCRIPT_DIR / "figures/tcga_trace_ui_analysis.png",
    MANUSCRIPT_DIR / "figures/tcga_trace_ui_multiverse.png",
]
MAIN_FIGURE_INPUT = r"\input{figures/graphical_abstract}"
MAIN_FIGURE_SOURCE = MANUSCRIPT_DIR / "figures/graphical_abstract.tex"
SUPPLEMENT_TABLE_SEQUENCE = [
    r"\label{tab:supp-comparator-matrix}",
    r"\input{tables/feature_signature_definitions}",
    r"\input{tables/reproducibility_benchmark}",
    r"\input{tables/single_gene_benchmark_full_overview}",
    r"\input{tables/feature_benchmark_summary}",
    r"\input{tables/feature_benchmark_diagnostic_summary}",
    r"\input{tables/statistical_calibration}",
    r"\input{tables/runtime_concurrency_benchmark}",
]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    failures: list[str] = []
    notes: list[str] = []

    try:
        main_text = MAIN.read_text(encoding="utf-8")
        supplement_text = SUPPLEMENT.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Editorial compliance check failed: {exc}", file=sys.stderr)
        return 1

    check_review_format(main_text, failures)
    check_title_and_structure(main_text, failures, notes)
    check_abstract(main_text, failures, notes)
    check_main_floats(main_text, failures, notes)
    check_evidence_narrative(main_text, supplement_text, failures, notes)
    check_paper_example_coverage(supplement_text, failures, notes)
    check_supplement(supplement_text, failures, notes)
    check_supplement_order_and_cutpoints(
        main_text,
        supplement_text,
        failures,
        notes,
    )
    check_oup_source(OUP_SOURCE, failures, notes)
    check_oup_pages(resolve_repo_path(args.oup_pdf), failures, notes)

    print("Bioinformatics editorial compliance:")
    for note in notes:
        print(f"- OK {note}")
    if failures:
        print("Editorial blockers:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("- OK no technical editorial blockers detected")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check the technical Bioinformatics Application Note constraints "
            "that can be verified from the manuscript artifacts."
        )
    )
    parser.add_argument(
        "--oup-pdf",
        type=Path,
        default=DEFAULT_OUP_PDF,
        help=f"OUP two-column preview PDF. Default: {DEFAULT_OUP_PDF.relative_to(ROOT)}",
    )
    return parser.parse_args(argv)


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def check_review_format(text: str, failures: list[str]) -> None:
    required = {
        r"\documentclass[12pt]{article}": "main manuscript is not 12-point review format",
        r"\linenumbers": "main manuscript does not enable line numbering",
        r"\doublespacing": "main manuscript does not enable double spacing",
    }
    for marker, message in required.items():
        if marker not in text:
            failures.append(message)


def check_title_and_structure(text: str, failures: list[str], notes: list[str]) -> None:
    title_match = re.search(r"\\title\{([^{}]+)\}", text)
    if not title_match:
        failures.append("main manuscript is missing a simple \\title{...} command")
    else:
        title = latex_to_plain(title_match.group(1))
        if not title.startswith("TCGA-TRACE:"):
            failures.append("title must begin with the application name `TCGA-TRACE:`")
        if len(title) > 75:
            failures.append(f"title is {len(title)} characters; writing blueprint limit is 75")
        forbidden = re.findall(r"\b(?:tool|package|application|software)\b", title, flags=re.IGNORECASE)
        if forbidden:
            failures.append(f"title contains discouraged generic term(s): {', '.join(forbidden)}")
        if not failures:
            notes.append(f"title is specific and concise ({len(title)}/75 characters)")

    section_positions = [text.find(marker) for marker in MAIN_SECTION_SEQUENCE]
    if any(position < 0 for position in section_positions):
        missing = [
            marker
            for marker, position in zip(MAIN_SECTION_SEQUENCE, section_positions)
            if position < 0
        ]
        failures.append("main narrative is missing required section(s): " + ", ".join(missing))
    elif section_positions != sorted(section_positions):
        failures.append("main narrative sections do not follow the writing-blueprint order")
    else:
        notes.append(
            "main narrative follows Introduction, Methods, Case Studies and Future Plans"
        )

    missing_subsections = [marker for marker in METHOD_SUBSECTIONS if marker not in text]
    if missing_subsections:
        failures.append("Methods is missing required subsection(s): " + ", ".join(missing_subsections))

    case_titles = re.findall(r"\\subsection\{(Case \d+:[^}]*)\}", text)
    if len(case_titles) != 4:
        failures.append(f"main narrative must contain four case studies; found {len(case_titles)}")
    else:
        question_titles = [title for title in case_titles if "?" in title]
        if question_titles:
            failures.append(
                "case-study titles must be declarative rather than questions: "
                + ", ".join(question_titles)
            )
        long_titles = [title for title in case_titles if len(latex_to_plain(title)) > 40]
        if long_titles:
            failures.append(
                "case-study titles exceed the 40-character readability target: "
                + ", ".join(long_titles)
            )
        if not question_titles and not long_titles:
            notes.append("four concise declarative case-study headings are present")
        if case_titles != EXPECTED_CASE_TITLES:
            failures.append(
                "case-study sequence does not match the evidence narrative: "
                + " | ".join(case_titles)
            )


def check_evidence_narrative(
    main_text: str,
    supplement_text: str,
    failures: list[str],
    notes: list[str],
) -> None:
    required_main = [
        r"\subsection*{Technical validation}",
        "retains supported, unsupported, nonlinear, sparse-event and PH-discordant",
        "chosen post hoc for explanation",
        "This was the deliberately non-confirmatory case.",
    ]
    normalized_main = " ".join(main_text.split())
    missing_main = [marker for marker in required_main if marker not in normalized_main]
    if missing_main:
        failures.append(
            "main manuscript does not preserve the declared evidence narrative: "
            + ", ".join(missing_main)
        )

    missing_comparators = [
        key for key in COMPARATOR_CITATION_KEYS if key not in supplement_text
    ]
    if missing_comparators:
        failures.append(
            "supplement comparator positioning is missing source key(s): "
            + ", ".join(missing_comparators)
        )

    required_supplement = [
        "positioning exercise rather than a",
        "representative rather than exhaustive",
        "No independent feature audit of every comparator version was",
        "two show within-TCGA literature concordance",
        "one provides cross-cohort/cross-assay directional corroboration",
        "deliberately non-confirmatory",
        "Only the ACC case uses a cohort and assay",
    ]
    missing_supplement = [
        marker for marker in required_supplement if marker not in supplement_text
    ]
    if missing_supplement:
        failures.append(
            "supplement does not state comparator/case-study boundaries: "
            + ", ".join(missing_supplement)
        )

    if not missing_main and not missing_comparators and not missing_supplement:
        notes.append(
            "evidence narrative keeps technical validation separate, three "
            "literature-aligned cases with only one orthogonal corroboration, "
            "one non-confirmatory case and 20 source-based comparator positions"
        )


def check_abstract(text: str, failures: list[str], notes: list[str]) -> None:
    try:
        abstract = extract_environment(text, "abstract")
    except ValueError as exc:
        failures.append(str(exc))
        return

    positions: list[int] = []
    for heading in ABSTRACT_HEADINGS:
        marker = rf"\textbf{{{heading}:}}"
        count = abstract.count(marker)
        if count != 1:
            failures.append(f"abstract must contain exactly one `{heading}:` heading; found {count}")
        positions.append(abstract.find(marker))
    if any(position < 0 for position in positions):
        return
    if positions != sorted(positions):
        failures.append("structured abstract headings are not in journal order")

    summary_start = positions[0] + len(r"\textbf{Summary:}")
    summary = abstract[summary_start:positions[1]]
    sentence_count = len(re.findall(r"[.!?](?=\s|$)", latex_to_plain(summary)))
    if sentence_count != 2:
        failures.append(f"Summary must contain 1-2 sentences; found {sentence_count}")
    else:
        notes.append("structured abstract has four required headings and a two-sentence Summary")


def check_main_floats(text: str, failures: list[str], notes: list[str]) -> None:
    table_count = len(re.findall(r"\\begin\{table\*?\}", text))
    table_inputs = re.findall(r"\\input\{tables/[^}]+\}", text)
    figures = re.findall(
        r"\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}",
        text,
        flags=re.DOTALL,
    )
    if table_count or table_inputs:
        failures.append(
            "main manuscript must keep empirical tables in the supplement; "
            f"found {table_count} inline table(s) and {len(table_inputs)} table input(s)"
        )
    if len(figures) != 1:
        failures.append(
            "main manuscript must contain exactly one integrated vector figure; "
            f"found {len(figures)}"
        )
    else:
        required_figure_markers = [
            MAIN_FIGURE_INPUT,
            r"\caption{",
            r"\label{fig:trace-workflow}",
            r"\textbf{Alt text:}",
        ]
        missing = [
            marker for marker in required_figure_markers if marker not in figures[0]
        ]
        if missing:
            failures.append(
                "main figure is missing required source, caption, label or alt text: "
                + ", ".join(missing)
            )

    try:
        figure_source = MAIN_FIGURE_SOURCE.read_text(encoding="utf-8")
    except OSError as exc:
        failures.append(f"could not read main vector figure: {exc}")
        return
    required_source_markers = [
        r"\begin{tikzpicture}",
        "{INPUTS}",
        "{COHORT}",
        "{ANALYSIS BRANCH}",
        "{CONTRACT}",
        "{RUN RECORD}",
    ]
    missing = [
        marker for marker in required_source_markers if marker not in figure_source
    ]
    if missing:
        failures.append(
            "main vector figure source is incomplete; missing " + ", ".join(missing)
        )
    elif len(figures) == 1 and not table_count and not table_inputs:
        notes.append(
            "main manuscript contains one integrated vector figure, inline alt "
            "text and no empirical tables"
        )


def check_paper_example_coverage(
    text: str,
    failures: list[str],
    notes: list[str],
) -> None:
    missing = [
        identifier
        for identifier in PAPER_EXAMPLE_IDENTIFIERS
        if rf"\texttt{{{identifier}}}" not in text
        and rf"\path{{{identifier}}}" not in text
    ]
    if missing:
        failures.append(
            "supplement does not explicitly map Paper Examples case(s): "
            + ", ".join(missing)
        )
        return
    notes.append(
        f"all {len(PAPER_EXAMPLE_IDENTIFIERS)} frozen Paper Examples cases are explicitly mapped"
    )


def check_supplement(
    text: str,
    failures: list[str],
    notes: list[str],
    manuscript_dir: Path = MANUSCRIPT_DIR,
) -> None:
    bibliography_position = text.find(r"\bibliographystyle")
    clearpage_position = text.rfind(r"\clearpage", 0, bibliography_position)
    if bibliography_position < 0 or clearpage_position < 0:
        failures.append("supplement must flush all floats with \\clearpage before the bibliography")

    table_count = len(re.findall(r"\\begin\{table\*?\}", text))
    table_inputs = re.findall(r"\\input\{(tables/[^}]+)\}", text)
    for table_input in table_inputs:
        table_path = manuscript_dir / table_input
        if table_path.suffix != ".tex":
            table_path = table_path.with_suffix(".tex")
        try:
            table_text = table_path.read_text(encoding="utf-8")
        except OSError as exc:
            failures.append(f"could not read supplementary table input {table_path}: {exc}")
            continue
        input_count = len(re.findall(r"\\begin\{table\*?\}", table_text))
        if input_count == 0:
            failures.append(f"supplementary table input has no table environment: {table_path}")
        table_count += input_count

    if table_count != EXPECTED_SUPPLEMENT_TABLES:
        failures.append(
            f"supplement must contain {EXPECTED_SUPPLEMENT_TABLES} cited tables; found {table_count}"
        )

    figures = re.findall(
        r"\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}",
        text,
        flags=re.DOTALL,
    )
    if len(figures) != EXPECTED_SUPPLEMENT_FIGURES:
        failures.append(
            f"supplement must contain {EXPECTED_SUPPLEMENT_FIGURES} interface figures; "
            f"found {len(figures)}"
        )
    missing_alt = [
        index
        for index, figure in enumerate(figures, start=1)
        if r"\textbf{Alt text:}" not in figure
    ]
    if missing_alt:
        failures.append(f"supplementary figures missing inline alt text: {missing_alt}")
    elif not figures:
        notes.append(
            f"supplement contains {table_count} tables, no figures, and flushes all "
            "floats before references"
        )
    else:
        figure_label = "figure" if len(figures) == 1 else "figures"
        notes.append(
            f"supplement contains {table_count} tables and {len(figures)} {figure_label} with "
            "inline alt text, and flushes all floats before references"
        )


def check_supplement_order_and_cutpoints(
    main_text: str,
    supplement_text: str,
    failures: list[str],
    notes: list[str],
) -> None:
    positions = [supplement_text.find(marker) for marker in SUPPLEMENT_TABLE_SEQUENCE]
    if any(position < 0 for position in positions):
        missing = [
            marker
            for marker, position in zip(SUPPLEMENT_TABLE_SEQUENCE, positions)
            if position < 0
        ]
        failures.append(
            "supplement is missing ordered table marker(s): " + ", ".join(missing)
        )
    elif positions != sorted(positions):
        failures.append(
            "supplementary tables are not ordered S1--S8 by first main-text citation"
        )

    first_citations: list[int] = []
    for match in re.finditer(
        r"Supplementary\s+Table(?:s)?\s+S([1-8])(?:--S?([1-8]))?",
        main_text,
    ):
        start = int(match.group(1))
        end = int(match.group(2) or start)
        for number in range(start, end + 1):
            if number not in first_citations:
                first_citations.append(number)
    if first_citations != list(range(1, EXPECTED_SUPPLEMENT_TABLES + 1)):
        failures.append(
            "main-text first citations must follow S1--S8; found "
            + ", ".join(f"S{number}" for number in first_citations)
        )

    normalized_supplement = " ".join(supplement_text.split()).lower()
    stale_phrases = [
        "five grouped methods",
        "Grouped BH used",
        "60th-percentile",
    ]
    found_stale = [
        phrase for phrase in stale_phrases if phrase.lower() in normalized_supplement
    ]
    if found_stale:
        failures.append(
            "supplement retains stale grouped-calibration wording: "
            + ", ".join(found_stale)
        )
    required_cutpoint_phrases = [
        "four grouped",
        "Within-replicate Holm",
        "three-group",
        "custom percentile",
    ]
    missing_cutpoint = [
        phrase
        for phrase in required_cutpoint_phrases
        if phrase.lower() not in normalized_supplement
    ]
    if missing_cutpoint:
        failures.append(
            "supplement does not fully state the four-cutpoint rationale: "
            + ", ".join(missing_cutpoint)
        )
    if not failures:
        notes.append(
            "supplementary tables are first-cited sequentially and calibration "
            "uses the declared four-rule Holm family"
        )


def check_screenshot_resolution(failures: list[str], notes: list[str]) -> None:
    dimensions: list[str] = []
    for path in SCREENSHOTS:
        try:
            width, height = png_dimensions(path)
        except (OSError, ValueError) as exc:
            failures.append(str(exc))
            continue
        dimensions.append(f"{path.name}={width}x{height}")
        if width < MIN_FULL_WIDTH_PIXELS:
            failures.append(
                f"{path.relative_to(ROOT)} is {width}px wide; full-width 350-dpi output "
                f"needs at least {MIN_FULL_WIDTH_PIXELS}px"
            )
    if len(dimensions) == len(SCREENSHOTS):
        notes.append("supplement screenshot pixels: " + ", ".join(dimensions))


def check_oup_source(path: Path, failures: list[str], notes: list[str]) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        failures.append(f"could not read generated OUP source {path.relative_to(ROOT)}: {exc}")
        return

    required = {
        r"\documentclass[webpdf,modern,large,namedate]{oup-authoring-template}":
            "OUP preview must use the Bioinformatics modern/large author-date class mapping",
        r"\appnotes{Applications Note}":
            "OUP preview must carry the `Applications Note` article label",
        r"\bibliographystyle{abbrvnat}":
            "OUP preview must use the Bioinformatics author-date bibliography style `abbrvnat`",
    }
    for marker, message in required.items():
        if marker not in text:
            failures.append(message)
    if r"\application" in text:
        failures.append("OUP preview uses obsolete `\\application`; use `\\appnotes{...}`")
    generated_authors = re.findall(r"\\author\[[^\]]+\]\{([^{}]+)\}", text)
    missing_authors = [
        author for author in EXPECTED_AUTHORS if author not in generated_authors
    ]
    if len(generated_authors) != len(EXPECTED_AUTHORS) or missing_authors:
        failures.append(
            "OUP preview author extraction is incomplete: expected "
            f"{len(EXPECTED_AUTHORS)}, found {len(generated_authors)}"
            + (
                "; missing " + ", ".join(missing_authors)
                if missing_authors
                else ""
            )
        )
    generated_affiliations = len(
        re.findall(r"\\address\[[^\]]+\]\{", text)
    )
    if generated_affiliations != EXPECTED_AFFILIATIONS:
        failures.append(
            "OUP preview affiliation extraction is incomplete: expected "
            f"{EXPECTED_AFFILIATIONS}, found {generated_affiliations}"
        )
    if not any(message in failures for message in required.values()):
        notes.append(
            "OUP source uses the Bioinformatics modern/large, numbered-section, "
            "author-date Applications Note mapping"
        )
    if not missing_authors and generated_affiliations == EXPECTED_AFFILIATIONS:
        notes.append(
            f"OUP source preserves all {len(EXPECTED_AUTHORS)} authors and "
            f"{EXPECTED_AFFILIATIONS} affiliations"
        )


def check_oup_pages(path: Path, failures: list[str], notes: list[str]) -> None:
    if not path.is_file():
        failures.append(f"missing OUP preview PDF: {path.relative_to(ROOT)}")
        return
    try:
        completed = subprocess.run(
            ["pdfinfo", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        failures.append("`pdfinfo` is required to enforce the four-page OUP limit")
        return
    except subprocess.CalledProcessError as exc:
        failures.append(f"could not inspect OUP preview PDF: {exc.stderr.strip()}")
        return
    match = re.search(r"^Pages:\s+(\d+)\s*$", completed.stdout, flags=re.MULTILINE)
    if not match:
        failures.append("could not read page count from OUP preview PDF")
        return
    pages = int(match.group(1))
    if pages > MAX_OUP_PAGES:
        failures.append(f"OUP preview has {pages} pages; Application Notes allow at most {MAX_OUP_PAGES}")
    else:
        notes.append(f"OUP two-column preview is {pages}/{MAX_OUP_PAGES} pages")

    size_match = re.search(
        r"^Page size:\s+([0-9.]+)\s+x\s+([0-9.]+)\s+pts",
        completed.stdout,
        flags=re.MULTILINE,
    )
    if not size_match:
        failures.append("could not read OUP preview page dimensions")
        return
    actual_size = tuple(float(value) for value in size_match.groups())
    if any(
        abs(actual - expected) > OUP_PAGE_SIZE_TOLERANCE
        for actual, expected in zip(actual_size, EXPECTED_OUP_PAGE_SIZE)
    ):
        failures.append(
            "OUP preview page size "
            f"{actual_size[0]:.3f} x {actual_size[1]:.3f} pt does not match "
            "the Bioinformatics modern/large layout"
        )
    else:
        notes.append(
            "OUP page geometry matches the Bioinformatics modern/large layout "
            f"({actual_size[0]:.3f} x {actual_size[1]:.3f} pt)"
        )


def extract_environment(text: str, environment: str) -> str:
    begin = f"\\begin{{{environment}}}"
    end = f"\\end{{{environment}}}"
    start = text.find(begin)
    if start < 0:
        raise ValueError(f"missing {begin}")
    start += len(begin)
    finish = text.find(end, start)
    if finish < 0:
        raise ValueError(f"missing {end}")
    return text[start:finish]


def latex_to_plain(text: str) -> str:
    plain = re.sub(r"%.*", " ", text)
    plain = re.sub(r"\\(?:citep|citet|url|texttt|textbf)\{([^{}]*)\}", r"\1", plain)
    plain = re.sub(r"\\[A-Za-z@]+", " ", plain)
    plain = plain.replace("{", " ").replace("}", " ").replace("~", " ")
    return " ".join(plain.split())


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path.relative_to(ROOT)} is not a valid PNG")
    return struct.unpack(">II", data[16:24])


if __name__ == "__main__":
    sys.exit(main())
