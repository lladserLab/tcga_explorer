from dataclasses import dataclass
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import zipfile

import pytest
from fastapi import Request

from app import main as main_module
from app.gsea import (
    ExpressionMatrix,
    MatrixGene,
    _benjamini_hochberg,
    _gsea_dotplot_svg,
    combine_camera_inference_with_preranked_effects,
    clinical_group_assignments,
    gsea_summary,
    load_gene_set_catalog,
    prepare_camera_expression_matrix,
    public_gene_set_catalog,
    rank_expression_matrix,
    read_gmt,
    run_preranked_effects,
    run_camera_gene_set_test,
    run_preranked_gsea,
    survival_group_assignments,
)
from app.models import AnalysisJob, Cohort
from app.repository.storage import write_float32le_matrix
from app.schemas import (
    GseaAnalysisOut,
    GseaAnalysisRequest,
    GseaGroupingDefinition,
    SignatureGene,
    SignatureSpec,
)


def test_gsea_response_model_reads_v1_without_reinterpreting_its_inference() -> None:
    archived = GseaAnalysisOut(
        schema_version="tcga-trace-preranked-gsea-result-v1",
        gsea_id="gsea-v1-fixture",
        status="completed",
        pipeline_version="preranked-gene-set-permutation-bh-contract-v1.6",
        cohort="TCGA-KIRC",
        expression_scale="log2_tpm",
        expression_scale_label="log2(TPM + 1)",
        grouping={},
        gene_set_collection={},
        ranking={},
        summary={},
    )

    assert archived.inference is None
    assert archived.schema_version == "tcga-trace-preranked-gsea-result-v1"

    with pytest.raises(ValueError, match="requires CAMERA inference metadata"):
        GseaAnalysisOut(
            gsea_id="gsea-invalid-v2",
            status="completed",
            pipeline_version="camera-v2",
            cohort="TCGA-KIRC",
            expression_scale="log2_tpm",
            expression_scale_label="log2(TPM + 1)",
            grouping={},
            gene_set_collection={},
            ranking={},
            summary={},
        )


@dataclass
class MockSample:
    patient_id: str
    barcode: str
    sample_type: str = "Primary Tumor"
    stage: str | None = None
    grade: str | None = None
    gender: str | None = None
    race: str | None = None
    age_at_index: float | None = None
    cohort: str = "TCGA-TEST"


