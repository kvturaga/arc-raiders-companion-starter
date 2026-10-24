from __future__ import annotations

from pathlib import Path

import pytest

from arc_companion import commands
from arc_companion.enums import Location, PreferenceKey
from arc_companion.model import (
    Goal,
    Holding,
    ItemInstance,
    PlayerBuild,
    Preference,
    ProjectContribution,
)
from arc_companion.queries import plan
from arc_companion.store import load

from .conftest import apply_change


def test_goal_priority_is_set_and_cleared(project: Path) -> None:
    apply_change(project, commands.set_goal_priority("gunsmith_3", 1))
    assert load(project / "data").get(Goal, "gunsmith_3").priority == 1
    apply_change(project, commands.set_goal_priority("gunsmith_3", None))
    assert load(project / "data").get(Goal, "gunsmith_3").priority is None


def test_a_new_goal_carries_requirements_and_prerequisites(project: Path) -> None:
    change = commands.add_goal(
        "hand_drill_reserve", "Keep 20 Hand Drills", 3, {"Hand Drill": 20}, ["gunsmith_3"]
    )
    apply_change(project, change)
    state = load(project / "data")
    packet = plan(state, state.get(Goal, "hand_drill_reserve"))
    assert [r["item"] for r in packet["requirements"]] == ["hand_drill"]
    assert packet["blocked_by"] == ["gunsmith_3"]


def test_a_duplicate_goal_is_refused(project: Path) -> None:
    with pytest.raises(commands.Refused, match="already exists"):
        apply_change(project, commands.add_goal("gunsmith_3", "again", None, {}, []))


def test_a_preference_is_recorded(project: Path) -> None:
    apply_change(project, commands.set_preference(PreferenceKey.STASH_HIGH_CASH_THRESHOLD, 180000))
    state = load(project / "data")
    assert state.get(Preference, PreferenceKey.STASH_HIGH_CASH_THRESHOLD.value).value == 180000


def test_durability_on_a_counted_item_makes_it_a_tracked_piece(project: Path) -> None:
    apply_change(project, commands.set_condition("Burletta I", 100, 100))
    piece = next(i for i in load(project / "data").all(ItemInstance) if i.item.id == "berletta_i")
    assert (piece.condition, piece.condition_max) == (100, 100)


def test_the_build_records_level_and_tree_points(project: Path) -> None:
    apply_change(project, commands.set_build(31, None, 6, 0))
    build = load(project / "data").all(PlayerBuild)[0]
    assert (build.level, build.conditioning_points, build.unspent_points) == (31, 6, 0)


def test_contributing_removes_items_and_counts_toward_the_goal(project: Path) -> None:
    apply_change(project, commands.set_count("Metal Parts", Location.STASH, 50))
    apply_change(project, commands.add_goal("demo", "Demo project", None, {"Metal Parts": 30}, []))
    apply_change(project, commands.contribute("demo", "Metal Parts", 20, Location.STASH))
    state = load(project / "data")
    assert state.get(Holding, "metal_parts@stash").quantity == 30
    assert state.get(ProjectContribution, ("demo", "metal_parts")).quantity == 20
    with pytest.raises(commands.Refused, match="contributions"):
        apply_change(project, commands.contribute("demo", "Metal Parts", 20, Location.STASH))
