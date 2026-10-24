"""Counts and where things are: live counts, condition, project contributions."""

from __future__ import annotations

import dataclasses

from ..enums import (
    Confidence,
    Location,
    MetricKind,
    RaidStatus,
)
from ..model import (
    AccountMetric,
    Goal,
    Holding,
    ProjectContribution,
    RaidReport,
    Source,
    StashCounter,
    UnreconciledHolding,
    WeaponAttachment,
)
from ..queries import resolve
from ..store import State
from .core import (
    Change,
    Refused,
    _holding_id,
    _one_piece,
    adjust_holding,
)


def set_count(
    item_name: str, location: Location, quantity: int | None, slots: int | None = None
) -> Change:
    """Record a live count for one stack. `None` records that the count is unknown."""
    if quantity is not None and quantity < 0:
        raise Refused("quantity cannot be negative")

    def change(state: State, source: Source) -> str:
        item = resolve(state, item_name)
        state.put(
            Holding(
                id=_holding_id(item, location),
                item=item,
                location=location,
                quantity=quantity,
                slots=slots,
                confidence=Confidence.UNKNOWN if quantity is None else Confidence.CONFIRMED,
                source=source,
                note=None,
            )
        )
        shown = "unknown" if quantity is None else quantity
        return f"set-count {item.id} @ {location} = {shown}"

    return change


def set_stash(used: int, capacity: int) -> Change:
    def change(state: State, source: Source) -> str:
        state.put(
            StashCounter(
                id="stash",
                used=used,
                capacity=capacity,
                confidence=Confidence.CONFIRMED,
                source=source,
            )
        )
        return f"set-stash {used}/{capacity}"

    return change


def set_metric(kind: MetricKind, value: int) -> Change:
    def change(state: State, source: Source) -> str:
        state.put(AccountMetric(id=kind, value=value, source=source))
        return f"set-metric {kind} = {value}"

    return change


def reconcile(item_name: str, counts: dict[Location, int]) -> Change:
    """Close every unreconciled row for an item with live counts.

    The stash count is mandatory, and so is a count for every location the open rows claim,
    so a row can never be closed by assuming its location is empty.
    """

    def change(state: State, source: Source) -> str:
        item = resolve(state, item_name)
        open_rows = [u for u in state.all(UnreconciledHolding) if u.item == item]
        needed = {Location.STASH} | {u.claimed_location for u in open_rows}
        if missing := sorted(needed - counts.keys()):
            raise Refused(f"{item.id}: live counts required for {', '.join(missing)}")
        for location, quantity in counts.items():
            set_count(item.id, location, quantity)(state, source)
        for row in open_rows:
            state.remove(row)
        _close_reconciled_reports(state)
        return f"reconcile {item.id}: {len(open_rows)} unreconciled rows closed by live count"

    return change


def _close_reconciled_reports(state: State) -> None:
    open_reports = {u.raid_report.id for u in state.all(UnreconciledHolding) if u.raid_report}
    for report in state.all(RaidReport):
        if report.status is not RaidStatus.RECONCILED and report.id not in open_reports:
            state.put(dataclasses.replace(report, status=RaidStatus.RECONCILED))


def set_condition(piece: str, current: int, maximum: int) -> Change:
    """`piece` is an instance id, or an item with exactly one unit, which becomes tracked."""

    def change(state: State, source: Source) -> str:
        attached = {a.mod.id for a in state.all(WeaponAttachment)}
        instance = _one_piece(state, piece, attached, source)
        instance_id = instance.id
        state.put(
            dataclasses.replace(
                instance, condition=current, condition_max=maximum, condition_source=source
            )
        )
        return f"set-condition {instance_id} = {current}/{maximum}"

    return change


def contribute(goal_id: str, item_name: str, quantity: int, location: Location | None) -> Change:
    """Commit items to a project (Trophy Display, quests): they leave the inventory for good and
    count toward the goal. `location=None` means straight from a raid, never recorded as held.
    The `contributions` rule refuses more than the goal asks."""
    if quantity < 1:
        raise Refused("contribute at least one")

    def change(state: State, source: Source) -> str:
        goal = state.get(Goal, goal_id)
        item = resolve(state, item_name)
        if location is not None:
            adjust_holding(state, item, -quantity, source, location)
        given = state.find(ProjectContribution, (goal.id, item.id))
        total = quantity + (given.quantity if given else 0)
        state.put(ProjectContribution(goal=goal, item=item, quantity=total, source=source))
        return f"contribute {quantity} {item.id} to {goal.id} ({total} given)"

    return change
