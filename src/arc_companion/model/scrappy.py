"""Scrappy: the companion, its food queue, reward shorthand and claimed batches."""

from __future__ import annotations

from dataclasses import dataclass

from ..enums import (
    FeedStatus,
    RewardBatchStatus,
)
from .base import (
    Entity,
    Source,
)
from .reference import (
    Item,
)


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
