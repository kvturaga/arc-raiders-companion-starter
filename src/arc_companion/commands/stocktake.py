"""The stocktake: a complete live count of the locations it covers.

Steps, in order: group what was seen; check the stash against the counter; settle each seen item
(move tracked pieces that changed location, record durability, record the stack); zero what was
recorded but not seen; remove tracked pieces not seen; close unreconciled rows in covered places.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from ..enums import ActionKind, Confidence, GoalStatus, Location
from ..model import (
    GoalRequirement,
    Holding,
    InventoryAction,
    Item,
    ItemInstance,
    Source,
    StackSize,
    StashCounter,
    UnreconciledHolding,
    WeaponAttachment,
)
from ..queries import resolve
from ..store import State
from .core import Change, Refused, _counted, _holding_id
from .inventory import _close_reconciled_reports

_CARRIED_SLOTS = frozenset(
    {Location.EQUIPMENT, Location.BACKPACK, Location.QUICK_USE, Location.SAFE_POCKET}
)


@dataclasses.dataclass(frozen=True, slots=True)
class CountLine:
    """One item seen at one location: each entry of `stacks` is one slot's number."""

    location: Location
    item: str
    stacks: tuple[int, ...]
    condition: tuple[int, int] | None = None


def parse_stacks(raw: str) -> tuple[int, ...]:
    """`50x4+43` -> (50, 50, 50, 50, 43). `x` repeats a stack; `+` separates slots."""
    stacks: list[int] = []
    for part in raw.replace(" ", "").split("+"):
        value, _, times = part.partition("x")
        stacks += [int(value)] * (int(times) if times else 1)
    if not stacks or any(s < 1 for s in stacks):
        raise Refused(f"stacks {raw!r}: every slot holds at least one unit")
    return tuple(stacks)


Seen = dict[tuple[Item, Location], list[CountLine]]
# A change the player reported alongside a count: (kind, item name, quantity).
Event = tuple[ActionKind, str, int]
_SIGN = {ActionKind.LOOT: 1, ActionKind.USED: -1, ActionKind.SELL: -1}


@dataclass
class _Count:
    """What one stocktake works with, shared by its steps."""

    state: State
    source: Source
    covered: frozenset[Location]
    seen: Seen
    attached: set[str]
    removed: list[str] = field(default_factory=list)
    residuals: list[str] = field(default_factory=list)
    zeroed: int = 0

    def seen_at(self, item: Item, location: Location) -> bool:
        return (item, location) in self.seen

    def loose_pieces(self, item: Item, location: Location) -> list[ItemInstance]:
        return [
            i
            for i in self.state.all(ItemInstance)
            if i.item == item and i.location is location and i.id not in self.attached
        ]


def stocktake(
    lines: list[CountLine], stash_used: int | None, events: tuple[Event, ...] = ()
) -> Change:
    """A complete live count of every location that appears in `lines`.

    Anything recorded in a covered location but not seen there becomes a recorded zero;
    tracked pieces not seen are removed, with their attachments. A stash count must reproduce
    the stash counter slot for slot, which is the proof that no tile was skipped or read twice.

    `events` are the changes since the last count (loot in, sold, used). They are recorded as
    history, and conservation is checked per item: a stash quantity that differs from records
    plus events is a residual, recorded and named in the summary (B4, A9).
    """
    covered = frozenset(line.location for line in lines)
    if Location.STASH in covered and stash_used is None:
        raise Refused("a stash count needs the counter reading (--stash-used)")
    if covered >= _CARRIED_SLOTS:
        covered |= {Location.CARRIED}

    def change(state: State, source: Source) -> str:
        count = _Count(
            state=state,
            source=source,
            covered=covered,
            seen=_group(state, lines),
            attached={a.mod.id for a in state.all(WeaponAttachment)},
        )
        expected = _expected(count, events) if Location.STASH in covered else {}
        if stash_used is not None:
            _check_counter(count, stash_used)
        for (item, location), group in count.seen.items():
            _settle(count, item, location, group)
        _zero_unseen(count)
        _remove_unseen_pieces(count)
        _record_events(count, events)
        _record_residuals(count, expected)
        closed = _close_unreconciled(count)
        return _summary(count, closed)

    return change


_LOST_ON_DEATH = frozenset(
    {Location.EQUIPMENT, Location.BACKPACK, Location.QUICK_USE, Location.CARRIED}
)


