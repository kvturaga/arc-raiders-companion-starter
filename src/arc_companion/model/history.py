"""History layer: what happened (raid receipts, inventory actions, transactions, questions)."""

from __future__ import annotations

from dataclasses import dataclass

from ..enums import (
    ActionKind,
    QuestionStatus,
    RaidLineKind,
    RaidStatus,
    TransactionStatus,
)
from .base import (
    Entity,
    Source,
)
from .reference import (
    Item,
    Recipe,
)


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
class OpenQuestion(Entity):
    """Something only the player can answer. `topic` is prose by nature; links are typed."""

    TABLE = "open_questions"
    id: str
    topic: str
    status: QuestionStatus
    raid_report: RaidReport | None
    source: Source
    resolution: Source | None
