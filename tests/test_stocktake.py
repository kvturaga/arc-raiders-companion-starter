from __future__ import annotations

from pathlib import Path

import pytest

from arc_companion import commands
from arc_companion.commands import CountLine, parse_stacks
from arc_companion.enums import ActionKind, ItemCategory, Location
from arc_companion.model import (
    Holding,
    InventoryAction,
    Item,
    ItemInstance,
    Reservation,
    StashCounter,
    UnreconciledHolding,
    WeaponAttachment,
)
from arc_companion.queries import balance, resolve, stash_after
from arc_companion.store import load

from .conftest import apply_change

STASH = Location.STASH


def _reserved(project: Path, skip: str = "") -> list[CountLine]:
    """Stash lines for every reserved item, so a partial test count keeps reservations valid."""
    totals: dict[str, int] = {}
    for r in load(project / "data").all(Reservation):
        totals[r.item.id] = totals.get(r.item.id, 0) + r.quantity
    return [CountLine(STASH, item, (qty,)) for item, qty in totals.items() if item != skip]


def test_parse_stacks_expands_repeats() -> None:
    assert parse_stacks("50x4+43") == (50, 50, 50, 50, 43)
    assert parse_stacks("3") == (3,)
    with pytest.raises(commands.Refused):
        parse_stacks("5+0")


def test_stash_tiles_must_reproduce_the_counter(project: Path) -> None:
    lines = [CountLine(STASH, "Metal Parts", (50, 50, 43))]
    with pytest.raises(commands.Refused, match="counted 3, counter shows 4"):
        apply_change(project, commands.stocktake(lines, stash_used=4))
    with pytest.raises(commands.Refused, match="stash-used"):
        commands.stocktake(lines, stash_used=None)


def test_a_complete_stash_count_zeroes_what_was_not_seen(project: Path) -> None:
    lines = [
        CountLine(STASH, "Metal Parts", (50, 50, 50, 50, 43)),
        CountLine(STASH, "Burletta I", (1,)),
    ]
    summary = apply_change(project, commands.stocktake(lines, stash_used=6))
    state = load(project / "data")
    metal = state.get(Holding, "metal_parts@stash")
    assert (metal.quantity, metal.slots) == (243, 5)
    assert state.get(Holding, "chemicals@stash").quantity == 0  # recorded zero, not deleted
    assert state.all(StashCounter)[0].used == 6
    # The Renegade was tracked in the stash but not seen: removed with its mods, and reported.
    assert "renegade_i" in summary
    assert not [i for i in state.all(ItemInstance) if i.item.id == "renegade_i"]
    assert not [i for i in state.all(ItemInstance) if i.item.id == "extended_medium_mag_i"]
    # Carried slots were not counted, so the Rattler and its mods are untouched.
    assert [i for i in state.all(ItemInstance) if i.item.id == "silencer_i"]


def test_counting_every_carried_slot_closes_unreconciled_rows(legacy_project: Path) -> None:
    lines = [
        *_reserved(legacy_project),
        CountLine(Location.BACKPACK, "Medium Ammo", (80, 80, 72)),
        CountLine(Location.QUICK_USE, "Regular Bandage", (4,)),
        CountLine(Location.SAFE_POCKET, "Grappling Hook", (1,)),
        CountLine(Location.SAFE_POCKET, "Photoelectric Cloak", (1,)),
        CountLine(Location.EQUIPMENT, "Rattler II", (1,), condition=(103, 110)),
        CountLine(Location.EQUIPMENT, "Looting Mk. II", (1,), condition=(100, 100)),
    ]
    used = sum(len(line.stacks) for line in lines if line.location is STASH)
    apply_change(legacy_project, commands.stocktake(lines, stash_used=used))
    state = load(legacy_project / "data")
    assert not state.all(UnreconciledHolding)
    assert state.get(Holding, "medium_ammo@carried").quantity == 0
    assert balance(state, state.get(Item, "medium_ammo")).confirmed == 232
    rattler = next(i for i in state.all(ItemInstance) if i.item.id == "rattler_ii")
    assert (rattler.condition, rattler.condition_max) == (103, 110)
    # A durability reading on an untracked unit turns it into a tracked piece.
    looting = next(i for i in state.all(ItemInstance) if i.item.id == "looting_mk_ii")
    assert (looting.condition, looting.location) == (100, Location.EQUIPMENT)
    assert state.get(Holding, "looting_mk_ii@equipment").quantity == 0


def test_counting_one_location_keeps_the_pieces_seen_there(project: Path) -> None:
    lines = [
        CountLine(Location.SAFE_POCKET, "Grappling Hook", (1,)),
        CountLine(Location.SAFE_POCKET, "Photoelectric Cloak", (1,)),
    ]
    apply_change(project, commands.stocktake(lines, stash_used=None))
    state = load(project / "data")
    assert len([i for i in state.all(ItemInstance) if i.location is Location.SAFE_POCKET]) == 2