def record_death() -> Change:
    """Death (C1): everything carried is lost except the safe pocket, mods on lost weapons too.

    The same steps as a stocktake that saw nothing in the carried slots, plus a loss event per
    item so history says what went down with the raider. The stash is not touched.
    """

    def change(state: State, source: Source) -> str:
        count = _Count(
            state=state,
            source=source,
            covered=_LOST_ON_DEATH,
            seen={},
            attached={a.mod.id for a in state.all(WeaponAttachment)},
        )
        lost: dict[Item, int] = {}
        for h in state.all(Holding):
            if h.location in _LOST_ON_DEATH and h.quantity:
                lost[h.item] = lost.get(h.item, 0) + h.quantity
        for piece in state.all(ItemInstance):
            if piece.location in _LOST_ON_DEATH:
                lost[piece.item] = lost.get(piece.item, 0) + 1
        losses = sorted((item.id, n) for item, n in lost.items())
        _zero_unseen(count)
        _remove_unseen_pieces(count)
        _record_events(count, tuple((ActionKind.LOSS, item, n) for item, n in losses))
        closed = _close_unreconciled(count)
        kept = sorted(
            {h.item.id for h in state.all(Holding) if h.location is Location.SAFE_POCKET}
            | {i.item.id for i in state.all(ItemInstance) if i.location is Location.SAFE_POCKET}
        )
        return (
            f"death: lost {', '.join(f'{item} {n}' for item, n in losses) or 'nothing'}"
            f"; safe pocket kept: {', '.join(kept) or 'nothing'}; {closed} unreconciled rows closed"
        )

    return change


def _held(count: _Count, item: Item) -> int | None:
    """Units of an item across the counted locations (stacks plus tracked pieces), or None if
    any of its stacks there was never counted. Moves between counted places net to zero."""
    quantities = [
        h.quantity
        for h in count.state.all(Holding)
        if h.item == item and h.location in count.covered
    ]
    pieces = sum(
        1 for i in count.state.all(ItemInstance) if i.item == item and i.location in count.covered
    )
    if any(q is None for q in quantities) or (not quantities and not pieces):
        return None  # never counted here: unobserved, not zero (A2)
    return sum(q or 0 for q in quantities) + pieces


def _expected(count: _Count, events: tuple[Event, ...]) -> dict[Item, int | None]:
    """What each item should total across the counted places: records plus reported events.
    `None` when the records never counted it (a first observation has no residual)."""
    items = {item for item, _ in count.seen}
    items |= {h.item for h in count.state.all(Holding) if h.location in count.covered}
    expected = {item: _held(count, item) for item in items}
    for kind, name, quantity in events:
        item = resolve(count.state, name)
        base = expected[item] if item in expected else _held(count, item)
        expected[item] = (base or 0) + _SIGN[kind] * quantity
    return expected


def _record_events(count: _Count, events: tuple[Event, ...]) -> None:
    for n, (kind, name, quantity) in enumerate(events):
        count.state.add(
            InventoryAction(
                id=f"{count.source.id}_{n}",
                kind=kind,
                item=resolve(count.state, name),
                quantity=quantity,
                source=count.source,
            )
        )


def _record_residuals(count: _Count, expected: dict[Item, int | None]) -> None:
    """Live total minus records plus events, per item. Recorded signed; never absorbed."""
    for item, should in sorted(expected.items(), key=lambda kv: kv[0].id):
        actual = _held(count, item) or 0
        if should is None or actual == should:
            continue
        count.state.add(
            InventoryAction(
                id=f"{count.source.id}_residual_{item.id}",
                kind=ActionKind.RESIDUAL,
                item=item,
                quantity=actual - should,
                source=count.source,
            )
        )
        count.residuals.append(f"{item.id} {actual - should:+}")


def _group(state: State, lines: list[CountLine]) -> Seen:
    seen: Seen = {}
    for line in lines:
        seen.setdefault((resolve(state, line.item), line.location), []).append(line)
    return seen


def _check_counter(count: _Count, stash_used: int) -> None:
    tiles = sum(
        len(line.stacks)
        for (_, location), group in count.seen.items()
        if location is Location.STASH
        for line in group
    )
    if tiles != stash_used:
        raise Refused(f"stash tiles counted {tiles}, counter shows {stash_used}")
    counter = count.state.all(StashCounter)[0]
    count.state.put(
        dataclasses.replace(
            counter, used=stash_used, confidence=Confidence.CONFIRMED, source=count.source
        )
    )


def _settle(count: _Count, item: Item, location: Location, group: list[CountLine]) -> None:
    """Record one seen item: its tracked pieces first, then the fungible rest as a stack."""
    stacks = [s for line in group for s in line.stacks]
    quantity = sum(stacks)
    pieces = _move_pieces_here(count, item, location, quantity)
    if quantity < len(pieces):
        raise Refused(
            f"{item.id} @ {location}: {quantity} seen, {len(pieces)} tracked pieces; "
            "say which piece is gone"
        )
    conditions = [line.condition for line in group if line.condition]
    pieces = _record_durability(
        count,
        item=item,
        location=location,
        quantity=quantity,
        pieces=pieces,
        conditions=conditions,
    )
    state, source = count.state, count.source
    fungible = quantity - len(pieces)
    if fungible or state.find(Holding, _holding_id(item, location)):
        state.put(_counted(item, location, fungible, len(stacks) - len(pieces), source))
    unallocated = state.find(Holding, _holding_id(item, Location.UNALLOCATED))
    if unallocated is not None and unallocated.quantity:
        state.put(_counted(item, Location.UNALLOCATED, 0, 0, source))


