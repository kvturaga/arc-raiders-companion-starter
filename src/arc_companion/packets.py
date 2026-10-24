"""The shapes `arc` prints. Views and queries return these; the CLI serializes them to JSON.

TypedDicts keep the output plain JSON while letting mypy check every field a view builds or
reads. `None` in a field means unobserved, as everywhere else (A2).
"""

from __future__ import annotations

from typing import TypedDict


class Requirement(TypedDict):
    item: str
    name: str
    required: int
    committed: int
    remaining: int
    stash: int | None
    reserved_for_other_goals: int
    available: int | None
    missing: int | None
    confidence: str
    unreconciled_not_counted: int | None


class ObjectiveLine(TypedDict):
    id: str
    kind: str
    target: str
    required: int
    progress: int | None


class GoalPlan(TypedDict):
    goal: str
    name: str
    status: str
    blocked_by: list[str]
    requirements: list[Requirement]
    objectives: list[ObjectiveLine]


class GoalLine(TypedDict):
    goal: str
    name: str
    priority: int | None
    blocked_by: list[str]
    short: dict[str, int | None]
    objectives: list[ObjectiveLine]


class AsOf(TypedDict):
    source: str
    date: str


class SlotMathLine(TypedDict):
    implied_by_counts: int
    complete: bool
    items_without_stack_size: int
    items_without_count: int


class StashLine(TypedDict):
    used: int
    capacity: int
    free: int
    confidence: str
    slot_math: SlotMathLine


class BuildLine(TypedDict):
    level: int
    mobility: int | None
    conditioning: int | None
    survival: int | None
    unspent: int
    skills: dict[str, int | None]


class Unproven(TypedDict):
    unreconciled_rows: int
    open_questions: int
    next_step: str | None


class Bootstrap(TypedDict):
    as_of: AsOf
    stash: StashLine
    coins: int | None
    build: BuildLine
    preferences: dict[str, int]
    active_goals: list[GoalLine]
    unproven: Unproven
    findings: list[str]


class CountCheckRow(TypedDict):
    item: str
    name: str
    recorded_stash: int | None
    unreconciled: int | None
    rows: int
    claimed_in: list[str]
    rows_followed_by_stash_count: int
    active_goals: list[str]
    reserved: bool
    command: str


class HoldingLine(TypedDict):
    location: str
    quantity: int | None
    source: str


class PieceLine(TypedDict):
    id: str
    location: str
    condition: str | None


class UnreconciledLine(TypedDict):
    claimed_in: str
    quantity: int | None
    raid: str | None
    stash_recounted_after: bool


class ItemPacket(TypedDict):
    item: str
    name: str
    category: str
    stack_size: int | None
    stack_size_source: str | None
    family: str | None
    confirmed_total: int | None
    stash: int | None
    confidence: str
    holdings: list[HoldingLine]
    instances: list[PieceLine]
    unreconciled_not_counted: list[UnreconciledLine]
    goals: list[str]


class LoadoutRow(TypedDict):
    location: str
    item: str
    quantity: int
    piece: str | None


class DebriefRow(TypedDict):
    item: str
    haul: int
    stash_after: int
    needed_by: list[str]
    decision: str
    why: str
    coins_if_sold: int | None
    slots_freed: int
    your_call: str | None


class SlotChange(TypedDict):
    item: str
    before: int
    after: int
    slots: int


class Prediction(TypedDict):
    counter_now: int
    counter_predicted: int
    slot_changes: list[SlotChange]
    coins_now: int | None
    coins_predicted: int | None
    sale_prices: str
    unpriced_sales: list[str]
    unknown: list[str]
