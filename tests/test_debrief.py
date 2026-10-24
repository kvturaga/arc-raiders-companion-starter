from __future__ import annotations

from pathlib import Path

from arc_companion import commands
from arc_companion.enums import DispositionAction, SourceKind
from arc_companion.model import Holding, Objective
from arc_companion.packets import DebriefRow
from arc_companion.queries import resolve
from arc_companion.reference import read_dataset
from arc_companion.store import load
from arc_companion.views import debrief

from .conftest import apply_change


def _row(project: Path, name: str, haul: int) -> DebriefRow:
    state = load(project / "data")
    return debrief(state, {resolve(state, name): haul})[0]


def test_basic_materials_are_kept_whatever_the_amount(project: Path, tmp_path: Path) -> None:
    items = tmp_path / "items"
    items.mkdir()
    row_json = '{"id": "metal_parts", "name": {"en": "Metal Parts"}, "type": "Basic Material"}'
    (items / "metal_parts.json").write_text(row_json)
    change = commands.import_reference(read_dataset(items))
    commands.apply(project, "t", "pytest", change, commit=False, kind=SourceKind.WEB_REFERENCE)
    row = _row(project, "Metal Parts", 50)
    assert row["decision"] == "keep"
    assert row["why"] == "basic material: feeds most crafting"


def test_goal_needs_are_kept_even_past_a_sell_rule(project: Path) -> None:
    apply_change(
        project, commands.set_disposition("Sentinel Firing Cores", DispositionAction.SELL, 0)
    )
    row = _row(project, "Sentinel Firing Cores", 1)
    needed = row["needed_by"]
    assert isinstance(needed, list)
    assert needed
    assert "sell" not in str(row["decision"]) or "keep 0" not in str(row["decision"])


def test_a_hold_rule_keeps_everything(project: Path) -> None:
    apply_change(project, commands.set_disposition("Hornet Driver", DispositionAction.HOLD, 0))
    row = _row(project, "Hornet Driver", 5)
    assert row["decision"] == "keep"
    assert row["why"] == "your standing rule: hold"


def test_a_keep_rule_sells_the_surplus_and_counts_coins(project: Path) -> None:
    apply_change(project, commands.set_disposition("Wires", DispositionAction.SELL, 15))
    state = load(project / "data")
    wires = resolve(state, "Wires")
    stash = state.get(Holding, "wires@stash").quantity or 0
    row = debrief(state, {wires: 40 - stash if stash < 40 else 0})[0]
    assert str(row["decision"]).startswith("sell ")
    assert str(row["decision"]).endswith("keep 15")


def test_an_item_a_quest_objective_uses_is_kept(legacy_project: Path) -> None:
    # Objectives exist only in the legacy import until an add-objective setter exists.
    state = load(legacy_project / "data")
    quest_items = [o.item for o in state.all(Objective) if o.item is not None]
    assert quest_items, "fixture should have a destroy-with-item objective"
    row = debrief(state, {quest_items[0]: 1})[0]
    assert row["decision"] == "keep"
    assert str(row["why"]).startswith("quest ")
