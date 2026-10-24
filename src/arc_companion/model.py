"""Typed entities. Each class is one CSV table; entity-typed fields are object references.

Conventions enforced by `store.py`:
- A field typed as another entity is stored as a `<field>_id` column and resolved on load;
  an unknown id is a load error, never a silent None.
- `X | None` means unobserved. `0` is a recorded zero. They are never interchangeable.
- `KEY` names the fields forming the identity; duplicates are a load error.
- Children point at parents (RecipeInput -> Recipe); `State` builds reverse indexes.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import ClassVar

from .enums import (
    ActionKind,
    Basis,
    BlueprintState,
    Confidence,
    DispositionAction,
    FeedStatus,
    GoalStatus,
    IntentStatus,
    ItemCategory,
    Location,
    MatchupRole,
    MetricKind,
    ModSlot,
    ObjectiveKind,
    Penetration,
    PreferenceKey,
    QuestionStatus,
    RaidLineKind,
    RaidStatus,
    RewardBatchStatus,
    SourceKind,
    TransactionStatus,
    UnreconciledReason,
    WeaponType,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class Entity:
    TABLE: ClassVar[str]
    KEY: ClassVar[tuple[str, ...]] = ("id",)


# --- Provenance -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class Source(Entity):
    """Where a fact came from. `seq` is the proven write order (append order of sources)."""

    TABLE = "sources"
    id: str
    seq: int
    kind: SourceKind
    observed_on: dt.date
    reference: str


# --- Reference: game facts -------------------------------------------------------------------


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


# --- Save state: account and build -----------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class StashCounter(Entity):
    """The in-game slot counter. Authoritative on its own; never derived from item rows."""

    TABLE = "stash_counter"
    id: str
    used: int
    capacity: int
    confidence: Confidence
    source: Source

    @property
    def free(self) -> int:
        return self.capacity - self.used


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountMetric(Entity):
    TABLE = "account_metrics"
    id: MetricKind
    value: int
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class Preference(Entity):
    """A player choice, not a game fact. Booleans are stored as 0/1."""

    TABLE = "preferences"
    id: PreferenceKey
    value: int
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class PlayerBuild(Entity):
    TABLE = "player_build"
    id: str
    level: int
    mobility_points: int | None
    conditioning_points: int | None
    unspent_points: int
    survival_points: int | None = None
    reset_cost_coins: int | None
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class SkillRank(Entity):
    TABLE = "skill_ranks"
    id: str
    name: str
    rank: int | None
    maximum: int | None
    confidence: Confidence
    source: Source
    note: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Feat(Entity):
    TABLE = "feats"
    id: str
    description: str
    progress: int | None
    required: int | None
    reward_points: int | None
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class RewardGap(Entity):
    TABLE = "reward_gaps"
    id: str
    name: str
    points_remaining: int
    source: Source


# --- Save state: inventory -------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class Holding(Entity):
    """A fungible stack: one row per (item, location). Quantity None = not counted."""

    TABLE = "holdings"
    id: str
    item: Item
    location: Location
    quantity: int | None
    slots: int | None
    confidence: Confidence
    source: Source
    note: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ItemInstance(Entity):
    """One physical weapon/mod/gear piece tracked individually (condition, attachments)."""

    TABLE = "item_instances"
    id: str
    item: Item
    location: Location
    condition: int | None
    condition_max: int | None
    condition_source: Source | None
    confidence: Confidence
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class WeaponAttachment(Entity):
    TABLE = "weapon_attachments"
    KEY = ("mod",)
    weapon: ItemInstance
    mod: ItemInstance
    slot: ModSlot
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class RaidReport(Entity):
    TABLE = "raid_reports"
    id: str
    status: RaidStatus
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class RaidLine(Entity):
    """Receipt history. `legacy_holding_id` is provenance into the frozen legacy copy only."""

    TABLE = "raid_lines"
    id: str
    report: RaidReport
    item: Item
    kind: RaidLineKind
    quantity: int
    legacy_holding_id: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class UnreconciledHolding(Entity):
    """Recorded quantity whose physical location is not established.

    Excluded from confirmed totals and from planning. Resolved only by a live count
    (`arc reconcile`) or a confirmed unload. Whether a later stash count already absorbed
    it is computed from `Source.seq`, never stored.
    """

    TABLE = "unreconciled_holdings"
    id: str
    item: Item
    claimed_location: Location
    quantity: int | None
    reason: UnreconciledReason
    raid_report: RaidReport | None
    source: Source
    legacy_holding_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RaidIntent(Entity):
    TABLE = "raid_intents"
    id: str
    objective: str
    item: Item | None
    status: IntentStatus
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class InventoryAction(Entity):
    """A confirmed thing that happened (sale, recycle, craft). History, never replayed."""

    TABLE = "inventory_actions"
    id: str
    kind: ActionKind
    item: Item
    quantity: int
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class Transaction(Entity):
    TABLE = "transactions"
    id: str
    recipe: Recipe | None
    batches: int
    status: TransactionStatus
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class LoadoutTarget(Entity):
    """A plan. Never alters ownership."""

    TABLE = "loadout_targets"
    KEY = ("item", "location")
    item: Item
    location: Location
    quantity: int
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class PlannedSale(Entity):
    TABLE = "planned_sales"
    id: str
    item: Item
    quantity: int
    unit_coins: int
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class DispositionRule(Entity):
    TABLE = "disposition_rules"
    KEY = ("item",)
    item: Item
    action: DispositionAction
    keep_total: int
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkbookPolicy(Entity):
    """Imported spreadsheet note. Reference only; not an active rule or recommendation."""

    TABLE = "workbook_policies"
    KEY = ("item",)
    item: Item
    keep_minimum: int | None
    decision: str
    source: Source


# --- Goals -----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class Goal(Entity):
    TABLE = "goals"
    id: str
    name: str
    status: GoalStatus
    priority: int | None
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class GoalRequirement(Entity):
    """Shares its goal's source."""

    TABLE = "goal_requirements"
    KEY = ("goal", "item")
    goal: Goal
    item: Item
    quantity: int


