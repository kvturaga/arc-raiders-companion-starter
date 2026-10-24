from __future__ import annotations

from pathlib import Path

import pytest

from arc_companion.store import LoadError, load


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
