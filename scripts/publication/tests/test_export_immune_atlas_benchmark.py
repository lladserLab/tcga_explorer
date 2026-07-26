from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "export_immune_atlas_benchmark.py"
)
SPEC = importlib.util.spec_from_file_location(
    "export_immune_atlas_benchmark",
    MODULE_PATH,
)
assert SPEC is not None
exporter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = exporter
assert SPEC.loader is not None
SPEC.loader.exec_module(exporter)


def test_latex_table_keeps_model_families_separate() -> None:
    rows = [
        {
            "model": "primary",
            "model_label": "Primary",
            "completed_gene_cohort_models": "100",
            "global_fdr_hits": "20",
            "meta_fdr_gene_hits": "5",
            "global_fdr_ph_flagged": "2",
            "recurrent_harmful_genes_ge5": "3",
            "recurrent_protective_genes_ge5": "1",
        },
        {
            "model": "availability_selected",
            "model_label": "Selected",
            "completed_gene_cohort_models": "80",
            "global_fdr_hits": "8",
            "meta_fdr_gene_hits": "",
            "global_fdr_ph_flagged": "1",
            "recurrent_harmful_genes_ge5": "0",
            "recurrent_protective_genes_ge5": "0",
        },
    ]

    output = exporter.render_latex_table(rows)

    assert "Primary expression & 100 & 20 & 5 & 2 & 3 / 1" in output
    assert "Availability-selected & 80 & 8 & -- & 1 & 0 / 0" in output
    assert "availability-selected row has no mixed-family meta-analysis" in output
