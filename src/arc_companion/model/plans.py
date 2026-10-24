"""Plans layer: what the player intends (goals, standing rules, preferences, planned sales)."""

from __future__ import annotations

from dataclasses import dataclass

from ..enums import (
    DispositionAction,
    GoalStatus,
    IntentStatus,
    Location,
    ObjectiveKind,
    PreferenceKey,
)
from .base import (
    Entity,
    Source,
)
from .reference import (
    Enemy,
    EnemyPart,
    Item,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class Preference(Entity):
    """A player choice, not a game fact. Booleans are stored as 0/1."""

    TABLE = "preferences"
    id: PreferenceKey
    value: int
    source: Source


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
class RaidIntent(Entity):
    TABLE = "raid_intents"
    id: str
    objective: str
    item: Item | None
    status: IntentStatus
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
