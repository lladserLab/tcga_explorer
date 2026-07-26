#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path("manuscript/bioinformatics_app_note/build/tcga-trace-review-package-final.tar.gz")

MAIN_PDF = Path("manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-application-note.pdf")
OUP_PREVIEW_PDF = Path(
    "manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-oup-preview.pdf"
)
SUPPLEMENT_PDF = Path("manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-supplement.pdf")


@dataclass(frozen=True)
class CommandStep:
    label: str
    argv: list[str]


@dataclass(frozen=True)
class FinalPackage:
    archive: Path
    archive_bytes: int
    archive_sha256: str
    main_pdf: Path
    oup_preview_pdf: Path
    supplement_pdf: Path


def main() -> int:
    args = parse_args()
    output = resolve_path(args.output)
    summary_output = resolve_path(args.summary_output) if args.summary_output else default_summary_path(output)
    steps = command_steps(
        resolve_path(args.metadata),
        output,
        license_source=resolve_path(args.license_source) if args.license_source else None,
        overwrite_license=args.overwrite_license,
    )

    if args.dry_run:
        print("Final submission package dry run. Commands that would run:")
        for step in steps:
            print(f"- {step.label}: {shell_join(step.argv)}")
        print(f"- write final package summary: {display(summary_output)}")
        try:
            validate_metadata_dry_run(steps[0])
        except FinalizeError as exc:
            print(f"Final submission packaging dry run failed: {exc}", file=sys.stderr)
            return 1
        return 0

    try:
        run_steps(steps)
        package = final_package(output)
        write_summary(package, summary_output)
    except FinalizeError as exc:
        print(f"Final submission packaging failed: {exc}", file=sys.stderr)
        return 1

    print("Final submission package ready:")
    print(f"- Main PDF: {display(package.main_pdf)}")
    print(f"- OUP preview PDF: {display(package.oup_preview_pdf)}")
    print(f"- Supplement PDF: {display(package.supplement_pdf)}")
    print(f"- Archive: {display(package.archive)}")
    print(f"- Archive bytes: {package.archive_bytes}")
    print(f"- Archive SHA-256: {package.archive_sha256}")
    print(f"- Summary JSON: {display(summary_output)}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Apply owner-supplied submission metadata, run the strict local "
            "pre-submission gate, build the compact reviewer/source archive and "
            "verify that archive. This command is intended for the final handoff "
            "after authorship, license, repository and DOI/release decisions are supplied."
        )
    )
    parser.add_argument("metadata", help="Owner metadata JSON consumed by apply_submission_metadata.py.")
    parser.add_argument(
        "--license-source",
        help="Path to complete final license text. Required unless a valid root LICENSE already exists.",
    )
    parser.add_argument(
        "--overwrite-license",
        action="store_true",
        help="Allow --license-source to replace an existing different root LICENSE file.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"Final archive output path, default: {DEFAULT_OUTPUT}.",
    )
    parser.add_argument(
        "--summary-output",
        help=(
            "Optional final package summary JSON path. Defaults to the archive "
            "path with .summary.json replacing .tar.gz."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the command plan and validate owner metadata/license without changing files.",
    )
    return parser.parse_args()


def command_steps(
    metadata: Path,
    output: Path,
    *,
    license_source: Path | None = None,
    overwrite_license: bool = False,
) -> list[CommandStep]:
    apply_cmd = [
        "scripts/publication/apply_submission_metadata.py",
        str(display(metadata)),
    ]
    if license_source is not None:
        apply_cmd.extend(["--license-source", str(display(license_source))])
    if overwrite_license:
        apply_cmd.append("--overwrite-license")

    return [
        CommandStep("apply owner metadata", apply_cmd),
        CommandStep("run strict pre-submission gate", ["scripts/publication/pre_submission_check.sh", "--strict-owner-metadata"]),
        CommandStep(
            "build final reviewer/source archive",
            [
                "scripts/publication/build_submission_archive.py",
                "--strict-owner-metadata",
                "--output",
                str(display(output)),
            ],
        ),
        CommandStep("verify final archive", ["scripts/publication/verify_submission_archive.py", str(display(output))]),
    ]


def run_steps(steps: list[CommandStep]) -> None:
    for step in steps:
        print(f"==> {step.label}")
        try:
            subprocess.run(step.argv, cwd=ROOT, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise FinalizeError(f"{step.label} failed") from exc


def validate_metadata_dry_run(apply_step: CommandStep) -> None:
    argv = [*apply_step.argv, "--dry-run"]
    print(f"==> validate owner metadata without writing: {shell_join(argv)}")
    try:
        subprocess.run(argv, cwd=ROOT, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise FinalizeError("owner metadata dry-run validation failed") from exc


def final_package(output: Path) -> FinalPackage:
    required = [output, ROOT / MAIN_PDF, ROOT / OUP_PREVIEW_PDF, ROOT / SUPPLEMENT_PDF]
    missing = [display(path) for path in required if not path.is_file()]
    if missing:
        raise FinalizeError("missing final output(s): " + ", ".join(str(path) for path in missing))
    return FinalPackage(
        archive=output,
        archive_bytes=output.stat().st_size,
        archive_sha256=file_sha256(output),
        main_pdf=ROOT / MAIN_PDF,
        oup_preview_pdf=ROOT / OUP_PREVIEW_PDF,
        supplement_pdf=ROOT / SUPPLEMENT_PDF,
    )


def default_summary_path(output: Path) -> Path:
    name = output.name
    if name.endswith(".tar.gz"):
        return output.with_name(name[: -len(".tar.gz")] + ".summary.json")
    return output.with_suffix(output.suffix + ".summary.json")


def write_summary(package: FinalPackage, output: Path) -> None:
    payload = {
        "schema_version": "tcga-trace-final-package-summary-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "main_pdf": file_record(package.main_pdf),
        "oup_preview_pdf": file_record(package.oup_preview_pdf),
        "supplement_pdf": file_record(package.supplement_pdf),
        "archive": {
            "path": str(display(package.archive)),
            "bytes": package.archive_bytes,
            "sha256": package.archive_sha256,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def file_record(path: Path) -> dict[str, str | int]:
    return {
        "path": str(display(path)),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def display(path: Path) -> Path:
    try:
        return path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return path


def shell_join(argv: list[str]) -> str:
    return " ".join(shlex.quote(item) for item in argv)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FinalizeError(Exception):
    pass


if __name__ == "__main__":
    sys.exit(main())
