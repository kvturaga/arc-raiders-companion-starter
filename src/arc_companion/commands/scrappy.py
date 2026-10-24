"""Scrappy: queuing food and claiming his haul, explained against the wiki's rate table."""

from __future__ import annotations

import dataclasses
import re

from ..enums import (
    FeedStatus,
    Location,
    RewardBatchStatus,
)
from ..model import (
    Companion,
    CompanionFeed,
    Holding,
    Item,
    RewardBatch,
    RewardLine,
    RewardOrder,
    ScrappyRate,
    Source,
    StashCounter,
)
from ..queries import resolve
from ..reference import (
    FEED_QUEUE,
    FOOD_BONUS,
    SCRAPPY_FOODS,
)
from ..store import State
from .core import (
    Change,
    Refused,
    _holding_id,
    adjust_holding,
)


def parse_scrappy(raw: str) -> list[int]:
    """`8 8 8 8 8 11`, or `8s and 11` (every material 8, seeds 11), in reward-order positions."""
    tokens = re.findall(r"\d+s?", raw)
    if tokens and tokens[0].endswith("s") and len(tokens) == 2:
        return [int(tokens[0][:-1])] * 5 + [int(tokens[1])]
    if len(tokens) != 6 or any(t.endswith("s") for t in tokens):
        raise Refused(f"scrappy shorthand {raw!r}: give six numbers, or 'Ns and M'")
    return [int(t) for t in tokens]


def _scrappy(state: State) -> Companion:
    return state.get(Companion, "scrappy")


def feed_scrappy(food: str, quantity: int = 1) -> Change:
    """Queue food: it leaves the stash now and pays +5 of its material once eaten."""

    def change(state: State, source: Source) -> str:
        item = resolve(state, food)
        if item.id not in SCRAPPY_FOODS:
            raise Refused(f"{item.id} is not a Scrappy food: {', '.join(sorted(SCRAPPY_FOODS))}")
        queued = [f for f in state.all(CompanionFeed) if f.status is FeedStatus.QUEUED]
        if len(queued) + quantity > FEED_QUEUE:
            raise Refused(f"queue holds {FEED_QUEUE}; {len(queued)} already queued")
        held = state.find(Holding, _holding_id(item, Location.STASH))
        if held is None or (held.quantity or 0) < quantity:
            raise Refused(f"stash has {held.quantity if held else None} {item.id}")
        adjust_holding(state, item, -quantity, source)
        for n in range(quantity):
            state.add(
                CompanionFeed(
                    id=f"feed_{source.id}_{n}",
                    companion=_scrappy(state),
                    item=item,
                    quantity=1,
                    status=FeedStatus.QUEUED,
                    source=source,
                )
            )
        return f"feed-scrappy {item.id} x{quantity}"

    return change


def claim_scrappy(
    shorthand: str,
    rounds: int,
    ate: list[str],
    extras: dict[str, int],
    stash_used: int | None,
) -> Change:
    """Claim Scrappy's haul into the stash (stacks merged) and explain it against the wiki."""
    amounts = parse_scrappy(shorthand)

    def change(state: State, source: Source) -> str:
        scrappy = _scrappy(state)
        if not 1 <= rounds <= scrappy.round_capacity:
            raise Refused(f"rounds must be 1-{scrappy.round_capacity}")
        order = sorted(
            (r for r in state.all(RewardOrder) if r.companion == scrappy), key=lambda r: r.position
        )
        got = {r.item.id: q for r, q in zip(order, amounts, strict=True)}
        for name, quantity in extras.items():
            got[resolve(state, name).id] = got.get(resolve(state, name).id, 0) + quantity
        bonus: dict[str, int] = {}
        for food in ate:
            item = resolve(state, food)
            queued = [
                f
                for f in state.all(CompanionFeed)
                if f.item == item and f.status is FeedStatus.QUEUED
            ]
            if not queued:
                raise Refused(f"no queued {item.id} to mark eaten")
            state.put(dataclasses.replace(queued[0], status=FeedStatus.CONSUMED, source=source))
            material = SCRAPPY_FOODS[item.id]
            bonus[material] = bonus.get(material, 0) + FOOD_BONUS
        batch = RewardBatch(
            id=f"scrappy_{source.id}",
            companion=scrappy,
            rounds=rounds,
            status=RewardBatchStatus.CLAIMED,
            source=source,
        )
        state.add(batch)
        for item_id, quantity in got.items():
            if quantity:
                item = state.get(Item, item_id)
                state.add(RewardLine(batch=batch, item=item, quantity=quantity))
                adjust_holding(state, item, quantity, source)
        if stash_used is not None:
            counter = state.all(StashCounter)[0]
            state.put(dataclasses.replace(counter, used=stash_used, source=source))
        return f"claim-scrappy {rounds} round(s): {_explain(state, scrappy, rounds, got, bonus)}"

    return change


def _explain(
    state: State, scrappy: Companion, rounds: int, got: dict[str, int], bonus: dict[str, int]
) -> str:
    """Name the wiki bracket that reproduces a one-round claim, or show what is unexplained."""
    order = sorted(
        (r for r in state.all(RewardOrder) if r.companion == scrappy), key=lambda r: r.position
    )
    seeds = order[-1].item.id
    shown = ", ".join(f"{r.item.id} {got.get(r.item.id, 0)}" for r in order)
    if rounds != 1:
        return f"{shown} (several rounds: brackets not separable)"
    for rate in state.all(ScrappyRate):
        if rate.level != scrappy.level:
            continue
        expect = {
            r.item.id: (rate.seed_quantity if r.item.id == seeds else rate.material_quantity)
            + bonus.get(r.item.id, 0)
            for r in order
        }
        if all(got.get(k, 0) == v for k, v in expect.items()):
            how = "extracted" if rate.extracted else "not extracted"
            minutes = rate.min_minutes_exclusive
            return f"{shown}; matches level {scrappy.level}, over {minutes} min, {how}"
    return f"{shown}; matches no level-{scrappy.level} bracket: an input is missing (food? bonus?)"
