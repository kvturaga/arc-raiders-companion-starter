"""Read-only views computed from the object graph. Nothing here writes or stores derived facts."""

from __future__ import annotations

from dataclasses import dataclass

from .enums import Confidence, GoalStatus, Location, MetricKind, ObjectiveKind, QuestionStatus
from .model import (
    AccountMetric,
    Alias,
    Goal,
    GoalDependency,
    GoalRequirement,
    Holding,
    Item,
    ItemInstance,
    Objective,
    OpenQuestion,
    ProjectContribution,
    Reservation,
    StackSize,
    StashCounter,
    UnreconciledHolding,
    WeaponAttachment,
)
from .packets import GoalPlan, Requirement
from .store import State


def _total(values: list[int | None]) -> int | None:
    """Sum, or None if any part is unobserved. No rows at all is also unobserved:
    an absent record never means the player has none."""
    if not values or any(v is None for v in values):
        return None
    return sum(v for v in values if v is not None)


def resolve(state: State, name: str) -> Item:
    """Exact id, exact name, or exact alias (case-insensitive). Never fuzzy."""
    if (item := state.find(Item, name)) is not None:
        return item
    folded = name.casefold()
    matches = {i.id: i for i in state.all(Item) if i.name.casefold() == folded}
    matches |= {a.item.id: a.item for a in state.all(Alias) if a.alias.casefold() == folded}
    if len(matches) == 1:
        return next(iter(matches.values()))
    if matches:
        raise KeyError(f"{name!r} is ambiguous: {sorted(matches)}")
    raise KeyError(f"unknown item {name!r}; add an alias rather than guessing")


def recounted_after(state: State, loot: UnreconciledHolding) -> bool:
    """True if a confirmed stash count for this item was recorded after the loot was."""
    return any(
        h.item == loot.item
        and h.location is Location.STASH
        and h.confidence is Confidence.CONFIRMED
        and h.source.seq > loot.source.seq
        for h in state.all(Holding)
    )


@dataclass(frozen=True, slots=True)
class Balance:
    item: Item
    holdings: tuple[Holding, ...]
    instances: tuple[ItemInstance, ...]
    unreconciled: tuple[UnreconciledHolding, ...]

    @property
    def confirmed(self) -> int | None:
        """Owned with an established location. Instances count one each."""
        return _total([h.quantity for h in self.holdings] + [1] * len(self.instances))

    @property
    def stash(self) -> int | None:
        stash = [h.quantity for h in self.holdings if h.location is Location.STASH]
        stash += [1 for i in self.instances if i.location is Location.STASH]
        return _total(stash)

    @property
    def unreconciled_quantity(self) -> int | None:
        """0 when no rows: this is a statement about our records, not the game."""
        return _total([u.quantity for u in self.unreconciled]) if self.unreconciled else 0

    @property
    def recorded(self) -> int | None:
        """Everything the records claim, located or not. Equals the legacy total."""
        parts = [h.quantity for h in self.holdings] + [1] * len(self.instances)
        return _total(parts + [u.quantity for u in self.unreconciled])

    @property
    def confidence(self) -> Confidence:
        counted = [h.confidence for h in self.holdings if h.quantity != 0]
        counted += [i.confidence for i in self.instances]
        if self.confirmed is None:
            return Confidence.UNKNOWN
        return Confidence.weakest(counted) if counted else Confidence.CONFIRMED


def balance(state: State, item: Item) -> Balance:
    return Balance(
        item=item,
        holdings=tuple(h for h in state.all(Holding) if h.item == item),
        instances=tuple(i for i in state.all(ItemInstance) if i.item == item),
        unreconciled=tuple(u for u in state.all(UnreconciledHolding) if u.item == item),
    )


