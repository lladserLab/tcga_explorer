#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAIN = Path("manuscript/bioinformatics_app_note/main.tex")
DEFAULT_OUTPUT = Path("manuscript/bioinformatics_app_note/build/oup_preview.tex")
OUP_CLASS_OPTIONS = "webpdf,modern,large,namedate"
OUP_ARTICLE_LABEL = "Applications Note"
OUP_BIBLIOGRAPHY_STYLE = "abbrvnat"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source_path = resolve_repo_path(args.main)
    output_path = resolve_repo_path(args.output)
    try:
        rendered = render_oup_source(source_path.read_text(encoding="utf-8"))
    except (OSError, SourceError) as exc:
        print(f"OUP preview generation failed: {exc}", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    print(f"Wrote {output_path.relative_to(ROOT)}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate an OUP two-column preview from the format-free "
            "Bioinformatics manuscript without duplicating its scientific text."
        )
    )
    parser.add_argument(
        "--main",
        type=Path,
        default=DEFAULT_MAIN,
        help=f"Main manuscript source. Default: {DEFAULT_MAIN}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Generated OUP source. Default: {DEFAULT_OUTPUT}",
    )
    return parser.parse_args(argv)


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def render_oup_source(source: str) -> str:
    title = extract_braced_command(source, "title")
    author_block = extract_braced_command(source, "author")
    abstract, abstract_end = extract_environment(source, "abstract")
    bibliography_start = source.find(r"\bibliographystyle", abstract_end)
    if bibliography_start < 0:
        raise SourceError("main manuscript has no bibliography style marker")

    body = source[abstract_end:bibliography_start].strip()
    authors, affiliations, correspondence = parse_article_author_block(
        author_block
    )
    author_commands = "\n".join(
        f"\\author[{references}]{{{name}}}"
        for name, references in authors
    )
    affiliation_commands = "\n".join(
        f"\\address[{reference}]{{{affiliation}}}"
        for reference, affiliation in affiliations
    )
    return (
        "% Bioinformatics: modern/large design and author-date citations.\n"
        "% OUP lists numsec for the journal; class 1.5 numbers sections by default.\n"
        f"\\documentclass[{OUP_CLASS_OPTIONS}]{{oup-authoring-template}}\n\n"
        "\\usepackage{hyperref}\n"
        "\\usepackage{tikz}\n"
        "\\usepackage{booktabs}\n"
        "\\usetikzlibrary{arrows.meta, calc, fit, positioning}\n"
        "\\hypersetup{colorlinks=true,linkcolor=black,citecolor=black,urlcolor=black}\n"
        "\\emergencystretch=2em\n\n"
        "\\providecommand{\\authormark}[1]{\\markboth{#1}{#1}}\n"
        "\\providecommand{\\societylogo}{}\n"
        "\\journaltitle{Bioinformatics}\n"
        "\\pubyear{2026}\n"
        "\\copyrightyear{2026}\n"
        f"\\appnotes{{{OUP_ARTICLE_LABEL}}}\n"
        f"\\title{{{title}}}\n"
        f"{author_commands}\n"
        f"{affiliation_commands}\n"
        f"\\corresp{{{correspondence}}}\n"
        "\\abstract{%\n"
        f"{abstract.strip()}\n"
        "}\n"
        "\\keywords{cancer genomics, reproducibility, survival analysis, TCGA}\n\n"
        "\\begin{document}\n"
        "\\maketitle\n\n"
        f"{body}\n\n"
        f"\\bibliographystyle{{{OUP_BIBLIOGRAPHY_STYLE}}}\n"
        "\\bibliography{references}\n\n"
        "\\end{document}\n"
    )


def extract_braced_command(source: str, command: str) -> str:
    match = re.search(rf"\\{re.escape(command)}\s*\{{", source)
    if not match:
        raise SourceError(f"missing \\{command}{{...}} command")
    open_brace = match.end() - 1
    close_brace = find_matching_brace(source, open_brace)
    return source[open_brace + 1 : close_brace].strip()


def extract_environment(source: str, environment: str) -> tuple[str, int]:
    begin = f"\\begin{{{environment}}}"
    end = f"\\end{{{environment}}}"
    begin_index = source.find(begin)
    if begin_index < 0:
        raise SourceError(f"missing {begin}")
    content_start = begin_index + len(begin)
    end_index = source.find(end, content_start)
    if end_index < 0:
        raise SourceError(f"missing {end}")
    return source[content_start:end_index], end_index + len(end)


def parse_article_author_block(
    author_block: str,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], str]:
    parts = [part.strip() for part in re.split(r"\\\\\s*(?:\n|$)", author_block) if part.strip()]
    if len(parts) < 3:
        raise SourceError(
            "the article author block must contain names, affiliations and correspondence "
            "on separate LaTeX lines"
        )
    correspondence_indexes = [
        index
        for index, part in enumerate(parts)
        if part.lower().startswith("correspondence:")
    ]
    if len(correspondence_indexes) != 1:
        raise SourceError(
            "the article author block must contain exactly one Correspondence line"
        )
    correspondence_index = correspondence_indexes[0]
    affiliation_indexes = [
        index
        for index, part in enumerate(parts[:correspondence_index])
        if re.match(r"^\$\^\{\d+\}\$", part)
    ]
    if not affiliation_indexes:
        raise SourceError(
            "the article author block must contain numbered affiliations"
        )
    first_affiliation = affiliation_indexes[0]
    names_text = " ".join(parts[:first_affiliation])
    affiliation_text = " ".join(
        parts[first_affiliation:correspondence_index]
    )
    authors = parse_numbered_authors(names_text)
    affiliations = parse_numbered_affiliations(affiliation_text)
    if not authors or not affiliations:
        raise SourceError(
            "the article author block must contain numbered authors and affiliations"
        )
    return authors, affiliations, parts[correspondence_index]


def parse_numbered_authors(value: str) -> list[tuple[str, str]]:
    normalized = " ".join(value.split())
    pattern = re.compile(
        r"(?:^|,\s*(?:and\s+)?|\s+and\s+)"
        r"(?P<name>[^,]+?)\$\^\{(?P<references>[0-9,\s]+)\}\$"
    )
    authors = []
    for match in pattern.finditer(normalized):
        name = match.group("name").strip()
        references = re.sub(r"\s+", "", match.group("references"))
        if name and references:
            authors.append((name, references))
    return authors


def parse_numbered_affiliations(value: str) -> list[tuple[str, str]]:
    markers = list(re.finditer(r"\$\^\{(?P<reference>\d+)\}\$", value))
    affiliations = []
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(value)
        text = value[marker.end():end].strip(" ;\n")
        if text:
            affiliations.append((marker.group("reference"), text))
    return affiliations


def find_matching_brace(source: str, open_brace: int) -> int:
    depth = 0
    for index in range(open_brace, len(source)):
        char = source[index]
        if char not in "{}" or is_escaped(source, index):
            continue
        depth += 1 if char == "{" else -1
        if depth == 0:
            return index
    raise SourceError("unterminated LaTeX command block")


def is_escaped(source: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and source[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


class SourceError(Exception):
    pass


if __name__ == "__main__":
    sys.exit(main())