def test_a_stash_count_settles_never_recorded_goal_items_as_zero(project: Path) -> None:
    apply_change(project, commands.add_item("rare_find", "Rare Find", ItemCategory.TRINKET, None))
    apply_change(project, commands.add_goal("collect", "Collect", None, {"Rare Find": 2}, []))
    assert load(project / "data").find(Holding, "rare_find@stash") is None  # unobserved
    lines = [CountLine(STASH, "Metal Parts", (50,))]
    apply_change(project, commands.stocktake(lines, stash_used=1))
    assert load(project / "data").get(Holding, "rare_find@stash").quantity == 0  # proven zero


def test_a_tracked_weapon_that_moved_keeps_its_mods(project: Path) -> None:
    before = load(project / "data")
    rattler = next(i for i in before.all(ItemInstance) if i.item.id == "rattler_ii")
    assert rattler.location is Location.EQUIPMENT
    lines = [*_reserved(project), CountLine(STASH, "Rattler II", (1,))]
    lines.append(CountLine(Location.EQUIPMENT, "Looting Mk. II", (1,)))
    apply_change(
        project, commands.stocktake(lines, stash_used=sum(len(x.stacks) for x in lines) - 1)
    )
    after = load(project / "data")
    moved = after.get(ItemInstance, rattler.id)  # same piece, not a new one
    assert moved.location is Location.STASH
    mods = [a.mod for a in after.all(WeaponAttachment) if a.weapon.id == rattler.id]
    assert mods
    assert {m.location for m in mods} == {Location.STASH}


def test_a_carried_stocktake_with_no_changes_keeps_every_count(project: Path) -> None:
    state = load(project / "data")
    before = {h.id: h.quantity for h in state.all(Holding) if h.location is STASH and h.quantity}
    lines = commands.carried_stash(state, stash_after(state, {}, {}))
    summary = apply_change(
        project, commands.stocktake(lines, stash_used=sum(len(x.stacks) for x in lines))
    )
    after = {
        h.id: h.quantity
        for h in load(project / "data").all(Holding)
        if h.location is STASH and h.quantity
    }
    assert after == before
    assert "removed" not in summary


def test_a_carried_raid_records_its_events_and_leaves_no_residual(project: Path) -> None:
    state = load(project / "data")
    add, sold = {resolve(state, "Metal Parts"): 15}, {resolve(state, "Wires"): 2}
    lines = commands.carried_stash(state, stash_after(state, add, sold))
    events = ((ActionKind.LOOT, "Metal Parts", 15), (ActionKind.SELL, "Wires", 2))
    used = sum(len(x.stacks) for x in lines)
    summary = apply_change(project, commands.stocktake(lines, used, events))
    assert "residual" not in summary
    kinds = {(a.kind, a.item.id, a.quantity) for a in load(project / "data").all(InventoryAction)}
    assert (ActionKind.LOOT, "metal_parts", 15) in kinds
    assert (ActionKind.SELL, "wires", 2) in kinds


def test_a_count_that_disagrees_with_records_names_the_item(project: Path) -> None:
    state = load(project / "data")
    lines = commands.carried_stash(state, stash_after(state, {}, {}))
    light = next(x for x in lines if x.item == "light_ammo")
    lines[lines.index(light)] = CountLine(STASH, "light_ammo", (100, 28))  # 8 more than recorded
    summary = apply_change(project, commands.stocktake(lines, sum(len(x.stacks) for x in lines)))
    assert "light_ammo +8" in summary
    residual = [
        a for a in load(project / "data").all(InventoryAction) if a.kind is ActionKind.RESIDUAL
    ]
    assert [(a.item.id, a.quantity) for a in residual] == [("light_ammo", 8)]


def test_a_death_loses_every_carried_slot_but_the_safe_pocket(project: Path) -> None:
    before = load(project / "data")
    stash = {h.id: h.quantity for h in before.all(Holding) if h.location is Location.STASH}
    summary = apply_change(project, commands.record_death())
    after = load(project / "data")
    lost = (Location.EQUIPMENT, Location.BACKPACK, Location.QUICK_USE)
    assert not [h for h in after.all(Holding) if h.location in lost and h.quantity]
    assert not [i for i in after.all(ItemInstance) if i.location in lost]
    # The Rattler's mods went down with it; the Renegade's stay on it in the stash.
    assert {a.weapon.item.id for a in after.all(WeaponAttachment)} == {"renegade_i"}
    pocket = {i.item.id for i in after.all(ItemInstance) if i.location is Location.SAFE_POCKET}
    assert pocket == {"grappling_hook", "photoelectric_cloak"}
    assert {h.id: h.quantity for h in after.all(Holding) if h.location is Location.STASH} == stash
    losses = {
        a.item.id: a.quantity for a in after.all(InventoryAction) if a.kind is ActionKind.LOSS
    }
    assert losses["medium_ammo"] == 160
    assert "rattler_ii 1" in summary
