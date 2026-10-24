from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from arc_companion import cli, commands
from arc_companion.enums import MetricKind
from arc_companion.model import AccountMetric
from arc_companion.store import LoadError, load

from .conftest import apply_change


def _edit(project: Path, table: str, old: str, new: str) -> None:
    path = project / "data" / f"{table}.csv"
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new, 1))


def test_unknown_reference_is_a_load_error(project: Path) -> None:
    _edit(project, "recipe_inputs", "mechanical_component,", "mechanical_component_typo,")
    with pytest.raises(LoadError, match="recipe_id"):
        load(project / "data")


def test_free_text_in_an_enum_column_is_rejected(project: Path) -> None:
    _edit(project, "goals", ",active,", ",kinda active,")
    with pytest.raises(LoadError, match="status"):
        load(project / "data")


def test_blank_required_value_is_rejected(project: Path) -> None:
    path = project / "data" / "stash_counter.csv"
    header, row = path.read_text().splitlines()[:2]
    cells = row.split(",")
    cells[header.split(",").index("used")] = ""
    path.write_text(header + "\n" + ",".join(cells) + "\n")
    with pytest.raises(LoadError, match="used is required"):
        load(project / "data")


def test_unexpected_column_is_rejected(project: Path) -> None:
    _edit(project, "goals", "id,name,status", "id,name,status_text")
    with pytest.raises(LoadError, match="columns"):
        load(project / "data")


def test_duplicate_key_is_rejected(project: Path) -> None:
    path = project / "data" / "stations.csv"
    lines = path.read_text().splitlines()
    path.write_text("\n".join([*lines, lines[1]]) + "\n")
    with pytest.raises(LoadError, match="duplicate"):
        load(project / "data")


def _crash(project: Path, *, swapped_out: bool) -> None:
    """Leave `data/` as a crash would: staging written, the old copy maybe already moved aside."""
    data = project / "data"
    staging = data.with_name("data.staging")
    shutil.copytree(data, staging)
    if swapped_out:
        data.rename(data.with_name("data.retired"))


@pytest.mark.parametrize("swapped_out", [False, True])
def test_a_save_interrupted_by_a_crash_is_recovered_by_the_next_write(
    project: Path, swapped_out: bool
) -> None:
    _crash(project, swapped_out=swapped_out)
    apply_change(project, commands.set_metric(MetricKind.COINS, 123))
    assert sorted(p.name for p in project.glob("data*")) == ["data"]
    assert load(project / "data").get(AccountMetric, MetricKind.COINS).value == 123


def test_a_read_after_a_crash_between_renames_finishes_the_save(project: Path) -> None:
    _crash(project, swapped_out=True)
    cli.main(["--project", str(project), "bootstrap"])
    assert sorted(p.name for p in project.glob("data*")) == ["data"]


def test_a_lock_left_by_a_dead_writer_is_taken_over(project: Path) -> None:
    lock = project / ".arc-write.lock"
    lock.write_text("999999")  # above any pid macOS or Linux hands out by default
    apply_change(project, commands.set_metric(MetricKind.COINS, 5))
    assert not lock.exists()
    lock.write_text(str(os.getpid()))  # a live writer still blocks
    with pytest.raises(LoadError, match="held by another writer"):
        apply_change(project, commands.set_metric(MetricKind.COINS, 6))
