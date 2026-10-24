"""Save state layer: what the player has now (counts, pieces, mods, counter, build)."""

from __future__ import annotations

from dataclasses import dataclass

from ..enums import (
    Confidence,
    Location,
    MetricKind,
    ModSlot,
    UnreconciledReason,
)
from .base import (
    Entity,
    Source,
)
from .history import (
    RaidReport,
)
from .reference import (
    Item,
)


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
