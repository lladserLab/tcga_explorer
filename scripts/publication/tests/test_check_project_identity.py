from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "check_project_identity.py"
SPEC = importlib.util.spec_from_file_location("check_project_identity", MODULE_PATH)
assert SPEC is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
assert SPEC.loader is not None
SPEC.loader.exec_module(checker)


def test_repository_uses_canonical_project_identity() -> None:
    assert checker.collect_blockers(checker.ROOT) == []
