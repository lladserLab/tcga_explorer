from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "check_editorial_compliance.py"
SPEC = importlib.util.spec_from_file_location("check_editorial_compliance", MODULE_PATH)
assert SPEC is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
assert SPEC.loader is not None
SPEC.loader.exec_module(checker)


def test_structured_abstract_accepts_two_sentence_summary() -> None:
    text = (
        "\\begin{abstract}\n"
        "\\textbf{Summary:} First sentence. Second sentence.\n"
        "\\textbf{Availability and Implementation:} Available online.\n"
        "\\textbf{Contact:} author@example.org.\n"
        "\\textbf{Supplementary information:} Available online.\n"
        "\\end{abstract}\n"
    )
    failures: list[str] = []
    notes: list[str] = []

    checker.check_abstract(text, failures, notes)

    assert failures == []
    assert any("two-sentence Summary" in note for note in notes)


def test_title_and_structure_accept_writing_blueprint() -> None:
    text = (
        "\\title{TCGA-TRACE: auditable survival analysis for TCGA transcriptomic biomarkers}\n"
        "\\section{Introduction}\n"
        "\\section{Methods}\n"
        "\\subsection{Data and cohort construction}\n"
        "\\subsection{Survival analyses}\n"
        "\\subsection{Web server and run record}\n"
        "\\section{Case Studies and Evaluation}\n"
        "\\subsection{Case 1: CDC20 in Hepatocellular Cancer}\n"
        "\\subsection{Case 2: BUB1B--PINK1 in ACC}\n"
        "\\subsection{Case 3: BIRC5 Across TCGA Cohorts}\n"
        "\\subsection{Case 4: BAP1/PRAME in Uveal Melanoma}\n"
        "\\section{Future Plans}\n"
    )
    failures: list[str] = []
    notes: list[str] = []

    checker.check_title_and_structure(text, failures, notes)

    assert failures == []
    assert any("74/75 characters" in note for note in notes)
    assert any("four concise declarative" in note for note in notes)


def test_title_and_structure_rejects_question_case_heading() -> None:
    text = (
        "\\title{TCGA-TRACE: auditable survival analysis for TCGA transcriptomic biomarkers}\n"
        "\\section{Introduction}\n"
        "\\section{Methods}\n"
        "\\subsection{Data and cohort construction}\n"
        "\\subsection{Survival analyses}\n"
        "\\subsection{Web server and run record}\n"
        "\\section{Case Studies and Evaluation}\n"
        "\\subsection{Case 1: Can Records Be Rebuilt?}\n"
        "\\subsection{Case 2: BUB1B--PINK1 in ACC}\n"
        "\\subsection{Case 3: BIRC5 Across TCGA Cohorts}\n"
        "\\subsection{Case 4: BAP1/PRAME in Uveal Melanoma}\n"
        "\\section{Future Plans}\n"
    )
    failures: list[str] = []

    checker.check_title_and_structure(text, failures, [])

    assert any("declarative rather than questions" in failure for failure in failures)


def test_evidence_narrative_accepts_declared_case_balance() -> None:
    main_text = "\n".join(
        [
            r"\subsection*{Technical validation}",
            "The panel retains supported, unsupported, nonlinear, sparse-event and PH-discordant results.",
            "The cases were chosen post hoc for explanation.",
            "This was the deliberately non-confirmatory case.",
        ]
    )
    supplement_text = "\n".join(
        [
            "This is a positioning exercise rather than a head-to-head benchmark.",
            "The resources are representative rather than exhaustive.",
            "No independent feature audit of every comparator version was performed.",
            "two show within-TCGA literature concordance",
            "one provides cross-cohort/cross-assay directional corroboration",
            "one is deliberately non-confirmatory",
            "Only the ACC case uses a cohort and assay",
            *checker.COMPARATOR_CITATION_KEYS,
        ]
    )
    failures: list[str] = []
    notes: list[str] = []

    checker.check_evidence_narrative(main_text, supplement_text, failures, notes)

    assert failures == []
    assert any("only one orthogonal corroboration" in note for note in notes)


