"""Reference layer: game facts, each sourced (items, recipes, stack sizes, augments, enemies)."""

from __future__ import annotations

from dataclasses import dataclass

from ..enums import (
    Basis,
    BlueprintState,
    ItemCategory,
    MatchupRole,
    ModSlot,
    Penetration,
    WeaponType,
)
from .base import (
    Entity,
    Source,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ItemFamily(Entity):
    """Variants of one item line (Rattler I..IV). Only families with 2+ members exist."""

    TABLE = "item_families"
    id: str
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Item(Entity):
    TABLE = "items"
    id: str
    name: str
    category: ItemCategory
    family: ItemFamily | None
    tier: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Alias(Entity):
    """Exact spoken/written name for an item; matched case-insensitively, never fuzzily."""

    TABLE = "aliases"
    KEY = ("alias",)
    alias: str
    item: Item


@dataclass(frozen=True, slots=True, kw_only=True)
class Station(Entity):
    TABLE = "stations"
    id: str
    name: str
    level: int
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class Recipe(Entity):
    TABLE = "recipes"
    id: str
    output: Item
    output_quantity: int
    station: Station | None
    required_level: int | None
    source: Source

    @property
    def unlocked(self) -> bool | None:
        if self.station is None or self.required_level is None:
            return None
        return self.station.level >= self.required_level


@dataclass(frozen=True, slots=True, kw_only=True)
class RecipeInput(Entity):
    """Shares its recipe's source."""

    TABLE = "recipe_inputs"
    KEY = ("recipe", "item")
    recipe: Recipe
    item: Item
    quantity: int


@dataclass(frozen=True, slots=True, kw_only=True)
class RecycleYield(Entity):
    TABLE = "recycle_yields"
    KEY = ("item", "output")
    item: Item
    output: Item
    quantity: int
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class ItemValue(Entity):
    TABLE = "item_values"
    KEY = ("item",)
    item: Item
    coins: int
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class StackSize(Entity):
    """Units of one item that fit in one slot. A player observation outranks a dataset row."""

    TABLE = "stack_sizes"
    KEY = ("item",)
    item: Item
    units_per_slot: int
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class AugmentCapacity(Entity):
    """What an augment lets a player carry. The equipped augment sets hard loadout limits."""

    TABLE = "augment_capacities"
    KEY = ("item",)
    item: Item
    backpack_slots: int
    quick_use_slots: int
    safe_pocket_slots: int
    weight_limit: int | None
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class ScrappyRate(Entity):
    TABLE = "scrappy_rates"
    KEY = ("level", "min_minutes_exclusive", "extracted")
    level: int
    min_minutes_exclusive: int
    extracted: bool
    material_quantity: int
    seed_quantity: int
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class WeaponProfile(Entity):
    TABLE = "weapon_profiles"
    KEY = ("item",)
    item: Item
    weapon_type: WeaponType


@dataclass(frozen=True, slots=True, kw_only=True)
class ModFit(Entity):
    TABLE = "mod_fits"
    KEY = ("mod", "weapon")
    mod: Item
    weapon: Item
    slot: ModSlot
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class CombatWeapon(Entity):
    """Listed damage is the sourced card value, not damage to any particular ARC part."""

    TABLE = "combat_weapons"
    KEY = ("item",)
    item: Item
    ammo: Item
    penetration: Penetration
    listed_damage: int | None
    magazine: int | None
    blueprint: BlueprintState
    handling: str
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class GameMap(Entity):
    TABLE = "maps"
    id: str
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Enemy(Entity):
    TABLE = "enemies"
    id: str
    name: str
    drop: Item | None
    weak_point: str | None
    tactic: str | None
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class EnemyPart(Entity):
    TABLE = "enemy_parts"
    id: str
    enemy: Enemy
    name: str
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class Matchup(Entity):
    TABLE = "matchups"
    KEY = ("weapon", "enemy")
    weapon: Item
    enemy: Enemy
    role: MatchupRole
    basis: Basis
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class MapEncounter(Entity):
    """A documented possible location, not a spawn guarantee."""

    TABLE = "map_encounters"
    KEY = ("game_map", "enemy", "location")
    game_map: GameMap
    enemy: Enemy
    location: str
    source: Source