def test_gmt_catalog_checks_manifest_and_parser_normalizes_genes(
    tmp_path: Path,
) -> None:
    gmt_path = tmp_path / "mini.gmt"
    gmt_path.write_text(
        "# deterministic fixture\n"
        "PATH_ALPHA\tAlpha pathway\ttp53\tEGFR\tTP53\n"
        "PATH_BETA\tBeta pathway\tmyc\tCDK2\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(gmt_path.read_bytes()).hexdigest()
    (tmp_path / "collections.json").write_text(
        json.dumps(
            {
                "collections": [
                    {
                        "id": "Mini",
                        "label": "Minimal collection",
                        "version": "fixture-v1",
                        "species": "Homo sapiens",
                        "identifier_type": "HGNC symbol",
                        "source": "unit test",
                        "license": "CC0-1.0",
                        "file": "mini.gmt",
                        "sha256": digest,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    catalog = load_gene_set_catalog(tmp_path)
    assert catalog[0]["id"] == "mini"
    assert catalog[0]["available"] is True
    assert catalog[0]["gene_set_count"] == 2
    assert catalog[0]["sha256"] == digest
    assert "file" not in public_gene_set_catalog(tmp_path)[0]

    pathways = read_gmt(gmt_path)
    assert pathways == [
        {
            "name": "PATH_ALPHA",
            "description": "Alpha pathway",
            "genes": ["TP53", "EGFR"],
        },
        {
            "name": "PATH_BETA",
            "description": "Beta pathway",
            "genes": ["MYC", "CDK2"],
        },
    ]

    gmt_path.write_text(
        gmt_path.read_text(encoding="utf-8") + "PATH_NEW\tNew\tSTAT1\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="SHA-256"):
        load_gene_set_catalog(tmp_path)


def test_clinical_grouping_supports_explicit_categories_and_age_median() -> None:
    samples = [
        MockSample("P1", "S1", stage="Stage I", age_at_index=30),
        MockSample("P2", "S2", stage="stage ii", age_at_index=40),
        MockSample("P3", "S3", stage="Stage III", age_at_index=None),
        MockSample("P4", "S4", stage="STAGE III", age_at_index=60),
        MockSample("P5", "S5", stage="Unknown", age_at_index=70),
    ]
    stage_grouping = GseaGroupingDefinition(
        source="clinical",
        clinical_variable="stage",
        group_a_label="Early",
        group_b_label="Advanced",
        group_a_values=["Stage I", "Stage II"],
        group_b_values=["Stage III"],
    )

    stage_assignments, stage_details = clinical_group_assignments(
        samples,
        stage_grouping,
    )

    assert stage_assignments == {
        "S1": "a",
        "S2": "a",
        "S3": "b",
        "S4": "b",
    }
    assert stage_details["contrast"] == "group_b_minus_group_a"
    assert stage_details["group_a_label"] == "Early"
    assert stage_details["group_b_label"] == "Advanced"

    age_grouping = GseaGroupingDefinition(
        source="clinical",
        clinical_variable="age_at_index",
        group_a_label="Younger",
        group_b_label="Older",
        clinical_cutpoint_method="median",
    )
    age_assignments, age_details = clinical_group_assignments(
        samples,
        age_grouping,
    )

    assert age_details["threshold"] == 50.0
    assert age_assignments == {
        "S1": "a",
        "S2": "a",
        "S4": "b",
        "S5": "b",
    }


def test_expression_grouping_rejects_multiple_genes_in_single_mode() -> None:
    with pytest.raises(
        ValueError,
        match="requires exactly one gene",
    ):
        GseaGroupingDefinition(
            source="expression",
            signature=SignatureSpec(
                gene_symbol="TP53,EGFR",
                signature_method="single",
                signature_genes=[
                    SignatureGene(gene_symbol="TP53"),
                    SignatureGene(gene_symbol="EGFR"),
                ],
            ),
        )


def test_float32_matrix_ranking_is_directional_and_filters_bad_rows(
    tmp_path: Path,
) -> None:
    sample_ids = [f"A{index}" for index in range(5)] + [
        f"B{index}" for index in range(5)
    ]
    rows = [
        [0.8, 1.0, 1.1, 0.9, 1.2, 4.8, 5.0, 5.1, 4.9, 5.2],
        [5.2, 5.0, 4.9, 5.1, 4.8, 1.2, 1.0, 0.9, 1.1, 0.8],
        [0, 1, 2, 3, 4, 0, 1, 2, 3, 4],
        [0, 1, 2, 3, 4, 0, 1, 2, 3, 4],
        [2] * 10,
        [math.nan, math.nan, 1, math.nan, 2, 0, 1, 2, 3, 4],
    ]
    matrix_path = tmp_path / "expression.float32le.bin"
    assert write_float32le_matrix(matrix_path, rows) == 60
    matrix = ExpressionMatrix(
        path=matrix_path,
        sample_ids=sample_ids,
        genes=[
            MatrixGene("UP_IN_B", 0),
            MatrixGene("UP_IN_A", 1),
            MatrixGene("TIE_B", 2),
            MatrixGene("TIE_A", 3),
            MatrixGene("CONSTANT", 4),
            MatrixGene("SPARSE", 5),
        ],
        dtype="float32",
        byte_order="little",
        expression_scale="fixture",
        expression_scale_label="Synthetic log expression",
        source_sha256=None,
    )
    assignments = {
        sample_id: ("a" if sample_id.startswith("A") else "b")
        for sample_id in sample_ids
    }

    ranked, metadata = rank_expression_matrix(
        matrix,
        assignments,
        ranking_metric="welch_t",
    )

    assert [row["gene"] for row in ranked] == [
        "UP_IN_B",
        "TIE_A",
        "TIE_B",
        "UP_IN_A",
    ]
    assert ranked[0]["score"] > 0
    assert ranked[-1]["score"] < 0
    assert ranked[0]["difference_b_minus_a"] == pytest.approx(4.0)
    assert ranked[-1]["difference_b_minus_a"] == pytest.approx(-4.0)
    assert metadata["contrast"] == "group_b_minus_group_a"
    assert metadata["adjacent_ties"] == 1
    assert metadata["exclusions"] == {
        "insufficient_finite_values": 1,
        "zero_within_group_variance": 1,
        "nonfinite_statistic": 0,
    }

    ranked_camera, camera_metadata, camera_matrix = (
        prepare_camera_expression_matrix(
            matrix,
            assignments,
            ranking_metric="welch_t",
            camera_matrix_path=tmp_path / "camera.float32le.bin",
        )
    )
    assert [row["gene"] for row in ranked_camera] == [
        "UP_IN_B",
        "TIE_A",
        "TIE_B",
        "UP_IN_A",
    ]
    assert camera_matrix.genes == ["UP_IN_B", "UP_IN_A", "TIE_B", "TIE_A"]
    assert camera_matrix.sample_ids == sample_ids
    assert camera_matrix.groups == ["a"] * 5 + ["b"] * 5
    assert camera_matrix.path.stat().st_size == 4 * 10 * 4
    assert camera_metadata["exclusions"] == {
        "insufficient_finite_values": 0,
        "zero_within_group_variance": 1,
        "nonfinite_statistic": 0,
        "incomplete_selected_samples": 1,
    }


def test_preranked_gsea_has_stable_direction_seed_and_global_bh() -> None:
    ranked = [
        {
            "gene": f"G{index:03d}",
            "score": float(31 - index),
            "rank": index,
        }
        for index in range(1, 61)
    ]
    pathways = [
        {
            "name": "UP_PATHWAY",
            "description": "Top-ranked genes",
            "genes": [f"G{index:03d}" for index in range(1, 9)],
        },
        {
            "name": "DOWN_PATHWAY",
            "description": "Bottom-ranked genes",
            "genes": [f"G{index:03d}" for index in range(53, 61)],
        },
        {
            "name": "CENTER_PATHWAY",
            "description": "Genes near zero",
            "genes": [f"G{index:03d}" for index in range(27, 35)],
        },
    ]

    first, first_details = run_preranked_gsea(
        ranked,
        pathways,
        min_size=5,
        max_size=20,
        permutations=250,
        seed=17291,
    )
    second, second_details = run_preranked_gsea(
        ranked,
        pathways,
        min_size=5,
        max_size=20,
        permutations=250,
        seed=17291,
    )
    reordered, reordered_details = run_preranked_gsea(
        ranked,
        list(reversed(pathways)),
        min_size=5,
        max_size=20,
        permutations=250,
        seed=17291,
    )

    assert first == second
    assert first_details == second_details
    assert reordered == first
    assert reordered_details == first_details
    by_pathway = {row["pathway"]: row for row in first}
    assert by_pathway["UP_PATHWAY"]["nes"] > 0
    assert by_pathway["UP_PATHWAY"]["direction"] == "group_b"
    assert by_pathway["DOWN_PATHWAY"]["nes"] < 0
    assert by_pathway["DOWN_PATHWAY"]["direction"] == "group_a"
    assert [row["fdr"] for row in first] == pytest.approx(
        _benjamini_hochberg([row["p_value"] for row in first])
    )
    assert _benjamini_hochberg([0.01, 0.04, 0.03, 0.002]) == pytest.approx(
        [0.02, 0.04, 0.04, 0.008]
    )
    assert first_details["pathways_tested"] == 3
    assert first_details["permutations"] == 250
    assert first_details["seed"] == 17291
    assert first_details["unique_overlap_sizes"] == 1
    assert first_details["null_enrichment_scores_generated"] == 250


def test_camera_inference_replaces_gene_set_permutation_p_values() -> None:
    effects = [
        {
            "pathway": "PATH_B",
            "size_used": 12,
            "es": 0.55,
            "nes": 1.8,
            "leading_edge": ["G1", "G2"],
            "effect_method": "weighted_preranked_gsea",
            "effect_inferential_role": "descriptive",
        },
        {
            "pathway": "PATH_A",
            "size_used": 10,
            "es": -0.40,
            "nes": -1.2,
            "leading_edge": ["G3"],
            "effect_method": "weighted_preranked_gsea",
            "effect_inferential_role": "descriptive",
        },
    ]
    camera = [
        {
            "pathway": "PATH_A",
            "size_used": 10,
            "camera_correlation": 0.08,
            "camera_direction": "group_b",
            "p_value": 0.04,
            "fdr": 0.04,
        },
        {
            "pathway": "PATH_B",
            "size_used": 12,
            "camera_correlation": 0.12,
            "camera_direction": "group_b",
            "p_value": 0.01,
            "fdr": 0.02,
        },
    ]

    combined, details = combine_camera_inference_with_preranked_effects(
        effects,
        camera,
    )

    assert [row["pathway"] for row in combined] == ["PATH_B", "PATH_A"]
    assert combined[0]["p_value"] == 0.01
    assert combined[0]["fdr"] == 0.02
    assert combined[0]["inference_method"] == "limma_camera"
    assert combined[0]["effect_inferential_role"] == "descriptive"
    assert combined[0]["direction_concordant"] is True
    assert combined[1]["direction_concordant"] is False
    assert details["direction_discordant_pathways"] == 1


def test_gsea_summary_uses_camera_direction_for_camera_supported_pathways() -> None:
    summary = gsea_summary(
        [
            {
                "pathway": "DISCORDANT",
                "nes": -1.8,
                "camera_direction": "group_b",
                "p_value": 0.001,
                "fdr": 0.01,
            },
            {
                "pathway": "REFERENCE",
                "nes": -1.2,
                "camera_direction": "group_a",
                "p_value": 0.01,
                "fdr": 0.02,
            },
        ],
        fdr_threshold=0.05,
        group_a_label="Reference",
        group_b_label="Target",
    )

    assert summary["supported_direction_basis"] == "camera_direction"
    assert summary["enriched_in_group_b"] == 1
    assert summary["enriched_in_group_a"] == 1
    assert summary["top_group_b_pathway"] == "DISCORDANT"
    assert summary["top_group_a_pathway"] == "REFERENCE"


def test_gsea_summary_preserves_legacy_nes_direction_fallback() -> None:
    summary = gsea_summary(
        [
            {"pathway": "POSITIVE", "nes": 1.0, "p_value": 0.01, "fdr": 0.02},
            {"pathway": "ZERO", "nes": 0.0, "p_value": 0.02, "fdr": 0.03},
        ],
        fdr_threshold=0.05,
        group_a_label="Reference",
        group_b_label="Target",
    )

    assert summary["supported_direction_basis"] == "nes_direction"
    assert summary["enriched_in_group_b"] == 1
    assert summary["enriched_in_group_a"] == 0


def test_preranked_effect_layer_does_not_expose_inferential_p_or_fdr() -> None:
    ranked = [
        {"gene": f"G{index:03d}", "score": float(31 - index), "rank": index}
        for index in range(1, 61)
    ]
    pathways = [
        {
            "name": "UP_PATHWAY",
            "description": "Top-ranked genes",
            "genes": [f"G{index:03d}" for index in range(1, 9)],
        }
    ]

    effects, details = run_preranked_effects(
        ranked,
        pathways,
        min_size=5,
        max_size=20,
        permutations=25,
        seed=17291,
    )

    assert "p_value" not in effects[0]
    assert "fdr" not in effects[0]
    assert effects[0]["effect_inferential_role"] == "descriptive"
    assert details["gene_set_permutation_p_values_reported"] is False
    assert details["effect_elapsed_seconds"] >= 0


@pytest.mark.parametrize("edge_whitespace", ["", " "])
def test_pinned_camera_engine_returns_correlation_aware_p_and_global_bh(
    tmp_path: Path,
    edge_whitespace: str,
) -> None:
    if shutil.which("Rscript") is None:
        pytest.skip("Rscript is unavailable.")
    version = subprocess.run(
        [
            "Rscript",
            "-e",
            'cat(if (requireNamespace("limma", quietly=TRUE)) '
            'as.character(packageVersion("limma")) else "missing")',
        ],
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if version != "3.62.2":
        pytest.skip("Pinned limma 3.62.2 is unavailable.")

    sample_ids = [f"A{index}" for index in range(5)] + [
        f"B{index}" for index in range(5)
    ]
    genes = [f"G{index:03d}" for index in range(120)]
    rows = []
    for gene_index in range(120):
        row = []
        for sample_index in range(10):
            value = gene_index / 20 + sample_index / 7
            if gene_index < 20 and sample_index >= 5:
                value += 3
            if gene_index >= 100 and sample_index >= 5:
                value -= 3
            row.append(value + ((gene_index * sample_index) % 5) / 50)
        rows.append(row)
    matrix_path = tmp_path / "camera-source.float32le.bin"
    write_float32le_matrix(matrix_path, rows)
    matrix = ExpressionMatrix(
        path=matrix_path,
        sample_ids=sample_ids,
        genes=[MatrixGene(gene, index) for index, gene in enumerate(genes)],
        dtype="float32",
        byte_order="little",
        expression_scale="fixture",
        expression_scale_label="fixture",
        source_sha256=None,
    )
    assignments = {
        sample_id: ("a" if sample_id.startswith("A") else "b")
        for sample_id in sample_ids
    }
    ranked, _, camera_matrix = prepare_camera_expression_matrix(
        matrix,
        assignments,
        ranking_metric="welch_t",
        camera_matrix_path=tmp_path / "camera-input.float32le.bin",
    )
    gmt_path = tmp_path / "fixture.gmt"
    gmt_path.write_text(
        edge_whitespace + "UP" + edge_whitespace + "\tUp\t" + "\t".join(genes[:20]) + "\n"
        "MIDDLE\tMiddle\t" + "\t".join(genes[50:70]) + "\n"
        "DOWN\tDown\t" + "\t".join(genes[100:]) + "\n",
        encoding="utf-8",
    )

    camera_rows, details = run_camera_gene_set_test(
        camera_matrix,
        gene_set_path=gmt_path,
        min_size=15,
        max_size=30,
        work_dir=tmp_path / "camera-work",
    )

    assert [row["pathway"] for row in camera_rows] == [
        "UP",
        "MIDDLE",
        "DOWN",
    ]
    assert camera_rows[0]["camera_direction"] == "group_b"
    assert camera_rows[2]["camera_direction"] == "group_a"
    assert [row["fdr"] for row in camera_rows] == pytest.approx(
        _benjamini_hochberg([row["p_value"] for row in camera_rows])
    )
    assert all(math.isfinite(row["camera_correlation"]) for row in camera_rows)
    assert details["limma_version"] == "3.62.2"
    assert details["inter_gene_correlation"] == "estimated_per_gene_set"
    assert details["allow_negative_correlation"] is False
    assert details["trend_variance"] is True
    assert details["camera_process_wall_seconds"] >= details[
        "camera_engine_seconds"
    ]
    effects, _ = run_preranked_effects(
        ranked, read_gmt(gmt_path), min_size=15, max_size=30,
        permutations=100, seed=17291,
    )
    combined, _ = combine_camera_inference_with_preranked_effects(effects, camera_rows)
    assert {row["pathway"] for row in combined} == {"UP", "MIDDLE", "DOWN"}


def test_gsea_dotplot_encodes_fdr_as_area_and_nes_as_position_and_color() -> None:
    svg = _gsea_dotplot_svg(
        [
            {
                "pathway": "NEGATIVE & IMMUNE",
                "nes": -2.0,
                "fdr": 0.01,
            },
            {
                "pathway": "POSITIVE <SIGNAL>",
                "nes": 2.0,
                "fdr": 0.0001,
            },
            {
                "pathway": "CAPPED",
                "nes": 0.5,
                "fdr": 0.0,
            },
            {
                "pathway": "FDR ONE",
                "nes": -0.5,
                "fdr": 1.0,
            },
        ],
        group_a_label="Group A",
        group_b_label="Group B",
    )

    root = ET.fromstring(svg)
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    assert root.attrib["role"] == "img"
    assert root.attrib["aria-labelledby"] == "dotplot-title dotplot-desc"
    description = root.find("svg:desc", namespace)
    assert description is not None
    assert "The 4 pathways" in (description.text or "")
    assert "Circle area is proportional" in (description.text or "")
    assert "capped at 10" in (description.text or "")
    assert "small cross" in (description.text or "")
    assert "dark-blue-to-white-to-red" in (description.text or "")
    assert "dashed vertical reference" in (description.text or "")

    gradient_stops = root.findall(
        ".//svg:linearGradient[@id='nes-color-scale']/svg:stop",
        namespace,
    )
    assert [stop.attrib["stop-color"] for stop in gradient_stops] == [
        "#00008b",
        "#ffffff",
        "#ff0000",
    ]
    assert [stop.attrib["offset"] for stop in gradient_stops] == [
        "0%",
        "50%",
        "100%",
    ]

    legend = root.find("svg:g[@id='dotplot-legends']", namespace)
    assert legend is not None
    assert legend.attrib["data-position"] == "top"
    axis = root.find("svg:g[@id='nes-axis']", namespace)
    assert axis is not None
    assert axis.attrib["data-position"] == "bottom"
    zero_reference = root.find(
        ".//svg:line[@data-role='nes-zero-reference']",
        namespace,
    )
    assert zero_reference is not None
    assert zero_reference.attrib["stroke-dasharray"] == "5 4"
    pathway_labels = root.findall(
        ".//svg:text[@data-role='pathway-label']",
        namespace,
    )
    assert len(pathway_labels) == 4
    assert all(
        label.attrib["data-axis-side"] == "right"
        for label in pathway_labels
    )
    assert all(label.attrib["text-anchor"] == "start" for label in pathway_labels)
    assert all(float(label.attrib["x"]) > 650 for label in pathway_labels)

    points = [
        circle
        for circle in root.findall(".//svg:circle", namespace)
        if "data-negative-log10-fdr" in circle.attrib
    ]
    assert len(points) == 4
    negative, positive, capped, fdr_one = points
    assert float(negative.attrib["cx"]) < float(positive.attrib["cx"])
    assert negative.attrib["fill"] == "#00008b"
    assert positive.attrib["fill"] == "#ff0000"
    assert math.isclose(
        float(positive.attrib["r"]) ** 2
        / float(negative.attrib["r"]) ** 2,
        2.0,
        rel_tol=0.02,
    )
    assert float(capped.attrib["data-negative-log10-fdr"]) == 10.0
    assert math.isclose(float(capped.attrib["r"]), 12.0)
    assert float(fdr_one.attrib["data-negative-log10-fdr"]) == 0.0
    assert float(fdr_one.attrib["r"]) == 0.0
    assert len(root.findall(".//svg:path", namespace)) == 2


def test_gsea_orchestration_writes_a_complete_reproducibility_bundle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sample_ids = [f"A{index}" for index in range(5)] + [
        f"B{index}" for index in range(5)
    ]
    rows: list[list[float]] = []
    genes = [f"G{index:03d}" for index in range(1, 121)]
    for index in range(120):
        if index < 20:
            rows.append(
                [1 + offset / 20 for offset in range(5)]
                + [5 + offset / 20 for offset in range(5)]
            )
        elif index >= 100:
            rows.append(
                [5 + offset / 20 for offset in range(5)]
                + [1 + offset / 20 for offset in range(5)]
            )
        else:
            rows.append(
                [2 + index / 100 + offset / 20 for offset in range(5)]
                + [2 + index / 100 + offset / 18 for offset in range(5)]
            )
    matrix_path = tmp_path / "expression.float32le.bin"
    write_float32le_matrix(matrix_path, rows)
    matrix = ExpressionMatrix(
        path=matrix_path,
        sample_ids=sample_ids,
        genes=[
            MatrixGene(symbol=symbol, row_number=index)
            for index, symbol in enumerate(genes)
        ],
        dtype="float32",
        byte_order="little",
        expression_scale="log2_tpm",
        expression_scale_label="log2(TPM + 1)",
        source_sha256=hashlib.sha256(matrix_path.read_bytes()).hexdigest(),
    )
    samples = [
        MockSample(
            patient_id=f"P-{sample_id}",
            barcode=sample_id,
            stage="Stage I" if sample_id.startswith("A") else "Stage II",
        )
        for sample_id in sample_ids
    ]

    gene_set_dir = tmp_path / "gene_sets"
    gene_set_dir.mkdir()
    gmt_path = gene_set_dir / "fixture.gmt"
    gmt_path.write_text(
        "UP\tTop genes\t" + "\t".join(genes[:15]) + "\n"
        "DOWN\tBottom genes\t" + "\t".join(genes[-15:]) + "\n"
        "MIDDLE\tMiddle genes\t" + "\t".join(genes[50:65]) + "\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(gmt_path.read_bytes()).hexdigest()
    (gene_set_dir / "collections.json").write_text(
        json.dumps(
            {
                "collections": [
                    {
                        "id": "fixture",
                        "label": "Fixture pathways",
                        "version": "fixture-v1",
                        "file": "fixture.gmt",
                        "sha256": digest,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    collection = load_gene_set_catalog(gene_set_dir)[0]
    artifact_root = tmp_path / "artifacts"
    fake_settings = SimpleNamespace(
        artifact_dir=artifact_root,
        gsea_gene_set_dir=gene_set_dir,
    )

    class FakeSession:
        def get(self, model, key):
            if model is Cohort and key == "TCGA-TEST":
                return SimpleNamespace(id=key)
            return None

    def write_fixture_receipt(
        _settings,
        *,
        subject_id,
        **_kwargs,
    ):
        receipt = artifact_root / "gsea" / subject_id / "attestation_receipt.json"
        receipt.write_text('{"fixture": true}\n', encoding="utf-8")
        return {"path": str(receipt)}

    monkeypatch.setattr(main_module, "settings", fake_settings)
    monkeypatch.setattr(
        main_module,
        "resolve_expression_matrix",
        lambda *_args, **_kwargs: matrix,
    )
    monkeypatch.setattr(
        main_module,
        "dataset_samples",
        lambda *_args, **_kwargs: samples,
    )
    monkeypatch.setattr(
        main_module,
        "current_data_version",
        lambda _db: {"fixture": {"manifest_hash": "fixture-hash"}},
    )
    monkeypatch.setattr(
        main_module,
        "write_attestation_receipt",
        write_fixture_receipt,
    )
    monkeypatch.setattr(
        main_module,
        "run_camera_gene_set_test",
        lambda camera_matrix, **_kwargs: (
            [
                {
                    "pathway": pathway,
                    "size_used": 15,
                    "camera_correlation": 0.05,
                    "camera_direction": direction,
                    "p_value": p_value,
                    "fdr": fdr,
                }
                for pathway, direction, p_value, fdr in (
                    ("UP", "group_b", 0.001, 0.003),
                    ("DOWN", "group_a", 0.01, 0.015),
                    ("MIDDLE", "group_b", 0.8, 0.8),
                )
            ],
            {
                "schema_version": "trace-camera-gene-set-test-v1",
                "method": "limma_camera",
                "hypothesis": "competitive",
                "limma_version": "3.62.2",
                "camera_engine_seconds": 0.2,
                "camera_process_wall_seconds": 0.3,
                "complete_case_genes": len(camera_matrix.genes),
                "pathways_tested": 3,
            },
        ),
    )
    request = GseaAnalysisRequest(
        cohort="TCGA-TEST",
        grouping=GseaGroupingDefinition(
            source="clinical",
            clinical_variable="stage",
            group_a_label="Stage I",
            group_b_label="Stage II",
            group_a_values=["Stage I"],
            group_b_values=["Stage II"],
        ),
        gene_set_collection="fixture",
        min_gene_set_size=5,
        max_gene_set_size=30,
        permutations=100,
        seed=99,
    )

    result = main_module._create_gsea_analysis_unlocked(
        request,
        FakeSession(),
        collection=collection,
    )

    result_dir = artifact_root / "gsea" / result.gsea_id
    assert result.status == "completed"
    assert result.ranking["genes_ranked"] == 120
    assert result.summary["pathways_tested"] == 3
    assert result.grouping["group_counts"] == {
        "Stage I": 5,
        "Stage II": 5,
    }
    assert result.audit["report_type"] == "camera_preranked_gsea_audit"
    assert result.inference["primary_method"] == "limma_camera"
    assert result.inference["camera_engine_seconds"] == 0.2
    assert result.pathways[0]["p_value"] == 0.001
    assert result.pathways[0]["inference_method"] == "limma_camera"
    assert {
        "input",
        "gene_set_manifest",
        "dotplot_svg",
        "attestation",
        "zip",
    }.issubset(result.downloads)
    for filename in {
        "input.json",
        "ranked_genes.csv",
        "sample_groups.csv",
        "gsea_results.csv",
        "leading_edges.csv",
        "gsea_landscape.svg",
        "gsea_dotplot.svg",
        "methodology.txt",
        "camera_gsea.R",
        "gene_set_manifest.json",
        "result.json",
        "audit_report.json",
        "attestation_receipt.json",
    }:
        assert (result_dir / filename).is_file()
    dotplot_record = result.audit["artifacts"]["dotplot_svg"]
    assert dotplot_record["filename"] == "gsea_dotplot.svg"
    assert dotplot_record["sha256"] == hashlib.sha256(
        (result_dir / "gsea_dotplot.svg").read_bytes()
    ).hexdigest()

    monkeypatch.setattr(
        main_module,
        "_public_gsea_job",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )
    dotplot_response = main_module.download_public_gsea_artifact(
        result.gsea_id,
        "dotplot_svg",
        request,
        FakeSession(),
    )
    assert Path(dotplot_response.path).name == "gsea_dotplot.svg"
    assert dotplot_response.media_type == "image/svg+xml"
    zip_response = main_module.download_public_gsea_artifact(
        result.gsea_id,
        "zip",
        request,
        FakeSession(),
    )
    with zipfile.ZipFile(io.BytesIO(zip_response.body)) as archive:
        assert "gsea_landscape.svg" in archive.namelist()
        assert "gsea_dotplot.svg" in archive.namelist()
        assert "camera_gsea.R" in archive.namelist()


def test_survival_grouping_reuses_exact_frozen_assignments(
    tmp_path: Path,
) -> None:
    raw_data = tmp_path / "raw_data.csv"
    raw_data.write_text(
        "patient_id,sample_barcode,group,expression_value\n"
        "P-low-2,TCGA-TS-0002-01A,Low,1.2\n"
        "P-high-1,TCGA-TS-0003-01A,High,9.4\n"
        "P-low-1,TCGA-TS-0001-01A,Low,2.3\n"
        "P-high-2,TCGA-TS-0004-01A,High,8.7\n",
        encoding="utf-8",
    )
    job = SimpleNamespace(
        id="survival-fixture",
        status="completed",
        cohort="TCGA-TEST",
        dataset_id=None,
        dataset_release_id=None,
        cutpoint_method="maxstat",
        csv_path=str(raw_data),
        request_payload={
            "gene_symbol": "GENE1",
            "cutpoint_method": "maxstat",
            "filters": {"sample_population": "primary_solid"},
        },
    )

    class FakeSession:
        def get(self, model, key):
            assert model is AnalysisJob
            assert key == job.id
            return job

    grouping = GseaGroupingDefinition(
        source="survival",
        survival_analysis_id=job.id,
        group_a_label="Inherited low",
        group_b_label="Inherited high",
        group_a_values=["low"],
        group_b_values=["HIGH"],
    )

    assignments, details, inherited_rows = survival_group_assignments(
        FakeSession(),
        cohort="TCGA-TEST",
        dataset_id=None,
        dataset_release_id=None,
        grouping=grouping,
    )

    assert assignments == {
        "TCGA-TS-0002-01A": "a",
        "TCGA-TS-0003-01A": "b",
        "TCGA-TS-0001-01A": "a",
        "TCGA-TS-0004-01A": "b",
    }
    assert inherited_rows == [
        {
            "sample_barcode": "TCGA-TS-0002-01A",
            "patient_id": "P-low-2",
            "source_group": "Low",
        },
        {
            "sample_barcode": "TCGA-TS-0003-01A",
            "patient_id": "P-high-1",
            "source_group": "High",
        },
        {
            "sample_barcode": "TCGA-TS-0001-01A",
            "patient_id": "P-low-1",
            "source_group": "Low",
        },
        {
            "sample_barcode": "TCGA-TS-0004-01A",
            "patient_id": "P-high-2",
            "source_group": "High",
        },
    ]
    assert details["source_group_a"] == "Low"
    assert details["source_group_b"] == "High"
    assert details["source_cutpoint_method"] == "maxstat"
    assert details["sample_population"]["id"] == "primary_solid"
    assert "outcome-informed" in details["circularity_notice"]


def test_survival_grouping_rejects_legacy_mixed_skcm_source(
    tmp_path: Path,
) -> None:
    raw_data = tmp_path / "legacy-skcm.csv"
    raw_data.write_text(
        "patient_id,sample_barcode,group\n"
        "P1,TCGA-SK-0001-01A,Low\n"
        "P2,TCGA-SK-0002-06A,High\n",
        encoding="utf-8",
    )
    job = SimpleNamespace(
        id="legacy-skcm",
        status="completed",
        cohort="TCGA-SKCM",
        dataset_id=None,
        dataset_release_id=None,
        cutpoint_method="median",
        csv_path=str(raw_data),
        request_payload={"gene_symbol": "PDCD1", "filters": {}},
    )

    class FakeSession:
        def get(self, model, key):
            return job

    grouping = GseaGroupingDefinition(
        source="survival",
        survival_analysis_id=job.id,
        group_a_label="Low",
        group_b_label="High",
    )

    with pytest.raises(ValueError, match="Choose primary_solid or metastatic"):
        survival_group_assignments(
            FakeSession(),
            cohort="TCGA-SKCM",
            dataset_id=None,
            dataset_release_id=None,
            grouping=grouping,
        )
