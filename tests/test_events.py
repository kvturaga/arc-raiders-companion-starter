"""Actions saved as they are reported, on the demo player (tests/demo.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from arc_companion import cli, commands
from arc_companion.enums import ActionKind, Location, MetricKind
from arc_companion.model import AccountMetric, Holding, InventoryAction, ItemInstance
from arc_companion.queries import stash_slot_math
from arc_companion.store import load

from .conftest import apply_change, snapshot

STASH, BACKPACK = Location.STASH, Location.BACKPACK


def _qty(project: Path, item: str, location: Location = STASH) -> int | None:
    held = load(project / "data").find(Holding, f"{item}@{location}")
    return None if held is None else held.quantity


def _counter(project: Path) -> int:
    return stash_slot_math(load(project / "data")).implied


def test_a_craft_takes_stash_inputs_and_lands_where_it_was_made(project: Path) -> None:
    craft = commands.craft([("Light Ammo", 20)], [("Chemicals", 4), ("Metal Parts", 6)], BACKPACK)
    apply_change(project, craft)
    assert _qty(project, "chemicals") == 86
    assert _qty(project, "metal_parts") == 228
    assert _qty(project, "light_ammo", BACKPACK) == 20  # never recorded there: started at zero
    kinds = {a.kind for a in load(project / "data").all(InventoryAction)}
    assert {ActionKind.CRAFT_INPUT, ActionKind.CRAFT_OUTPUT} <= kinds


def test_the_counter_is_checked_on_the_action_that_changes_it(project: Path) -> None:
    before = snapshot(project / "data")
    expected = _counter(project) - 2  # all 22 Wires: both tiles (15 + 7) empty
    wrong = commands.sell([("Wires", 22)], reading=commands.Reading(stash_used=expected + 1))
    with pytest.raises(commands.Refused, match="records imply"):
        apply_change(project, wrong)
    assert snapshot(project / "data") == before  # refused: nothing written
    right = commands.Reading(stash_used=expected, coins=100_500)
    apply_change(project, commands.sell([("Wires", 22)], reading=right))
    state = load(project / "data")
    assert state.get(AccountMetric, MetricKind.COINS).value == 100_500
    assert _qty(project, "wires") == 0


def test_a_move_nets_to_zero_and_a_piece_moves_with_its_mods(project: Path) -> None:
    apply_change(project, commands.move([("Light Ammo", 20)], STASH, BACKPACK))
    assert (_qty(project, "light_ammo"), _qty(project, "light_ammo", BACKPACK)) == (100, 20)
    moves = [a.quantity for a in load(project / "data").all(InventoryAction)]
    assert sum(moves) == 0
    rattler_before = next(
        i for i in load(project / "data").all(ItemInstance) if i.item.id == "rattler_ii"
    )
    apply_change(project, commands.move([("Rattler II", 1)], Location.EQUIPMENT, STASH))
    state = load(project / "data")
    rattler = state.get(ItemInstance, rattler_before.id)  # the same piece, not a new count
    assert (rattler.location, rattler.condition) == (STASH, rattler_before.condition)
    silencer = next(i for i in state.all(ItemInstance) if i.item.id == "silencer_i")
    assert silencer.location is STASH  # its mods go with it
    with pytest.raises(commands.Refused, match="tracked at"):
        apply_change(project, commands.move([("Rattler II", 1)], Location.EQUIPMENT, STASH))


def test_a_trade_gives_a_piece_away_with_its_mods(project: Path) -> None:
    trade = commands.trade([("Renegade I", 1), ("Hornet Driver", 2)], [("Bobcat I", 1)])
    apply_change(project, trade)
    state = load(project / "data")
    assert not [i for i in state.all(ItemInstance) if i.item.id == "renegade_i"]
    assert not [i for i in state.all(ItemInstance) if i.item.id == "compensator_tier_unknown"]
    assert _qty(project, "hornet_driver") == 6
    assert _qty(project, "bobcat_i") == 1


def test_a_repair_spends_its_cost_and_sets_the_new_durability(project: Path) -> None:
    repair = commands.repair([("Plastic Parts", 4)], commands.set_condition("Renegade I", 100, 100))
    apply_change(project, repair)
    state = load(project / "data")
    renegade = next(i for i in state.all(ItemInstance) if i.item.id == "renegade_i")
    assert (renegade.condition, renegade.condition_max) == (100, 100)
    assert _qty(project, "plastic_parts") == 106


def test_recycle_and_use_from_the_cli(project: Path) -> None:
    base = ["--project", str(project)]
    note = ["--note", "test", "--no-commit"]
    cli.main([*base, "recycle", "Hornet Driver=1", "--into", "Wires=2", *note])
    cli.main([*base, "use", "Medium Ammo=30", *note])
    assert _qty(project, "wires") == 24
    assert _qty(project, "medium_ammo", BACKPACK) == 130
    with pytest.raises(SystemExit):
        cli.main([*base, "use", "Medium Ammo=500", *note])  # more than carried