def slots_needed(quantity: int, units_per_slot: int) -> int:
    """Fewest slots that hold `quantity`: exact once stacks are merged, a minimum otherwise."""
    return -(-quantity // units_per_slot)


@dataclass(frozen=True, slots=True)
class SlotMath:
    """Slots at one location implied by item counts. `implied` covers stacks whose slot count
    is known (recorded, or derived from quantity and stack size with merged stacks). Each tracked
    piece is one slot, except a mod attached to a weapon, which rides in the weapon's slot."""

    implied: int
    counter: int | None
    without_stack_size: tuple[Item, ...]
    without_count: tuple[Item, ...]
    unreconciled_rows: int

    @property
    def complete(self) -> bool:
        return not (self.without_stack_size or self.without_count or self.unreconciled_rows)


def slot_math(state: State, location: Location) -> SlotMath:
    limits = {s.item.id: s.units_per_slot for s in state.all(StackSize)}
    implied = 0
    no_limit: list[Item] = []
    no_count: list[Item] = []
    for h in state.all(Holding):
        if h.location is not location or h.quantity == 0:
            continue
        if h.quantity is None:
            no_count.append(h.item)
        elif h.slots is not None:
            implied += h.slots
        elif (limit := limits.get(h.item.id)) is not None:
            implied += slots_needed(h.quantity, limit)
        else:
            no_limit.append(h.item)
    attached = {a.mod.id for a in state.all(WeaponAttachment)}
    implied += sum(
        1 for i in state.all(ItemInstance) if i.location is location and i.id not in attached
    )
    return SlotMath(
        implied=implied,
        counter=state.all(StashCounter)[0].used if location is Location.STASH else None,
        without_stack_size=tuple(no_limit),
        without_count=tuple(no_count),
        unreconciled_rows=len(state.all(UnreconciledHolding)),
    )


def stash_slot_math(state: State) -> SlotMath:
    return slot_math(state, Location.STASH)


def contributed(state: State, goal: Goal, item: Item) -> int:
    """What was already handed in to a project for one requirement (one row per goal and item)."""
    given = state.find(ProjectContribution, (goal.id, item.id))
    return given.quantity if given else 0


def still_needed(state: State, item: Item) -> list[tuple[Goal, int]]:
    """Open goals still short of this item, and by how much."""
    return [
        (req.goal, req.quantity - contributed(state, req.goal, item))
        for req in state.all(GoalRequirement)
        if req.item == item
        and req.goal.status is not GoalStatus.COMPLETE
        and req.quantity > contributed(state, req.goal, item)
    ]


def stash_after(state: State, add: dict[Item, int], remove: dict[Item, int]) -> dict[Item, int]:
    """Stash quantities once a raid's changes land: what came in, minus what left (sold,
    recycled, used, moved out). Uncounted stacks count as zero only if they change."""
    after = {
        h.item: h.quantity
        for h in state.all(Holding)
        if h.location is Location.STASH and h.quantity is not None
    }
    for item, quantity in add.items():
        after[item] = after.get(item, 0) + quantity
    for item, quantity in remove.items():
        after[item] = after.get(item, 0) - quantity
    return after


def metric(state: State, kind: MetricKind) -> int | None:
    found = state.find(AccountMetric, kind.value)
    return None if found is None else found.value


def objective_progress(state: State, objective: Objective) -> int | None:
    if objective.kind is ObjectiveKind.SAVE_COINS:
        return metric(state, MetricKind.COINS)
    return objective.progress


def objective_target(objective: Objective) -> str:
    match objective.kind:
        case ObjectiveKind.DESTROY_ENEMY:
            return objective.enemy.id if objective.enemy else "?"
        case ObjectiveKind.DESTROY_ENEMY_PART:
            return objective.enemy_part.id if objective.enemy_part else "?"
        case ObjectiveKind.DESTROY_WITH_ITEM:
            return f"any ARC with {objective.item.id}" if objective.item else "?"
        case ObjectiveKind.SAVE_COINS:
            return MetricKind.COINS.value


def plan(state: State, goal: Goal) -> GoalPlan:
    """What a goal still needs. Uses stash only; unreconciled loot is shown, never counted."""
    rows: list[Requirement] = []
    for req in (r for r in state.all(GoalRequirement) if r.goal == goal):
        committed = contributed(state, goal, req.item)
        remaining = req.quantity - committed
        held = balance(state, req.item)
        others = sum(
            r.quantity for r in state.all(Reservation) if r.item == req.item and r.goal != goal
        )
        available = None if held.stash is None else max(0, held.stash - others)
        rows.append(
            {
                "item": req.item.id,
                "name": req.item.name,
                "required": req.quantity,
                "committed": committed,
                "remaining": remaining,
                "stash": held.stash,
                "reserved_for_other_goals": others,
                "available": available,
                "missing": None if available is None else max(0, remaining - available),
                "confidence": held.confidence.value,
                "unreconciled_not_counted": held.unreconciled_quantity or None,
            }
        )
    return {
        "goal": goal.id,
        "name": goal.name,
        "status": goal.status.value,
        "blocked_by": [
            d.prerequisite.id
            for d in state.all(GoalDependency)
            if d.goal == goal and d.prerequisite.status is not GoalStatus.COMPLETE
        ],
        "requirements": rows,
        "objectives": [
            {
                "id": o.id,
                "kind": o.kind.value,
                "target": objective_target(o),
                "required": o.required,
                "progress": objective_progress(state, o),
            }
            for o in state.all(Objective)
            if o.goal == goal
        ],
    }


def open_questions(state: State) -> list[OpenQuestion]:
    return [q for q in state.all(OpenQuestion) if q.status is QuestionStatus.OPEN]
