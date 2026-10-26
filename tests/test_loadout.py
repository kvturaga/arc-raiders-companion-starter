from __future__ import annotations

from pathlib import Path

import pytest

from arc_companion import commands
from arc_companion.enums import Location, SourceKind
from arc_companion.model import PlayerBuild, StashCounter
from arc_companion.queries import resolve
from arc_companion.store import load
from arc_companion.views import expected

from .conftest import apply_change


def test_data_without_a_new_optional_column_still_loads(project: Path) -> None:
    path = project / "data" / "player_build.csv"
    header, row = path.read_text().splitlines()[:2]
    columns, values = header.split(","), row.split(",")
    keep = [i for i, c in enumerate(columns) if c != "survival_points"]
    path.write_text(
        ",".join(columns[i] for i in keep) + "\n" + ",".join(values[i] for i in keep) + "\n"
    )
    assert load(project / "data").all(PlayerBuild)[0].survival_points is None


def test_survival_points_are_recorded(project: Path) -> None:
    apply_change(project, commands.set_build(31, None, None, 0, survival=6))
    assert load(project / "data").all(PlayerBuild)[0].survival_points == 6


def test_the_safe_pocket_cannot_hold_more_than_the_augment_allows(project: Path) -> None:
    apply_change(project, commands.import_augment_capacities(), SourceKind.WEB)
    lines = [
        commands.CountLine(Location.EQUIPMENT, "Looting Mk. II", (1,)),
        commands.CountLine(Location.SAFE_POCKET, "Grappling Hook", (1,)),
        commands.CountLine(Location.SAFE_POCKET, "Photoelectric Cloak", (1,)),
    ]
    apply_change(project, commands.stocktake(lines, stash_used=None))
    with pytest.raises(commands.Refused, match="loadout_capacity"):
        apply_change(project, commands.set_count("Zipline", Location.SAFE_POCKET, 1, slots=1))


def test_expected_counter_adds_slots_only_when_a_stack_spills(project: Path) -> None:
    apply_change(project, commands.set_stack_sizes({"Metal Parts": 50}))
    apply_change(project, commands.set_count("Metal Parts", Location.STASH, 340, slots=7))
    state = load(project / "data")
    metal = resolve(state, "Metal Parts")
    counter = state.all(StashCounter)[0].used
    assert expected(state, {metal: 10}, {}, {})["counter_expected"] == counter
    spilled = expected(state, {metal: 11}, {}, {})
    assert spilled["counter_expected"] == counter + 1
    assert spilled["slot_changes"] == [
        {"item": "Metal Parts", "before": 340, "after": 351, "slots": 1}
    ]