def _move_pieces_here(
    count: _Count, item: Item, location: Location, quantity: int
) -> list[ItemInstance]:
    """A tracked piece seen here but recorded in another counted place moved here (A11): it
    keeps its id, durability and mods. Returns the pieces now here."""
    pieces = count.loose_pieces(item, location)
    elsewhere = [
        i
        for other in count.covered
        if other is not location and not count.seen_at(item, other)
        for i in count.loose_pieces(item, other)
    ]
    for moved in elsewhere[: max(0, quantity - len(pieces))]:
        count.state.put(dataclasses.replace(moved, location=location, source=count.source))
        for a in count.state.all(WeaponAttachment):
            if a.weapon.id == moved.id:
                count.state.put(dataclasses.replace(a.mod, location=location, source=count.source))
        pieces.append(count.state.get(ItemInstance, moved.id))
    return pieces


def _record_durability(
    count: _Count,
    *,
    item: Item,
    location: Location,
    quantity: int,
    pieces: list[ItemInstance],
    conditions: list[tuple[int, int]],
) -> list[ItemInstance]:
    """A durability reading lands on the one piece it can belong to; on a single untracked unit
    it makes that unit a tracked piece."""
    if not conditions:
        return pieces
    state, source = count.state, count.source
    if not pieces and quantity == 1:
        pieces = [
            ItemInstance(
                id=f"{item.id}@{location}_{source.id}",
                item=item,
                location=location,
                condition=None,
                condition_max=None,
                condition_source=None,
                confidence=Confidence.CONFIRMED,
                source=source,
            )
        ]
        state.put(pieces[0])
    if len(pieces) == 1 and len(conditions) == 1:
        current, maximum = conditions[0]
        state.put(
            dataclasses.replace(
                pieces[0],
                condition=current,
                condition_max=maximum,
                condition_source=source,
                confidence=Confidence.CONFIRMED,
                source=source,
            )
        )
        pieces = [state.get(ItemInstance, pieces[0].id)]
    return pieces


def _zero_unseen(count: _Count) -> None:
    """Recorded but not seen in a covered place is a recorded zero (A2). A complete stash count
    also proves zero for open-goal items never recorded at all."""
    state, source = count.state, count.source
    if Location.STASH in count.covered:
        for req in state.all(GoalRequirement):
            if (
                req.goal.status is not GoalStatus.COMPLETE
                and not count.seen_at(req.item, Location.STASH)
                and state.find(Holding, _holding_id(req.item, Location.STASH)) is None
            ):
                state.put(_counted(req.item, Location.STASH, 0, 0, source))
                count.zeroed += 1
    for h in state.all(Holding):
        if h.location in count.covered and not count.seen_at(h.item, h.location) and h.quantity:
            state.put(_counted(h.item, h.location, 0, 0, source))
            count.zeroed += 1


def _remove_unseen_pieces(count: _Count) -> None:
    state = count.state
    for piece in state.all(ItemInstance):
        if (
            piece.location in count.covered
            and not count.seen_at(piece.item, piece.location)
            and piece.id not in count.attached
        ):
            for a in state.all(WeaponAttachment):
                if a.weapon.id == piece.id:
                    state.remove(a)
                    state.remove(a.mod)
                    count.removed.append(a.mod.id)
            state.remove(piece)
            count.removed.append(piece.id)


def _close_unreconciled(count: _Count) -> int:
    closed = [
        u for u in count.state.all(UnreconciledHolding) if u.claimed_location in count.covered
    ]
    for row in closed:
        count.state.remove(row)
    _close_reconciled_reports(count.state)
    return len(closed)


def _summary(count: _Count, closed: int) -> str:
    left = sorted(
        h.item.id
        for h in count.state.all(Holding)
        if h.location is Location.UNALLOCATED and h.quantity
    )
    lines = [
        f"stocktake {', '.join(sorted(count.covered))}: {len(count.seen)} items counted, "
        f"{count.zeroed} recorded zeros, {closed} unreconciled rows closed"
    ]
    if count.removed:
        lines.append("not seen, removed: " + ", ".join(count.removed))
    if count.residuals:
        lines.append(
            "residual (count differs from records plus events): " + ", ".join(count.residuals)
        )
    if left:
        lines.append("still unallocated (not seen): " + ", ".join(left))
    return "\n".join(lines)


def carried_stash(state: State, quantities: dict[Item, int]) -> list[CountLine]:
    """Stash lines for a stocktake carried forward from the records: each stack merged at its
    stack size, plus every loose tracked piece. Used when the player reads only the counter."""
    attached = {a.mod.id for a in state.all(WeaponAttachment)}
    lines = []
    for item, quantity in sorted(quantities.items(), key=lambda kv: kv[0].id):
        if quantity <= 0:
            continue
        stack = state.find(StackSize, item.id)
        size = stack.units_per_slot if stack else quantity
        full, rest = divmod(quantity, size)
        lines.append(CountLine(Location.STASH, item.id, (size,) * full + ((rest,) if rest else ())))
    for piece in state.all(ItemInstance):
        if piece.location is Location.STASH and piece.id not in attached:
            lines.append(CountLine(Location.STASH, piece.item.id, (1,)))
    return lines
