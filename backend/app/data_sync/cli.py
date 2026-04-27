from __future__ import annotations

import argparse
import json
import sys

from app.data_sync.sync import SyncError, import_after_sync, run_sync
from app.config import get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Incrementally synchronize TCGA data sources.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("check", "apply"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--source", choices=["all", "tcga_rna", "tcga_cdr"], default="all")
        sub.add_argument("--max-workers", type=int, default=10)
        sub.add_argument(
            "--reimport",
            action="store_true",
            help="Force database reimport after an apply run. Backend startup also reimports when restarted.",
        )

    args = parser.parse_args(argv)
    apply = args.command == "apply"
    try:
        payload = run_sync(source=args.source, apply=apply, max_workers=args.max_workers)
        if apply and args.reimport:
            import_after_sync(get_settings())
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 20 if apply and payload["status"] == "updated" else 0
    except SyncError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

