from __future__ import annotations

import json
from pathlib import Path

import pytest

from arc_companion import commands
from arc_companion.enums import ItemCategory, Location, SourceKind
from arc_companion.model import Item, ItemValue, Recipe, RecipeInput, StackSize
from arc_companion.queries import resolve, slots_needed, stash_slot_math
from arc_companion.reference import read_dataset
from arc_companion.store import load

from .conftest import apply_change


def _dataset(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    items = tmp_path / "items"
    items.mkdir()
    for row in rows:
        (items / f"{row['id']}.json").write_text(json.dumps(row))
    return items


def _row(id: str, name: str, type: str, stack: int) -> dict[str, object]:
    return {"id": id, "name": {"en": name}, "type": type, "stackSize": stack}


@pytest.mark.parametrize(
    ("quantity", "units", "slots"), [(1, 1, 1), (120, 100, 2), (240, 60, 4), (7, 3, 3), (15, 24, 1)]
)
def test_slots_needed_rounds_up(quantity: int, units: int, slots: int) -> None:
    assert slots_needed(quantity, units) == slots


def test_player_stack_sizes_are_recorded_as_user_reports(project: Path) -> None:
    apply_change(project, commands.set_stack_sizes({"Light Ammo": 100, "Zipline": 3}))
    state = load(project / "data")
    stack = state.get(StackSize, "light_ammo")
    assert stack.units_per_slot == 100
    assert stack.source.kind is SourceKind.USER_REPORT


def test_a_stack_size_below_one_is_refused(project: Path) -> None:
    with pytest.raises(commands.Refused, match="at least one"):
        commands.set_stack_sizes({"Zipline": 0})


def test_a_slot_count_too_small_for_the_stack_size_is_refused(project: Path) -> None:
    apply_change(project, commands.set_stack_sizes({"Light Ammo": 100}))
    with pytest.raises(commands.Refused, match="stack_physics"):
        apply_change(project, commands.set_count("Light Ammo", Location.STASH, 120, slots=1))
    apply_change(project, commands.set_count("Light Ammo", Location.STASH, 120, slots=2))


def test_more_slots_than_units_is_refused(project: Path) -> None:
    with pytest.raises(commands.Refused, match="stack_physics"):
        apply_change(project, commands.set_count("Zipline", Location.STASH, 1, slots=2))


def test_import_matches_exactly_and_by_reviewed_pairs(legacy_project: Path, tmp_path: Path) -> None:
    dataset = read_dataset(
        _dataset(
            tmp_path,
            [
                _row("zipline", "Zipline", "Quick Use", 3),  # same id
                _row("heavy_fuze_grenade", "Heavy Fuze Grenade", "Quick Use", 3),  # reviewed
                _row("burletta_i", "Burletta I", "Pistol", 1),  # reviewed, misspelt here
                _row("unrelated", "Something Else", "Trinket", 5),
            ],
        )
    )
    summary = apply_change(
        legacy_project, commands.import_reference(dataset), SourceKind.WEB_REFERENCE
    )
    state = load(legacy_project / "data")
    assert state.get(StackSize, "zipline").units_per_slot == 3
    assert state.get(StackSize, "heavy_fuse_grenade").source.kind is SourceKind.WEB_REFERENCE
    fuze = state.get(Item, "heavy_fuse_grenade")
    assert fuze.name == "Heavy Fuze Grenade"
    assert fuze.category is ItemCategory.QUICK_USE
    # The old spelling still resolves: renaming keeps it as an alias.
    assert resolve(state, "Heavy Fuse Grenade") == fuze
    assert resolve(state, "Berletta I").id == "berletta_i"
    assert "unmatched" in summary


def test_import_never_overwrites_a_player_observation(project: Path, tmp_path: Path) -> None:
    apply_change(project, commands.set_stack_sizes({"Zipline": 3}))
    dataset = read_dataset(_dataset(tmp_path, [_row("zipline", "Zipline", "Quick Use", 5)]))
    summary = apply_change(project, commands.import_reference(dataset), SourceKind.WEB_REFERENCE)
    state = load(project / "data")
    assert state.get(StackSize, "zipline").units_per_slot == 3
    assert "player 3, dataset 5" in summary


def test_import_must_be_sourced_as_a_web_reference(project: Path, tmp_path: Path) -> None:
    dataset = read_dataset(_dataset(tmp_path, [_row("zipline", "Zipline", "Quick Use", 3)]))
    with pytest.raises(commands.Refused, match="web_reference"):
        apply_change(project, commands.import_reference(dataset))


def test_slot_math_counts_only_fully_known_stacks(project: Path) -> None:
    math = stash_slot_math(load(project / "data"))
    assert math.complete  # every demo stash item has a stack size
    apply_change(project, commands.set_count("Light Ammo", Location.STASH, 201))
    assert stash_slot_math(load(project / "data")).implied == math.implied + 1  # 3 stacks, not 2
    apply_change(project, commands.add_item("odd_thing", "Odd Thing", ItemCategory.TRINKET, None))
    apply_change(project, commands.set_count("Odd Thing", Location.STASH, 4))
    unknown = stash_slot_math(load(project / "data"))
    assert not unknown.complete  # a stack size is unknown, so the counter cannot be checked
    assert [i.id for i in unknown.without_stack_size] == ["odd_thing"]


def test_import_never_renames_onto_a_name_another_item_holds(
    legacy_project: Path, tmp_path: Path
) -> None:
    # Both legacy items exist; the reviewed match would give the second the first one's name.
    dataset = read_dataset(
        _dataset(tmp_path, [_row("lil_smoke_grenade", "Li'l Smoke Grenade", "Quick Use", 5)])
    )
    summary = apply_change(
        legacy_project, commands.import_reference(dataset), SourceKind.WEB_REFERENCE
    )
    state = load(legacy_project / "data")
    assert "already names lil_smoke_grenade" in summary
    assert state.get(Item, "little_smoke_grenade_verify_exact_name").name != "Li'l Smoke Grenade"


def test_add_missing_brings_in_the_rest_of_the_catalog(project: Path, tmp_path: Path) -> None:
    dataset = read_dataset(
        _dataset(
            tmp_path,
            [
                _row("toaster", "Toaster", "Recyclable", 3),
                # Unmatched, but the name is an existing item's: never added as a second item.
                _row("fuse_clone", "Heavy Fuse Grenade", "Quick Use", 3),
            ],
        )
    )
    change = commands.import_reference(dataset, add_missing=True)
    summary = apply_change(project, change, SourceKind.WEB_REFERENCE)
    state = load(project / "data")
    toaster = state.get(Item, "toaster")
    assert toaster.category is ItemCategory.RECYCLABLE
    assert state.get(StackSize, "toaster").units_per_slot == 3
    assert state.find(Item, "fuse_clone") is None
    assert "not added fuse_clone" in summary


def test_values_and_recipes_come_in_without_overwriting_ours(project: Path, tmp_path: Path) -> None:
    motion = _row("arc_motion_core", "ARC Motion Core", "Topside Material", 5)
    motion |= {"value": 1000, "recipe": {"arc_alloy": 8}, "craftBench": "refiner"}
    motion["stationLevelRequired"] = 2
    alloy = _row("arc_alloy", "ARC Alloy", "Topside Material", 15) | {"value": 200}
    wasp = _row("wasp_driver", "Wasp Driver", "Recyclable", 3) | {"value": 999}
    dataset = read_dataset(_dataset(tmp_path, [motion, alloy, wasp]))
    apply_change(project, commands.import_reference(dataset), SourceKind.WEB_REFERENCE)
    state = load(project / "data")
    assert state.get(ItemValue, "arc_alloy").coins == 200
    assert state.get(ItemValue, "wasp_driver").coins == 640  # the wiki value already recorded
    recipe = state.get(Recipe, "arc_motion_core")
    assert (recipe.station.id if recipe.station else None, recipe.required_level) == ("refiner", 2)
    assert [(i.item.id, i.quantity) for i in state.all(RecipeInput) if i.recipe == recipe] == [
        ("arc_alloy", 8)
    ]
