from __future__ import annotations

import csv
import importlib
from pathlib import Path
from typing import cast

import pytest

from arc_companion import commands
from arc_companion.enums import SourceKind
from arc_companion.store import State, write

PROJECT = Path(__file__).resolve().parents[1]
# A new player's package has no legacy import; tests that need it skip.
_LEGACY = sorted((PROJECT / "legacy").iterdir()) if (PROJECT / "legacy").exists() else []
LEGACY = _LEGACY[0] if _LEGACY else PROJECT / "legacy"


@pytest.fixture(scope="session")
def migrated() -> State:
    if not _LEGACY:
        pytest.skip("no legacy import in this package")
    # Loaded by name: shared copies have no arc_legacy package, and must still type-check.
    legacy = importlib.import_module("arc_legacy.migrate")
    state, _ = legacy.migrate(LEGACY / "data", LEGACY.name)
    return cast(State, state)


@pytest.fixture
def project(tmp_path: Path, migrated: State) -> Path:
    """A throwaway project (no git) whose data/ is the frozen migration."""
    write(migrated, tmp_path / "data")
    return tmp_path


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(root.glob("*.csv"))}


def apply_change(
    project: Path, change: commands.Change, kind: SourceKind = SourceKind.USER_REPORT
) -> str:
    """Run a setter against a test project without committing."""
    return commands.apply(project, "test observation", "pytest", change, commit=False, kind=kind)
