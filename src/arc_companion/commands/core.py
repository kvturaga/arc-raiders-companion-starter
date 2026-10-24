"""Shared machinery for every setter: the write transaction and the helpers that move items."""

from __future__ import annotations

import dataclasses
import datetime as dt
import subprocess
from collections.abc import Callable
from pathlib import Path

from ..checks import errors, run
from ..enums import (
    Confidence,
    Location,
    SourceKind,
)
from ..model import (
    Holding,
    Item,
    ItemInstance,
    Source,
    StackSize,
)
from ..queries import resolve, slots_needed
from ..store import State, load, save, write_lock

Change = Callable[[State, Source], str]


class Refused(ValueError):
    pass


def data_dir(project: Path) -> Path:
    return project / "data"


def apply(
    project: Path,
    note: str,
    actor: str,
    change: Change,
    *,
    commit: bool = True,
    kind: SourceKind = SourceKind.USER_REPORT,
) -> str:
    if not note.strip():
        raise Refused("a note recording what the player observed is required")
    with write_lock(project):
        work = load(data_dir(project))
        now = dt.datetime.now()
        source = Source(
            id=f"obs_{now:%Y%m%dT%H%M%S%f}",
            seq=max(s.seq for s in work.all(Source)) + 1,
            kind=kind,
            observed_on=now.date(),
            reference=note.strip(),
        )
        work.add(source)
        summary = change(work, source)
        work.replace_references()
        if problems := errors(run(work)):
            raise Refused("; ".join(f"[{f.rule}] {f.message}" for f in problems))
        save(work, data_dir(project))
        if commit and (project / ".git").exists():
            _commit(project, f"{summary}\n\nactor: {actor}\nsource: {source.id}\nnote: {note}")
    return summary


def _commit(project: Path, message: str) -> None:
    git = ["git", "-C", str(project)]
    subprocess.run([*git, "add", "data"], check=True, capture_output=True)
    subprocess.run([*git, "commit", "-q", "-m", message], check=True, capture_output=True)


def _holding_id(item: Item, location: Location) -> str:
    return f"{item.id}@{location}"


def _counted(item: Item, location: Location, quantity: int, slots: int, source: Source) -> Holding:
    return Holding(
        id=_holding_id(item, location),
        item=item,
        location=location,
        quantity=quantity,
        slots=slots,
        confidence=Confidence.CONFIRMED,
        source=source,
        note=None,
    )


def _piece_from_stock(state: State, item: Item, location: Location, source: Source) -> ItemInstance:
    """Track one unit individually, taking it from the stack at `location` if there is one;
    otherwise the piece is new to the records (seen on a weapon, never counted as a tile)."""
    held = state.find(Holding, _holding_id(item, location))
    if held is not None and held.quantity:
        slots = held.slots
        if slots is not None and held.quantity - 1 < slots:
            slots = held.quantity - 1
        state.put(dataclasses.replace(held, quantity=held.quantity - 1, slots=slots, source=source))
    piece = ItemInstance(
        id=f"{item.id}@{location}_{source.id}",
        item=item,
        location=location,
        condition=None,
        condition_max=None,
        condition_source=None,
        confidence=Confidence.CONFIRMED,
        source=source,
    )
    state.add(piece)
    return piece


def _one_piece(state: State, name: str, attached: set[str], source: Source) -> ItemInstance:
    if (piece := state.find(ItemInstance, name)) is not None:
        return piece
    item = resolve(state, name)
    pieces = [i for i in state.all(ItemInstance) if i.item == item and i.id not in attached]
    if len(pieces) == 1:
        return pieces[0]
    if pieces:
        raise Refused(
            f"{item.id}: {len(pieces)} tracked pieces; name one: {[i.id for i in pieces]}"
        )
    stocked = [h for h in state.all(Holding) if h.item == item and h.quantity]
    if len(stocked) != 1 or stocked[0].quantity != 1:
        raise Refused(f"{item.id}: no single unit to track (holdings: {[h.id for h in stocked]})")
    return _piece_from_stock(state, item, stocked[0].location, source)


def adjust_holding(
    state: State, item: Item, delta: int, source: Source, location: Location = Location.STASH
) -> None:
    """Add to or take from a counted stack; slots follow merged stacks. Refuses below zero or on
    a stack that was never counted (blank is unobserved, not zero)."""
    held = state.find(Holding, _holding_id(item, location))
    if held is None or held.quantity is None:
        raise Refused(f"{item.id} has no counted {location} stack to adjust")
    quantity = held.quantity + delta
    if quantity < 0:
        raise Refused(f"{item.id}: {location} would go to {quantity}")
    stack = state.find(StackSize, item.id)
    slots = slots_needed(quantity, stack.units_per_slot) if stack else None
    state.put(dataclasses.replace(held, quantity=quantity, slots=slots, source=source))