def test_evidence_narrative_rejects_missing_comparator_and_case_boundary() -> None:
    failures: list[str] = []

    checker.check_evidence_narrative(
        r"\subsection*{Technical validation}",
        "positioning exercise rather than a benchmark",
        failures,
        [],
    )

    assert any("declared evidence narrative" in failure for failure in failures)
    assert any("missing source key" in failure for failure in failures)
    assert any("comparator/case-study boundaries" in failure for failure in failures)


def test_main_floats_accepts_one_vector_figure_without_tables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    figure_source = tmp_path / "graphical_abstract.tex"
    figure_source.write_text(
        "\\begin{tikzpicture}{INPUTS}{COHORT}{ANALYSIS BRANCH}{CONTRACT}{RUN RECORD}"
        "\\end{tikzpicture}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "MAIN_FIGURE_SOURCE", figure_source)
    text = (
        "\\begin{figure*}\n"
        f"{checker.MAIN_FIGURE_INPUT}\n"
        "\\caption{Workflow. \\textbf{Alt text:} Five-stage flow diagram.}\n"
        "\\label{fig:trace-workflow}\n"
        "\\end{figure*}\n"
    )
    failures: list[str] = []
    notes: list[str] = []

    checker.check_main_floats(text, failures, notes)

    assert failures == []
    assert any("one integrated vector figure" in note for note in notes)


def test_main_floats_rejects_empirical_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    figure_source = tmp_path / "graphical_abstract.tex"
    figure_source.write_text(
        "\\begin{tikzpicture}{INPUTS}{COHORT}{ANALYSIS BRANCH}{CONTRACT}{RUN RECORD}"
        "\\end{tikzpicture}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "MAIN_FIGURE_SOURCE", figure_source)
    text = (
        "\\begin{figure*}\n"
        f"{checker.MAIN_FIGURE_INPUT}\n"
        "\\caption{Workflow. \\textbf{Alt text:} Five-stage flow diagram.}\n"
        "\\label{fig:trace-workflow}\n"
        "\\end{figure*}\n"
        "\\input{tables/main_evidence_matrix}\n"
    )
    failures: list[str] = []

    checker.check_main_floats(text, failures, [])

    assert any("keep empirical tables in the supplement" in failure for failure in failures)


def test_png_dimensions_reads_ihdr_dimensions(tmp_path: Path) -> None:
    path = tmp_path / "figure.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", 3000, 2000))

    assert checker.png_dimensions(path) == (3000, 2000)


def test_paper_example_coverage_accepts_all_frozen_cases() -> None:
    text = "\n".join(
        f"\\path{{{identifier}}}"
        for identifier in checker.PAPER_EXAMPLE_IDENTIFIERS
    )
    failures: list[str] = []
    notes: list[str] = []

    checker.check_paper_example_coverage(text, failures, notes)

    assert failures == []
    assert any("all 17 frozen Paper Examples" in note for note in notes)


def test_oup_source_accepts_bioinformatics_journal_mapping(tmp_path: Path) -> None:
    path = tmp_path / "oup_preview.tex"
    path.write_text(
        "\\documentclass[webpdf,modern,large,namedate]{oup-authoring-template}\n"
        "\\appnotes{Applications Note}\n"
        "\\author[1,2,3]{Sergio Hernández-Galaz}\n"
        "\\author[1,2]{Andrés Hernández-Oliveras}\n"
        "\\author[1,3,4]{Ignacio Pezoa-Soto}\n"
        "\\author[1]{Javiera Reyes-Alvarez}\n"
        "\\author[1]{Vincenzo Benedetti}\n"
        "\\author[1,4]{Alberto J. M. Martin}\n"
        "\\author[1,3]{Alvaro Lladser}\n"
        "\\address[1]{Institute A}\n"
        "\\address[2]{Institute B}\n"
        "\\address[3]{Institute C}\n"
        "\\address[4]{Institute D}\n"
        "\\bibliographystyle{abbrvnat}\n",
        encoding="utf-8",
    )
    failures: list[str] = []
    notes: list[str] = []

    checker.check_oup_source(path, failures, notes)

    assert failures == []
    assert any("Bioinformatics modern/large" in note for note in notes)
    assert any("all 7 authors and 4 affiliations" in note for note in notes)


