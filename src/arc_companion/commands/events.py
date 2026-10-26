"""One thing that happened, saved as it is reported.

Play reports a stream of small actions (a craft, a move, a trade, a reward), not a finished
count. Each action is one `event`: signed deltas per (item, location), recorded as history with
its real kind, and saved on its own. Given the stash counter, the records must reproduce it
(A5), so a missing input is caught on the action that caused it, not raids later. The batch
`stocktake` stays for full recounts.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from ..enums import ActionKind, Location, MetricKind
from ..model import (
    AccountMetric,
    Holding,
    InventoryAction,
    Item,
    ItemInstance,
    Source,
    WeaponAttachment,
)
from ..queries import resolve
from ..store import State
from .core import Change, Refused, _counted, _holding_id, adjust_holding, check_counter

STASH = Location.STASH


@dataclass(frozen=True, slots=True)
class Reading:
    """What the player read off the screen with the action, if anything."""

    stash_used: int | None = None
    coins: int | None = None


NO_READING = Reading()


@dataclass(frozen=True, slots=True)
class Delta:
    """`quantity` units of `item` arrive at (positive) or leave (negative) `location`."""

    kind: ActionKind
    item: str
    location: Location
    quantity: int


def event(
    verb: str, deltas: list[Delta], reading: Reading = NO_READING, then: Change | None = None
) -> Change:
    """Apply `deltas`, record each as history, then run `then` (e.g. a repair's new
    durability). A stash reading is checked against the records; coins are recorded as read."""
    if not deltas:
        raise Refused(f"{verb}: nothing happened")

    def change(state: State, source: Source) -> str:
        lines = []
        for n, d in enumerate(deltas):
            item = resolve(state, d.item)
            _apply(state, item, d, source)
            state.add(
                InventoryAction(
                    id=f"{source.id}_{n}",
                    kind=d.kind,
                    item=item,
                    quantity=d.quantity,
                    source=source,
                )
            )
            lines.append(f"{item.id}@{d.location} {d.quantity:+d}")
        summary = [f"{verb}: {', '.join(lines)}"]
        if then is not None:
            summary.append(then(state, source))
        summary += _record_reading(state, reading, source)
        return "; ".join(summary)

    return change


def _record_reading(state: State, reading: Reading, source: Source) -> list[str]:
    lines = []
    if reading.stash_used is not None:
        lines.append(check_counter(state, reading.stash_used, source))
    if reading.coins is not None:
        state.put(AccountMetric(id=MetricKind.COINS, value=reading.coins, source=source))
        lines.append(f"coins {reading.coins}")
    return lines


def _apply(state: State, item: Item, d: Delta, source: Source) -> None:
    """Counted stacks first; a unit leaving with no stack left is a tracked piece, which goes
    with its mods. An item arriving
    where it was never recorded starts from zero: the place is counted, so absence was a zero."""
    location, quantity = d.location, d.quantity
    held = state.find(Holding, _holding_id(item, location))
    if quantity > 0 and held is None:
        state.add(_counted(item, location, 0, 0, source))
    from_stack = quantity
    if quantity < 0:
        on_hand = held.quantity if held is not None and held.quantity is not None else 0
        from_stack = max(quantity, -on_hand)
        _remove_pieces(state, item, location, from_stack - quantity)
    if from_stack:
        adjust_holding(state, item, from_stack, source, location)


def _remove_pieces(state: State, item: Item, location: Location, count: int) -> None:
    if not count:
        return
    attached = {a.mod.id for a in state.all(WeaponAttachment)}
    loose = [
        i
        for i in state.all(ItemInstance)
        if i.item == item and i.location is location and i.id not in attached
    ]
    if len(loose) < count:
        raise Refused(f"{item.id}: only {len(loose)} at {location}, cannot take {count}")
    if len(loose) > count:
        raise Refused(f"{item.id}: {len(loose)} tracked pieces at {location}; name one")
    for piece in loose:
        for a in state.all(WeaponAttachment):
            if a.weapon.id == piece.id:
                state.remove(a)
                state.remove(a.mod)
        state.remove(piece)


# --- the actions players report -----------------------------------------------------------------

Pairs = list[tuple[str, int]]


def move(pairs: Pairs, origin: Location, dest: Location, reading: Reading = NO_READING) -> Change:
    """Units from a counted stack move as deltas; a tracked piece (a weapon, a shield) moves
    itself, with its mods, durability and history (A11)."""

    def change(state: State, source: Source) -> str:
        stacked: Pairs = []
        pieces: list[str] = []
        for name, quantity in pairs:
            item = resolve(state, name)
            held = state.find(Holding, _holding_id(item, origin))
            from_stack = min(quantity, (held.quantity or 0) if held else 0)
            if from_stack:
                stacked.append((name, from_stack))
            if quantity > from_stack:
                pieces += _relocate(state, item, origin, dest, quantity - from_stack)
        summary = []
        if stacked:
            deltas = [d for n, q in stacked for d in _pair(ActionKind.MOVE, n, origin, dest, q)]
            summary.append(event("move", deltas)(state, source))
        if pieces:
            summary.append(f"move: {', '.join(pieces)} {origin} -> {dest}")
        return "; ".join(summary + _record_reading(state, reading, source))

    return change


def _relocate(state: State, item: Item, origin: Location, dest: Location, count: int) -> list[str]:
    attached = {a.mod.id: a for a in state.all(WeaponAttachment)}
    loose = [
        i
        for i in state.all(ItemInstance)
        if i.item == item and i.location is origin and i.id not in attached
    ]
    if len(loose) != count:
        raise Refused(f"{item.id}: {len(loose)} tracked at {origin}, moving {count}; name one")
    for piece in loose:
        state.put(dataclasses.replace(piece, location=dest))
        for a in attached.values():
            if a.weapon.id == piece.id:
                state.put(dataclasses.replace(a.mod, location=dest))
    return [piece.item.id for piece in loose]


def craft(
    made: Pairs, using: Pairs, into: Location = STASH, reading: Reading = NO_READING
) -> Change:
    """Inputs come from the stash; the output lands at `into` (the backpack for ammo)."""
    deltas = [Delta(ActionKind.CRAFT_INPUT, n, STASH, -q) for n, q in using]
    deltas += [Delta(ActionKind.CRAFT_OUTPUT, n, into, q) for n, q in made]
    return event("craft", deltas, reading)


def recycle(items: Pairs, outputs: Pairs, reading: Reading = NO_READING) -> Change:
    deltas = [Delta(ActionKind.RECYCLE, n, STASH, -q) for n, q in items]
    deltas += [Delta(ActionKind.RECYCLE_OUTPUT, n, STASH, q) for n, q in outputs]
    return event("recycle", deltas, reading)


def sell(items: Pairs, origin: Location = STASH, reading: Reading = NO_READING) -> Change:
    return event("sell", [Delta(ActionKind.SELL, n, origin, -q) for n, q in items], reading)


def loot(items: Pairs, into: Location = STASH, reading: Reading = NO_READING) -> Change:
    """Came in: unloaded from a raid, a quest or pass reward, bought."""
    return event("loot", [Delta(ActionKind.LOOT, n, into, q) for n, q in items], reading)


def use(items: Pairs, origin: Location, reading: Reading = NO_READING) -> Change:
    """Consumed: meds and ammo in a raid, a key."""
    return event("use", [Delta(ActionKind.USED, n, origin, -q) for n, q in items], reading)


def trade(give: Pairs, get: Pairs, reading: Reading = NO_READING) -> Change:
    """An Envoy or trader swap: items out of the stash, items in."""
    deltas = [Delta(ActionKind.TRADE, n, STASH, -q) for n, q in give]
    deltas += [Delta(ActionKind.TRADE, n, STASH, q) for n, q in get]
    return event("trade", deltas, reading)


def repair(using: Pairs, condition: Change, reading: Reading = NO_READING) -> Change:
    deltas = [Delta(ActionKind.REPAIR_INPUT, n, STASH, -q) for n, q in using]
    return event("repair", deltas, reading, condition)


def _pair(kind: ActionKind, name: str, origin: Location, dest: Location, q: int) -> list[Delta]:
    return [Delta(kind, name, origin, -q), Delta(kind, name, dest, q)]
