from __future__ import annotations

import importlib.util
import sys
import tarfile
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "build_submission_archive.py"
SPEC = importlib.util.spec_from_file_location("build_submission_archive", MODULE_PATH)
assert SPEC is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
assert SPEC.loader is not None
SPEC.loader.exec_module(builder)


def test_should_include_excludes_runtime_data_but_keeps_reconstruction_bundle() -> None:
    assert not builder.should_include(Path("derived/rna_bulk/matrices/TCGA-KIRC/log2_tpm.float32.bin"))
    assert not builder.should_include(Path("artifacts/other-analysis/raw_data.csv"))
    assert builder.should_include(Path("artifacts/.gitkeep"))
    bundles = builder.reproducibility_bundle_paths(builder.ROOT)
    assert bundles
    assert builder.should_include(bundles[0] / "audit_report.json")


def test_should_include_keeps_manuscript_pdfs_but_excludes_archives() -> None:
    assert builder.should_include(
        Path("manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-application-note.pdf")
    )
    assert not builder.should_include(Path("manuscript/bioinformatics_app_note/build/package.tar.gz"))


def test_write_archive_adds_manifest_under_prefix(tmp_path: Path) -> None:
    root = tmp_path
    source = root / "README.md"
    source.write_text("review package\n", encoding="utf-8")
    record = builder.file_record(root, Path("README.md"))
    manifest = builder.build_archive_manifest(
        [record],
        {
            "owner_metadata_blockers": ["release pending"],
            "owner_metadata_decision_count": 1,
            "owner_metadata_occurrence_count": 1,
            "owner_metadata_decisions": [
                {
                    "decision": "release_archive",
                    "label": "Version-specific archive DOI or URL",
                    "occurrence_count": 1,
                    "occurrences": ["release pending"],
                }
            ],
            "artifact_count": 1,
            "available_artifact_count": 1,
        },
        "pkg",
        root / "out.tar.gz",
    )
    assert manifest["project_name"] == "TCGA-TRACE"
    assert manifest["owner_metadata_decision_count"] == 1
    assert manifest["owner_metadata_occurrence_count"] == 1
    assert manifest["owner_metadata_decisions"][0]["decision"] == "release_archive"

    output = root / "out.tar.gz"
    builder.write_archive(root, output, "pkg", [record], manifest)

    with tarfile.open(output, mode="r:gz") as archive:
        names = set(archive.getnames())

    assert "pkg/README.md" in names
    assert "pkg/submission_archive_manifest.json" in names
