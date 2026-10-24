from __future__ import annotations

import csv
import importlib
import shutil
from pathlib import Path
from typing import cast

import pytest

from arc_companion import commands
from arc_companion.enums import SourceKind
from arc_companion.store import State, write

from .demo import build_demo

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


# Game facts for the demo player: this repo's data, or a shared copy's starter_data.
SEED = PROJECT / "data" if (PROJECT / "data").exists() else PROJECT / "starter_data"


@pytest.fixture(scope="session")
def demo_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("demo")
    build_demo(root, SEED)
    return root


@pytest.fixture
def project(tmp_path: Path, demo_template: Path) -> Path:
    """A throwaway project (no git) holding the demo player (tests/demo.py)."""
    shutil.copytree(demo_template / "data", tmp_path / "data")
    return tmp_path


@pytest.fixture
def legacy_project(tmp_path: Path, migrated: State) -> Path:
    """A throwaway project (no git) whose data/ is the frozen legacy migration. Only for
    behavior that exists because of that import (parity, legacy unreconciled rows)."""
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