def test_supplement_counts_direct_and_input_tables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / "included.tex").write_text(
        "\\begin{table}\\caption{Included}\\end{table}\n",
        encoding="utf-8",
    )
    text = (
        "\\begin{table}\\caption{Direct}\\end{table}\n"
        "\\input{tables/included}\n"
        "\\begin{figure}\\caption{One}\\textbf{Alt text:} Description.\\end{figure}\n"
        "\\clearpage\n"
        "\\bibliographystyle{plainnat}\n"
    )
    monkeypatch.setattr(checker, "EXPECTED_SUPPLEMENT_TABLES", 2)
    monkeypatch.setattr(checker, "EXPECTED_SUPPLEMENT_FIGURES", 1)
    failures: list[str] = []
    notes: list[str] = []

    checker.check_supplement(text, failures, notes, manuscript_dir=tmp_path)

    assert failures == []
    assert any("2 tables and 1 figure" in note for note in notes)


def test_supplement_order_accepts_sequential_first_citations() -> None:
    main_text = "\n".join(
        [
            "Supplementary Table S1.",
            "Supplementary Table S2.",
            "Supplementary Table S3.",
            "Supplementary Table S4.",
            "Supplementary Tables S5--S6.",
            "Supplementary Table S7.",
            "Supplementary Table S8.",
        ]
    )
    supplement_text = "\n".join(
        [
            checker.SUPPLEMENT_TABLE_SEQUENCE[0],
            checker.SUPPLEMENT_TABLE_SEQUENCE[1],
            checker.SUPPLEMENT_TABLE_SEQUENCE[2],
            checker.SUPPLEMENT_TABLE_SEQUENCE[3],
            checker.SUPPLEMENT_TABLE_SEQUENCE[4],
            checker.SUPPLEMENT_TABLE_SEQUENCE[5],
            checker.SUPPLEMENT_TABLE_SEQUENCE[6],
            checker.SUPPLEMENT_TABLE_SEQUENCE[7],
            "four grouped methods",
            "Within-replicate Holm",
            "tertiles are a three-group comparison",
            "custom percentile is user-defined",
        ]
    )
    failures: list[str] = []
    notes: list[str] = []

    checker.check_supplement_order_and_cutpoints(
        main_text,
        supplement_text,
        failures,
        notes,
    )

    assert failures == []
    assert any("first-cited sequentially" in note for note in notes)


def test_supplement_order_rejects_out_of_order_and_stale_bh() -> None:
    main_text = "\n".join(
        [
            "Supplementary Table S3.",
            "Supplementary Table S1.",
            "Supplementary Table S2.",
        ]
    )
    supplement_text = "\n".join(
        [
            checker.SUPPLEMENT_TABLE_SEQUENCE[2],
            checker.SUPPLEMENT_TABLE_SEQUENCE[0],
            checker.SUPPLEMENT_TABLE_SEQUENCE[1],
            *checker.SUPPLEMENT_TABLE_SEQUENCE[3:],
            "five grouped methods. Grouped BH used the Lau94 p-value.",
        ]
    )
    failures: list[str] = []

    checker.check_supplement_order_and_cutpoints(
        main_text,
        supplement_text,
        failures,
        [],
    )

    assert any("not ordered" in failure for failure in failures)
    assert any("first citations" in failure for failure in failures)
    assert any("stale grouped-calibration" in failure for failure in failures)
