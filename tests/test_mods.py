"""Tracked pieces and their mods, on the demo player (tests/demo.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from arc_companion import commands
from arc_companion.enums import ItemCategory, Location, ModSlot, WeaponType
from arc_companion.model import (
    Holding,
    Item,
    ItemInstance,
    ModFit,
    WeaponAttachment,
    WeaponProfile,
)
from arc_companion.store import State, load

from .conftest import apply_change


def _piece(state: State, item_id: str) -> ItemInstance:
    return next(i for i in state.all(ItemInstance) if i.item.id == item_id)


def _mods_on(project: Path, item_id: str) -> dict[ModSlot, str]:
    state = load(project / "data")
    weapon = _piece(state, item_id)
    return {a.slot: a.mod.item.id for a in state.all(WeaponAttachment) if a.weapon == weapon}


def test_a_mod_seen_on_a_weapon_is_attached(project: Path) -> None:
    apply_change(project, commands.attach_mod("Renegade I", "Stable Stock II", ModSlot.STOCK))
    mods = _mods_on(project, "renegade_i")
    assert mods[ModSlot.STOCK] == "stable_stock_ii"
    assert mods[ModSlot.MUZZLE] == "compensator_tier_unknown"  # existing mods untouched


def test_an_occupied_slot_is_refused(project: Path) -> None:
    with pytest.raises(commands.Refused, match="already holds"):
        apply_change(project, commands.attach_mod("Renegade I", "Silencer I", ModSlot.MUZZLE))


def test_a_weapon_without_a_profile_needs_its_type(project: Path) -> None:
    apply_change(project, commands.add_item("test_pistol", "Test Pistol", ItemCategory.WEAPON, 1))
    apply_change(project, commands.set_count("Test Pistol", Location.STASH, 1, slots=1))
    change = commands.attach_mod("Test Pistol", "Extended Light Mag I", ModSlot.MAGAZINE)
    with pytest.raises(commands.Refused, match="weapon-type"):
        apply_change(project, change)
    typed = commands.attach_mod(
        "Test Pistol", "Extended Light Mag I", ModSlot.MAGAZINE, WeaponType.PISTOL
    )
    apply_change(project, typed)
    state = load(project / "data")
    assert state.get(WeaponProfile, "test_pistol").weapon_type is WeaponType.PISTOL
    # The observation is the source for the fit.
    assert state.get(ModFit, ("extended_light_mag_i", "test_pistol")).slot is ModSlot.MAGAZINE


def test_a_counted_weapon_becomes_a_tracked_piece_with_its_mod(project: Path) -> None:
    change = commands.attach_mod("Burletta I", "Extended Light Mag I", ModSlot.MAGAZINE)
    apply_change(project, change)
    state = load(project / "data")
    gun = _piece(state, "berletta_i")
    assert gun.location is Location.STASH
    assert state.get(Holding, "berletta_i@stash").quantity == 0  # the unit moved, not copied
    assert state.get(Holding, "extended_light_mag_i@stash").quantity == 0  # the mod's tile too
    assert _mods_on(project, "berletta_i") == {ModSlot.MAGAZINE: "extended_light_mag_i"}


def test_adding_an_item_with_a_taken_name_or_id_is_refused(project: Path) -> None:
    with pytest.raises(commands.Refused, match="unique_names"):
        apply_change(
            project, commands.add_item("zipline_2", "Zipline", ItemCategory.QUICK_USE, None)
        )
    with pytest.raises(commands.Refused, match="already exists"):
        apply_change(project, commands.add_item("zipline", "Zip", ItemCategory.QUICK_USE, None))


def test_a_detached_mod_becomes_its_own_tile_by_the_weapon(project: Path) -> None:
    apply_change(project, commands.detach_mod("Renegade I", ModSlot.MUZZLE))
    assert ModSlot.MUZZLE not in _mods_on(project, "renegade_i")
    state = load(project / "data")
    loose = _piece(state, "compensator_tier_unknown")
    assert loose.location is Location.STASH
    with pytest.raises(commands.Refused, match="no mod"):
        apply_change(project, commands.detach_mod("Renegade I", ModSlot.MUZZLE))


def test_an_upgrade_keeps_the_piece_and_its_mods(project: Path) -> None:
    state = load(project / "data")
    rattler = _piece(state, "rattler_ii")
    metal = state.get(Holding, "metal_parts@stash").quantity or 0
    change = commands.upgrade_piece("Rattler II", "Rattler III", {"Metal Parts": 10}, (120, 120))
    apply_change(project, change)
    after = load(project / "data")
    piece = after.get(ItemInstance, rattler.id)
    assert piece.item == after.get(Item, "rattler_iii")
    assert (piece.condition, piece.condition_max) == (120, 120)
    assert len(_mods_on(project, "rattler_iii")) == 3  # mods stay on the upgraded weapon
    assert after.get(Holding, "metal_parts@stash").quantity == metal - 10
