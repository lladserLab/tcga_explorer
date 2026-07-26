from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "build_oup_preview.py"
SPEC = importlib.util.spec_from_file_location("build_oup_preview", MODULE_PATH)
assert SPEC is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
assert SPEC.loader is not None
SPEC.loader.exec_module(builder)


def test_render_oup_source_reuses_main_manuscript_content() -> None:
    source = (
        "\\documentclass[12pt]{article}\n"
        "\\title{TCGA-TRACE test title}\n"
        "\\author{\n"
        "  Ada Lovelace$^{1}$ and Grace Hopper$^{2}$\\\\\n"
        "  $^{1}$Institute A\\\\\n"
        "  $^{2}$Institute B\\\\\n"
        "  Correspondence: ada@example.org\n"
        "}\n"
        "\\begin{document}\n"
        "\\begin{abstract}\n"
        "\\textbf{Summary:} Two sentences. This is the second.\n"
        "\\end{abstract}\n"
        "\\section*{Introduction}\n"
        "Shared scientific body.\n"
        "\\bibliographystyle{plainnat}\n"
        "\\bibliography{references}\n"
        "\\end{document}\n"
    )

    rendered = builder.render_oup_source(source)

    assert "\\documentclass[webpdf,modern,large,namedate]" in rendered
    assert "\\appnotes{Applications Note}" in rendered
    assert "\\application" not in rendered
    assert "\\title{TCGA-TRACE test title}" in rendered
    assert "\\author[1]{Ada Lovelace}" in rendered
    assert "\\author[2]{Grace Hopper}" in rendered
    assert "\\address[1]{Institute A}" in rendered
    assert "\\address[2]{Institute B}" in rendered
    assert "\\abstract{%" in rendered
    assert "Shared scientific body." in rendered
    assert "\\bibliographystyle{abbrvnat}" in rendered


def test_parse_article_author_block_requires_three_lines() -> None:
    try:
        builder.parse_article_author_block("Ada Lovelace")
    except builder.SourceError as exc:
        assert "names, affiliations and correspondence" in str(exc)
    else:
        raise AssertionError("incomplete author block should fail")
