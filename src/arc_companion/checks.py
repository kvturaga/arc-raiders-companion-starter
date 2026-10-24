"""Named integrity rules over the loaded graph. ERROR blocks a write; WARN is surfaced in audits.

Each rule exists because the failure it describes either happened in the legacy tracker or
is one join away from happening. Add a rule rather than a prose warning.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from .enums import (
    Basis,
    GoalStatus,
    Location,
    MetricKind,
    ObjectiveKind,
    RaidStatus,
    Severity,
)
from .model import (
    AccountMetric,
    Alias,
    AugmentCapacity,
    Feat,
    Goal,
    GoalDependency,
    GoalRequirement,
    Holding,
    Item,
    ItemInstance,
    ItemValue,
    Matchup,
    ModFit,
    Objective,
    PlannedSale,
    PlayerBuild,
    ProjectContribution,
    RaidReport,
    Reservation,
    RewardBatch,
    SkillRank,
    Source,
    StackSize,
    StashCounter,
    UnreconciledHolding,
    WeaponAttachment,
    WeaponProfile,
)
from .queries import balance, recounted_after, slot_math, slots_needed, stash_slot_math
from .store import State


@dataclass(frozen=True, slots=True)
class Finding:
    severity: Severity
    rule: str
    message: str


Rule = Callable[[State], Iterator[Finding]]
RULES: list[Rule] = []


def rule(fn: Rule) -> Rule:
    RULES.append(fn)
    return fn


def _error(name: str, message: str) -> Finding:
    return Finding(Severity.ERROR, name, message)


def _warn(name: str, message: str) -> Finding:
    return Finding(Severity.WARN, name, message)


@rule
def source_order(state: State) -> Iterator[Finding]:
    seqs = [s.seq for s in state.all(Source)]
    if seqs != sorted(seqs) or len(set(seqs)) != len(seqs):
        yield _error("source_order", "sources.csv must be in strictly increasing seq order")


@rule
def one_stack_per_location(state: State) -> Iterator[Finding]:
    counts = Counter((h.item.id, h.location) for h in state.all(Holding))
    for (item, location), n in counts.items():
        if n > 1:
            yield _error("one_stack_per_location", f"{item} has {n} holdings in {location}")


@rule
def single_singletons(state: State) -> Iterator[Finding]:
    for cls in (StashCounter, PlayerBuild):
        if len(state.all(cls)) != 1:
            yield _error("single_singletons", f"{cls.TABLE} must hold exactly one row")


@rule
def stash_counter(state: State) -> Iterator[Finding]:
    for s in state.all(StashCounter):
        if not 0 <= s.used <= s.capacity:
            yield _error("stash_counter", f"stash {s.used}/{s.capacity} is impossible")


@rule
def nonnegative_quantities(state: State) -> Iterator[Finding]:
    for h in state.all(Holding):
        if (h.quantity is not None and h.quantity < 0) or (h.slots is not None and h.slots < 0):
            yield _error("nonnegative_quantities", f"holding {h.id} is negative")
    for u in state.all(UnreconciledHolding):
        if u.quantity is not None and u.quantity < 0:
            yield _error("nonnegative_quantities", f"unreconciled {u.id} is negative")


@rule
def instance_condition(state: State) -> Iterator[Finding]:
    for i in state.all(ItemInstance):
        if (i.condition is None) != (i.condition_max is None) or (
            (i.condition is None) != (i.condition_source is None)
        ):
            yield _error("instance_condition", f"{i.id}: condition fields must be set together")
        elif (
            i.condition is not None
            and i.condition_max is not None
            and not 0 <= i.condition <= i.condition_max
        ):
            yield _error("instance_condition", f"{i.id}: {i.condition}/{i.condition_max}")


@rule
def attachments_fit(state: State) -> Iterator[Finding]:
    fits = {(f.mod.id, f.weapon.id): f for f in state.all(ModFit)}
    slots: Counter[tuple[str, str]] = Counter()
    for a in state.all(WeaponAttachment):
        fit = fits.get((a.mod.item.id, a.weapon.item.id))
        if fit is None:
            yield _error(
                "attachments_fit", f"{a.mod.item.id} has no sourced fit on {a.weapon.item.id}"
            )
        elif fit.slot is not a.slot:
            yield _error("attachments_fit", f"{a.mod.id} attached to {a.slot}, fits {fit.slot}")
        if a.mod.location is not a.weapon.location:
            yield _error("attachments_fit", f"{a.mod.id} is not where its weapon {a.weapon.id} is")
        slots[(a.weapon.id, a.slot)] += 1
    for (weapon, slot), n in slots.items():
        if n > 1:
            yield _error("attachments_fit", f"{weapon} has {n} mods in {slot}")
    profiled = {p.item.id for p in state.all(WeaponProfile)}
    for f in state.all(ModFit):
        if f.weapon.id not in profiled:
            yield _error("attachments_fit", f"mod fit targets {f.weapon.id}, which has no profile")


@rule
def goal_graph(state: State) -> Iterator[Finding]:
    edges = defaultdict(list)
    for d in state.all(GoalDependency):
        edges[d.goal.id].append(d.prerequisite.id)

    def cyclic(node: str, path: frozenset[str]) -> bool:
        return node in path or any(cyclic(n, path | {node}) for n in edges[node])

    for goal in state.all(Goal):
        if cyclic(goal.id, frozenset()):
            yield _error("goal_graph", f"dependency cycle through {goal.id}")


def _required(state: State, goal: Goal, item_id: str) -> int:
    return sum(
        r.quantity for r in state.all(GoalRequirement) if r.goal == goal and r.item.id == item_id
    )


@rule
def contributions(state: State) -> Iterator[Finding]:
    for c in state.all(ProjectContribution):
        if c.quantity > _required(state, c.goal, c.item.id):
            yield _error(
                "contributions", f"{c.goal.id}: {c.item.id} contributed beyond requirement"
            )


@rule
def reservations(state: State) -> Iterator[Finding]:
    """Reservations must match an open requirement and fit inside confirmed stash stock."""
    per_item: Counter[Item] = Counter()
    for r in state.all(Reservation):
        per_item[r.item] += r.quantity
        if r.goal.status is GoalStatus.COMPLETE:
            yield _error("reservations", f"{r.goal.id} is complete but still reserves {r.item.id}")
        if r.quantity > _required(state, r.goal, r.item.id):
            yield _error("reservations", f"{r.goal.id} reserves more {r.item.id} than it needs")
    for item, reserved in per_item.items():
        stash = balance(state, item).stash
        if stash is None or reserved > stash:
            yield _error("reservations", f"{reserved} {item.id} reserved, stash has {stash}")


@rule
def objectives_typed(state: State) -> Iterator[Finding]:
    """Exactly the target field the kind demands is set; savings progress is never stored."""
    expected = {
        ObjectiveKind.DESTROY_ENEMY: "enemy",
        ObjectiveKind.DESTROY_ENEMY_PART: "enemy_part",
        ObjectiveKind.DESTROY_WITH_ITEM: "item",
        ObjectiveKind.SAVE_COINS: None,
    }
    for o in state.all(Objective):
        set_fields = {f for f in ("enemy", "enemy_part", "item") if getattr(o, f) is not None}
        want = expected[o.kind]
        if set_fields != ({want} if want else set()):
            yield _error("objectives_typed", f"{o.id}: {o.kind} needs {want}, has {set_fields}")
        if o.kind is ObjectiveKind.SAVE_COINS and o.progress is not None:
            yield _error("objectives_typed", f"{o.id}: savings progress comes from the coin metric")
        if o.progress is not None and o.progress > o.required:
            yield _error("objectives_typed", f"{o.id}: progress {o.progress} > {o.required}")
    saving = any(o.kind is ObjectiveKind.SAVE_COINS for o in state.all(Objective))
    if saving and state.find(AccountMetric, MetricKind.COINS.value) is None:
        yield _error("objectives_typed", "a savings objective exists but coins are unrecorded")


@rule
def bounded_progress(state: State) -> Iterator[Finding]:
    for s in state.all(SkillRank):
        if s.rank is not None and s.maximum is not None and s.rank > s.maximum:
            yield _error("bounded_progress", f"skill {s.id} rank {s.rank} > {s.maximum}")
    for f in state.all(Feat):
        if f.progress is not None and f.required is not None and f.progress > f.required:
            yield _error("bounded_progress", f"feat {f.id} {f.progress} > {f.required}")
    for b in state.all(RewardBatch):
        if b.rounds is not None and b.rounds > b.companion.round_capacity:
            yield _error("bounded_progress", f"reward batch {b.id} exceeds companion capacity")


@rule
def inference_labeled(state: State) -> Iterator[Finding]:
    for m in state.all(Matchup):
        if m.basis is not Basis.TACTICAL_INFERENCE:
            yield _error(
                "inference_labeled",
                f"matchup {m.weapon.id}/{m.enemy.id}: rankings are inference until measured",
            )


@rule
def one_price_per_item(state: State) -> Iterator[Finding]:
    """A sale price stored twice drifts; the planned sale must agree with the item value."""
    values = {v.item.id: v.coins for v in state.all(ItemValue)}
    for p in state.all(PlannedSale):
        if p.item.id in values and values[p.item.id] != p.unit_coins:
            yield _error(
                "one_price_per_item", f"{p.id}: {p.unit_coins} vs value {values[p.item.id]}"
            )


@rule
def unreconciled_loot(state: State) -> Iterator[Finding]:
    rows = state.all(UnreconciledHolding)
    if rows:
        absorbed = sum(recounted_after(state, u) for u in rows)
        items = len({u.item.id for u in rows})
        yield _warn(
            "unreconciled_loot",
            f"{len(rows)} recorded quantities across {items} items have no established location "
            f"({absorbed} were followed by a fresh stash count). Run `arc count-check`.",
        )
    for r in state.all(RaidReport):
        if r.status is RaidStatus.RECONCILED and any(u.raid_report == r for u in rows):
            yield _error("unreconciled_loot", f"{r.id} is reconciled but still has open loot")


@rule
def carried_locations_sane(state: State) -> Iterator[Finding]:
    """No fixed capacities are asserted (augment-dependent, not yet sourced); flag only
    duplicates of an item between `carried` and a specific carried slot."""
    carried = {
        h.item.id for h in state.all(Holding) if h.location is Location.CARRIED and h.quantity
    }
    specific = (Location.BACKPACK, Location.QUICK_USE, Location.SAFE_POCKET, Location.EQUIPMENT)
    for h in state.all(Holding):
        if h.location in specific and h.item.id in carried and h.quantity:
            yield _warn(
                "carried_locations_sane",
                f"{h.item.id} has an undivided carried total and also {h.quantity} in {h.location}",
            )


@rule
def unique_names(state: State) -> Iterator[Finding]:
    """A spoken name resolves to one item; two items sharing a name or alias make it ambiguous."""
    owners: defaultdict[str, set[str]] = defaultdict(set)
    for i in state.all(Item):
        owners[i.name.casefold()].add(i.id)
    for a in state.all(Alias):
        owners[a.alias.casefold()].add(a.item.id)
    for name, ids in owners.items():
        if len(ids) > 1:
            yield _error("unique_names", f"{name!r} names {', '.join(sorted(ids))}")


@rule
def stack_physics(state: State) -> Iterator[Finding]:
    """A slot holds at least one unit and at most the item's stack size (C4). With merged
    stacks and every stash item counted, the counts must reproduce the stash counter."""
    limits = {}
    for s in state.all(StackSize):
        limits[s.item.id] = s.units_per_slot
        if s.units_per_slot < 1:
            yield _error("stack_physics", f"{s.item.id}: stack size {s.units_per_slot}")
    for h in state.all(Holding):
        if h.quantity is None or h.slots is None:
            continue
        if h.slots > h.quantity:
            yield _error("stack_physics", f"{h.id}: {h.slots} slots cannot hold {h.quantity}")
        limit = limits.get(h.item.id)
        if limit and h.slots < slots_needed(h.quantity, limit):
            yield _error(
                "stack_physics",
                f"{h.id}: {h.quantity} at {limit} per slot needs "
                f"{slots_needed(h.quantity, limit)} slots, recorded {h.slots}",
            )
    math = stash_slot_math(state)
    if math.complete and math.implied != math.counter:
        yield _warn(
            "stack_physics",
            f"stash counts imply {math.implied} slots, counter shows {math.counter}: "
            "an unmerged stack, a missed item or a stale count",
        )


_CARRY = (Location.BACKPACK, Location.QUICK_USE, Location.SAFE_POCKET)


@rule
def loadout_capacity(state: State) -> Iterator[Finding]:
    """The equipped augment caps the backpack, quick use and safe pocket (C2)."""
    caps = {c.item.id: c for c in state.all(AugmentCapacity)}
    worn = {
        h.item.id for h in state.all(Holding) if h.location is Location.EQUIPMENT and h.quantity
    }
    worn |= {i.item.id for i in state.all(ItemInstance) if i.location is Location.EQUIPMENT}
    equipped = [caps[i] for i in worn if i in caps]
    if len(equipped) > 1:
        yield _error("loadout_capacity", f"{len(equipped)} augments equipped")
        return
    if not equipped:
        return
    cap = equipped[0]
    limits = {
        Location.BACKPACK: cap.backpack_slots,
        Location.QUICK_USE: cap.quick_use_slots,
        Location.SAFE_POCKET: cap.safe_pocket_slots,
    }
    for location in _CARRY:
        carried = slot_math(state, location)
        used = None if carried.without_stack_size or carried.without_count else carried.implied
        if used is not None and used > limits[location]:
            yield _error(
                "loadout_capacity",
                f"{location} holds {used} stacks; {cap.item.name} allows {limits[location]}",
            )


def run(state: State) -> list[Finding]:
    return [finding for check in RULES for finding in check(state)]


def errors(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity is Severity.ERROR]
