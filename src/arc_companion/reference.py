"""Import game reference facts from the RaidTheory community dataset (items/*.json).

Matching is exact: dataset id, dataset name, or one of our aliases equal to the dataset name.
`REVIEWED_MATCHES` holds pairs whose names differ (plural, spelling, numerals); each was
checked by meaning, not produced by a fuzzy matcher. Anything else stays unmatched and is
reported, never guessed.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path

from .enums import ItemCategory, SourceKind
from .model import Alias, Item, ItemValue, Recipe, RecipeInput, Source, StackSize, Station
from .store import State

# our item id -> dataset id
REVIEWED_MATCHES: dict[str, str] = {
    "advanced_arc_power_cell": "advanced_arc_powercell",
    "advanced_electrical_component": "advanced_electrical_components",
    "advanced_mechanical_component": "advanced_mechanical_components",
    "apricots": "apricot",
    "arc_power_cells": "arc_powercell",
    "berletta_i": "burletta_i",
    "combat_mk_i": "combat_mk1",
    "combat_mk_ii": "combat_mk2",
    "dartboard": "dart_board",
    "doc_master_s_detector": "dockmasters_detector",
    "heavy_fuse_grenade": "heavy_fuze_grenade",
    "heavy_gun_part": "heavy_gun_parts",
    "little_smoke_grenade_verify_exact_name": "lil_smoke_grenade",
    "looting_mk_i": "looting_mk1",
    "looting_mk_ii": "looting_mk2",
    "magnets": "magnet",
    "mechanical_component": "mechanical_components",
    "medium_gun_part": "medium_gun_parts",
    "mod_component": "mod_components",
    "natural_wonders_poster": "poster_of_natural_wonders",
    "prickly_pears": "prickly_pear",
    "processors": "processor",
    "regular_bandage": "bandage",
    "rusted_gears": "rusted_gear",
    "sentinel_firing_cores": "sentinel_firing_core",
    "smoke_grenade_trap_unverified": "smoke_grenade_trap",
    "speaker_components": "speaker_component",
    "spotter_relays": "spotter_relay",
    "spring_cushion_unverified": "spring_cushion",
    "steel_springs": "steel_spring",
    "surveyor_vaults": "surveyor_vault",
    "tactical_mk_iii_smoke_blueprint": "tactical_mk3_smoke_blueprint",
    "vitashot": "vita_shot",
}

_WEAPON_TYPES = {
    "Assault Rifle",
    "Battle Rifle",
    "Hand Cannon",
    "LMG",
    "Pistol",
    "SMG",
    "Shotgun",
    "Sniper Rifle",
    "Special",
}
CATEGORIES: dict[str, ItemCategory] = {
    "Ammunition": ItemCategory.AMMUNITION,
    "Augment": ItemCategory.AUGMENT,
    "Basic Material": ItemCategory.BASIC_MATERIAL,
    "Blueprint": ItemCategory.BLUEPRINT,
    "Key": ItemCategory.KEY,
    "Modification": ItemCategory.MOD,
    "Nature": ItemCategory.NATURE,
    "Quick Use": ItemCategory.QUICK_USE,
    "Recyclable": ItemCategory.RECYCLABLE,
    "Refined Material": ItemCategory.REFINED_MATERIAL,
    "Shield": ItemCategory.SHIELD,
    "Topside Material": ItemCategory.TOPSIDE_MATERIAL,
    "Trinket": ItemCategory.TRINKET,
    **{t: ItemCategory.WEAPON for t in _WEAPON_TYPES},
}


@dataclass(frozen=True, slots=True)
class DatasetItem:
    id: str
    name: str
    type: str | None
    stack_size: int | None
    value: int | None = None
    recipe: tuple[tuple[str, int], ...] = ()
    bench: str | None = None
    bench_level: int | None = None
    makes: int = 1


# Dataset bench ids -> station ids here. `in_raid` crafting has no station and is skipped.
BENCHES = {
    "weapon_bench": "gunsmith",
    "equipment_bench": "gear_bench",
    "utility_bench": "utility",
    "explosives_bench": "explosives",
    "med_station": "medical_lab",
    "refiner": "refiner",
    "workbench": "workbench",
}


def _bench(raw: object) -> str | None:
    options = raw if isinstance(raw, list) else [raw]
    return next((b for b in options if isinstance(b, str) and b in BENCHES), None)


def read_dataset(items_dir: Path) -> dict[str, DatasetItem]:
    result = {}
    for path in sorted(items_dir.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        stack = raw.get("stackSize")
        value, level, makes = (
            raw.get("value"),
            raw.get("stationLevelRequired"),
            raw.get("craftQuantity"),
        )
        result[raw["id"]] = DatasetItem(
            id=raw["id"],
            name=raw["name"]["en"],
            type=raw.get("type"),
            stack_size=stack if isinstance(stack, int) else None,
            value=value if isinstance(value, int) else None,
            recipe=tuple(sorted((raw.get("recipe") or {}).items())),
            bench=_bench(raw.get("craftBench")),
            bench_level=level if isinstance(level, int) else None,
            makes=makes if isinstance(makes, int) else 1,
        )
    return result


def _match(state: State, item: Item, dataset: dict[str, DatasetItem]) -> DatasetItem | None:
    if item.id in REVIEWED_MATCHES:
        return dataset.get(REVIEWED_MATCHES[item.id])
    if item.id in dataset:
        return dataset[item.id]
    names = {item.name.casefold()} | {
        a.alias.casefold() for a in state.all(Alias) if a.item == item
    }
    hits = [d for d in dataset.values() if d.name.casefold() in names]
    return hits[0] if len(hits) == 1 else None


@dataclass
class ImportReport:
    stack_sizes: int = 0
    classified: int = 0
    renamed: int = 0
    added: int = 0
    values: int = 0
    recipes: int = 0
    unmatched: list[str] = dataclasses.field(default_factory=list)
    conflicts: list[str] = dataclasses.field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"import-reference: {self.stack_sizes} stack sizes, {self.classified} items "
            f"classified, {self.renamed} renamed to the game name (old name kept as alias), "
            f"{self.added} new items added, {self.values} sale values, "
            f"{self.recipes} recipes",
        ]
        if self.conflicts:
            lines.append("kept existing value, conflicts: " + "; ".join(self.conflicts))
        if self.unmatched:
            lines.append(f"unmatched ({len(self.unmatched)}): " + ", ".join(self.unmatched))
        return "\n".join(lines)


def apply_dataset(
    state: State, source: Source, dataset: dict[str, DatasetItem], *, add_missing: bool = False
) -> ImportReport:
    """Stack sizes, categories for unclassified items, and the game's spelling of names.

    A player-observed stack size is never overwritten; a disagreement is reported instead.
    A category already set is never overwritten either. With `add_missing`, dataset items
    nobody here matches are added as new items, unless their name is already taken.
    """
    report = ImportReport()
    matched: set[str] = set()
    ours: dict[str, Item] = {}  # dataset id -> our item
    known_aliases = {a.alias.casefold() for a in state.all(Alias)}
    owner: dict[str, str] = {i.name.casefold(): i.id for i in state.all(Item)}
    owner |= {a.alias.casefold(): a.item.id for a in state.all(Alias)}
    # Exact-id matches claim their game name before reviewed or name matches can take it.
    for item in sorted(state.all(Item), key=lambda i: i.id not in dataset):
        entry = _match(state, item, dataset)
        if entry is None:
            report.unmatched.append(item.id)
            continue
        matched.add(entry.id)
        ours[entry.id] = item
        if entry.stack_size is not None:
            existing = state.find(StackSize, item.id)
            if existing is not None and existing.source.kind is not SourceKind.WEB_REFERENCE:
                if existing.units_per_slot != entry.stack_size:
                    report.conflicts.append(
                        f"{item.id} stack: player {existing.units_per_slot}, "
                        f"dataset {entry.stack_size}"
                    )
            elif existing is None or existing.units_per_slot != entry.stack_size:
                state.put(StackSize(item=item, units_per_slot=entry.stack_size, source=source))
                report.stack_sizes += 1
        new_category, new_name = item.category, item.name
        category = CATEGORIES.get(entry.type or "")
        if category is not None and category is not item.category:
            if item.category is ItemCategory.UNCLASSIFIED:
                new_category = category
                report.classified += 1
            else:
                report.conflicts.append(f"{item.id} category: ours {item.category}, {entry.type}")
        holder = owner.get(entry.name.casefold(), item.id)
        if entry.name != item.name and holder != item.id:
            report.conflicts.append(f"{item.id} name: {entry.name!r} already names {holder}")
        elif entry.name != item.name:
            new_name = entry.name
            owner[entry.name.casefold()] = item.id
            if item.name.casefold() not in known_aliases:
                state.put(Alias(alias=item.name, item=item))
                known_aliases.add(item.name.casefold())
            report.renamed += 1
        if (new_category, new_name) != (item.category, item.name):
            state.put(dataclasses.replace(item, category=new_category, name=new_name))
    if add_missing:
        for entry in sorted(dataset.values(), key=lambda d: d.id):
            if entry.id in matched or state.find(Item, entry.id) is not None:
                continue
            if (taken := owner.get(entry.name.casefold())) is not None:
                report.conflicts.append(f"not added {entry.id}: {entry.name!r} names {taken}")
                continue
            category = CATEGORIES.get(entry.type or "", ItemCategory.UNCLASSIFIED)
            new = Item(id=entry.id, name=entry.name, category=category, family=None, tier=None)
            state.add(new)
            ours[entry.id] = new
            owner[entry.name.casefold()] = entry.id
            if entry.stack_size is not None:
                state.put(StackSize(item=new, units_per_slot=entry.stack_size, source=source))
            report.added += 1
    for dataset_id, item in ours.items():
        entry = dataset[dataset_id]
        _import_value(state, item, entry, source, report)
        _import_recipe(state, item, entry, ours=ours, source=source, report=report)
    return report


def _import_value(
    state: State, item: Item, entry: DatasetItem, source: Source, report: ImportReport
) -> None:
    """A sale value only where none is recorded: any recorded value (player, wiki) wins."""
    if entry.value is None or state.find(ItemValue, item.id) is not None:
        return
    state.add(ItemValue(item=item, coins=entry.value, source=source))
    report.values += 1


def _import_recipe(
    state: State,
    item: Item,
    entry: DatasetItem,
    *,
    ours: dict[str, Item],
    source: Source,
    report: ImportReport,
) -> None:
    """A recipe for an item that has none yet. Recipes recorded here (wiki or player) win."""
    if not entry.recipe or entry.bench is None or state.find(Recipe, item.id) is not None:
        return
    inputs = [(ours.get(dataset_id), quantity) for dataset_id, quantity in entry.recipe]
    station = state.find(Station, BENCHES[entry.bench])
    if station is None or any(i is None for i, _ in inputs):
        return
    recipe = Recipe(
        id=item.id,
        output=item,
        output_quantity=entry.makes,
        station=station,
        required_level=entry.bench_level,
        source=source,
    )
    state.add(recipe)
    for ingredient, quantity in inputs:
        assert ingredient is not None
        state.add(RecipeInput(recipe=recipe, item=ingredient, quantity=quantity))
    report.recipes += 1


SCRAPPY_WIKI = (
    "https://arcraiders.wiki/wiki/Scrappy (modified 2026-10-12; level 4 values marked accurate "
    "as of Update 1.31.0)"
)
# (level, more than N minutes in round, not extracted: material, seeds, extracted: material, seeds)
SCRAPPY_RATES: tuple[tuple[int, int, int, int, int, int], ...] = (
    (1, 1, 5, 3, 3, 3),
    (1, 6, 9, 4, 4, 4),
    (1, 15, 12, 5, 6, 5),
    (2, 1, 5, 3, 3, 3),
    (2, 6, 10, 5, 5, 5),
    (2, 15, 13, 7, 7, 7),
    (3, 1, 5, 3, 3, 3),
    (3, 6, 11, 6, 6, 6),
    (3, 15, 14, 9, 7, 9),
    (4, 1, 6, 3, 3, 3),
    (4, 6, 12, 7, 5, 7),
    (4, 15, 15, 11, 8, 11),
    (5, 1, 5, 3, 3, 3),
    (5, 6, 13, 8, 8, 8),
    (5, 15, 16, 13, 8, 13),
)
# Each eaten food adds a flat +5 of one material (wiki: Scrappy, Feeding Boost).
SCRAPPY_FOODS: dict[str, str] = {
    "agave": "assorted_seeds",
    "apricots": "metal_parts",
    "lemon": "chemicals",
    "mushroom": "plastic_parts",
    "olives": "fabric",
    "prickly_pears": "rubber_parts",
}
FOOD_BONUS = 5
FEED_QUEUE = 6


AUGMENTS_WIKI = (
    "https://arcraiders.wiki/wiki/Augments (2.0 notes list no slot changes); Looting Mk. 2 "
    "confirmed in game 2026-10-23: 22 backpack, 4 quick use, 2 safe pocket, weight 60"
)
# (item id, weight limit, backpack slots, quick use slots, safe pocket slots)
AUGMENTS: tuple[tuple[str, int, int, int, int], ...] = (
    ("free_loadout_augment", 35, 14, 4, 0),
    ("looting_mk_i", 50, 18, 4, 1),
    ("looting_mk_ii", 60, 22, 4, 2),
    ("looting_mk3_cautious", 70, 24, 5, 2),
    ("looting_mk3_safekeeper", 65, 18, 4, 1),
    ("looting_mk3_survivor", 80, 20, 5, 3),
    ("combat_mk_i", 45, 16, 4, 1),
    ("combat_mk_ii", 55, 18, 4, 1),
    ("tactical_mk1", 40, 15, 5, 1),
    ("tactical_mk2", 45, 17, 5, 1),
)