@dataclass(frozen=True, slots=True, kw_only=True)
class GoalDependency(Entity):
    TABLE = "goal_dependencies"
    KEY = ("goal", "prerequisite")
    goal: Goal
    prerequisite: Goal


@dataclass(frozen=True, slots=True, kw_only=True)
class Reservation(Entity):
    TABLE = "reservations"
    KEY = ("goal", "item")
    goal: Goal
    item: Item
    quantity: int
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectContribution(Entity):
    """Items irretrievably submitted to a project. Never added back to inventory."""

    TABLE = "project_contributions"
    KEY = ("goal", "item")
    goal: Goal
    item: Item
    quantity: int
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class Objective(Entity):
    """Quest step. The target is a typed reference chosen by `kind`; see checks."""

    TABLE = "objectives"
    id: str
    goal: Goal
    kind: ObjectiveKind
    required: int
    progress: int | None
    enemy: Enemy | None
    enemy_part: EnemyPart | None
    item: Item | None
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenQuestion(Entity):
    """Something only the player can answer. `topic` is prose by nature; links are typed."""

    TABLE = "open_questions"
    id: str
    topic: str
    status: QuestionStatus
    raid_report: RaidReport | None
    source: Source
    resolution: Source | None


# --- Scrappy ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class Companion(Entity):
    TABLE = "companions"
    id: str
    name: str
    level: int
    round_capacity: int
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class CompanionFeed(Entity):
    TABLE = "companion_feeds"
    id: str
    companion: Companion
    item: Item
    quantity: int
    status: FeedStatus
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class RewardOrder(Entity):
    """Order of the player's six-number Scrappy shorthand."""

    TABLE = "reward_order"
    KEY = ("companion", "position")
    companion: Companion
    position: int
    item: Item
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class RewardBatch(Entity):
    TABLE = "reward_batches"
    id: str
    companion: Companion
    rounds: int | None
    status: RewardBatchStatus
    source: Source


@dataclass(frozen=True, slots=True, kw_only=True)
class RewardLine(Entity):
    TABLE = "reward_lines"
    KEY = ("batch", "item")
    batch: RewardBatch
    item: Item
    quantity: int


# Load order: every reference points to a table earlier in this list.
ENTITIES: tuple[type[Entity], ...] = (
    Source,
    ItemFamily,
    Item,
    Alias,
    Station,
    Recipe,
    RecipeInput,
    RecycleYield,
    ItemValue,
    StackSize,
    AugmentCapacity,
    ScrappyRate,
    WeaponProfile,
    ModFit,
    CombatWeapon,
    GameMap,
    Enemy,
    EnemyPart,
    Matchup,
    MapEncounter,
    StashCounter,
    AccountMetric,
    Preference,
    PlayerBuild,
    SkillRank,
    Feat,
    RewardGap,
    Holding,
    ItemInstance,
    WeaponAttachment,
    RaidReport,
    RaidLine,
    UnreconciledHolding,
    RaidIntent,
    InventoryAction,
    Transaction,
    LoadoutTarget,
    PlannedSale,
    DispositionRule,
    WorkbookPolicy,
    Goal,
    GoalRequirement,
    GoalDependency,
    Reservation,
    ProjectContribution,
    Objective,
    OpenQuestion,
    Companion,
    CompanionFeed,
    RewardOrder,
    RewardBatch,
    RewardLine,
)
