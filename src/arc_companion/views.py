"""Compact packets for a conversation. Each is a projection of the graph; none stores anything."""

from __future__ import annotations

from collections import defaultdict

from .checks import run
from .enums import (
    DispositionAction,
    GoalStatus,
    ItemCategory,
    Location,
    MetricKind,
    Severity,
    SourceKind,
)
from .model import (
    DispositionRule,
    Goal,
    GoalRequirement,
    Holding,
    Item,
    ItemInstance,
    ItemValue,
    Objective,
    PlayerBuild,
    Preference,
    RecipeInput,
    Reservation,
    SkillRank,
    Source,
    StackSize,
    StashCounter,
    UnreconciledHolding,
    WeaponAttachment,
)
from .packets import (
    Bootstrap,
    CountCheckRow,
    DebriefRow,
    Expected,
    GoalLine,
    ItemPacket,
    LoadoutRow,
    SlotChange,
)
from .queries import (
    balance,
    metric,
    open_questions,
    plan,
    recounted_after,
    slots_needed,
    stash_after,
    stash_slot_math,
    still_needed,
)
from .reference import SCRAPPY_FOODS
from .store import State


def _active_goals(state: State) -> list[Goal]:
    goals = [g for g in state.all(Goal) if g.status is GoalStatus.ACTIVE]
    return sorted(goals, key=lambda g: (g.priority is None, g.priority or 0, g.id))


def bootstrap(state: State) -> Bootstrap:
    """First call of every session: exact current state plus what is unproven."""
    stash = state.all(StashCounter)[0]
    build = state.all(PlayerBuild)[0]
    observed = [s for s in state.all(Source) if s.kind is not SourceKind.MIGRATION]
    latest = max(observed, key=lambda s: s.seq)
    findings = run(state)
    slots = stash_slot_math(state)
    return {
        "as_of": {"source": latest.id, "date": latest.observed_on.isoformat()},
        "stash": {
            "used": stash.used,
            "capacity": stash.capacity,
            "free": stash.free,
            "confidence": stash.confidence.value,
            "slot_math": {
                "implied_by_counts": slots.implied,
                "complete": slots.complete,
                "items_without_stack_size": len(slots.without_stack_size),
                "items_without_count": len(slots.without_count),
            },
        },
        "coins": metric(state, MetricKind.COINS),
        "build": {
            "level": build.level,
            "mobility": build.mobility_points,
            "conditioning": build.conditioning_points,
            "survival": build.survival_points,
            "unspent": build.unspent_points,
            "skills": {s.name: s.rank for s in state.all(SkillRank)},
        },
        "preferences": {p.id.value: p.value for p in state.all(Preference)},
        "active_goals": [_goal_line(state, g) for g in _active_goals(state)],
        "unproven": {
            "unreconciled_rows": len(state.all(UnreconciledHolding)),
            "open_questions": len(open_questions(state)),
            "next_step": "arc count-check" if state.all(UnreconciledHolding) else None,
        },
        "findings": [f"{f.severity}: [{f.rule}] {f.message}" for f in findings],
    }


def _goal_line(state: State, goal: Goal) -> GoalLine:
    p = plan(state, goal)
    requirements = p["requirements"]
    return {
        "goal": goal.id,
        "name": goal.name,
        "priority": goal.priority,
        "blocked_by": p["blocked_by"],
        "short": {r["item"]: r["missing"] for r in requirements if r["missing"] != 0},
        "objectives": p["objectives"],
    }


def count_check(state: State) -> list[CountCheckRow]:
    """Items whose real count is unproven, most decision-relevant first.

    One live stash count per item (plus the claimed slot's count) closes every row for it.
    """
    by_item: dict[Item, list[UnreconciledHolding]] = defaultdict(list)
    for row in state.all(UnreconciledHolding):
        by_item[row.item].append(row)
    needed_by = defaultdict(list)
    for req in state.all(GoalRequirement):
        if req.goal.status in (GoalStatus.ACTIVE, GoalStatus.BLOCKED):
            needed_by[req.item].append(req.goal.id)
    reserved = {r.item for r in state.all(Reservation)}
    packets: list[CountCheckRow] = []
    for item, rows in by_item.items():
        held = balance(state, item)
        locations = sorted({r.claimed_location for r in rows})
        flags = " ".join(f"--{loc.value.replace('_', '-')} N" for loc in locations)
        packets.append(
            {
                "item": item.id,
                "name": item.name,
                "recorded_stash": held.stash,
                "unreconciled": held.unreconciled_quantity,
                "rows": len(rows),
                "claimed_in": [loc.value for loc in locations],
                "rows_followed_by_stash_count": sum(recounted_after(state, r) for r in rows),
                "active_goals": needed_by.get(item, []),
                "reserved": item in reserved,
                "command": f'arc reconcile "{item.name}" --stash N {flags} --note "..."',
            }
        )
    return sorted(
        packets,
        key=lambda p: (not p["active_goals"], not p["reserved"], -(p["unreconciled"] or 0)),
    )


def item_packet(state: State, item: Item) -> ItemPacket:
    held = balance(state, item)
    stack = state.find(StackSize, item.id)
    return {
        "item": item.id,
        "name": item.name,
        "category": item.category.value,
        "stack_size": None if stack is None else stack.units_per_slot,
        "stack_size_source": None if stack is None else stack.source.kind.value,
        "family": item.family.id if item.family else None,
        "confirmed_total": held.confirmed,
        "stash": held.stash,
        "confidence": held.confidence.value,
        "holdings": [
            {"location": h.location.value, "quantity": h.quantity, "source": h.source.id}
            for h in held.holdings
        ],
        "instances": [
            {
                "id": i.id,
                "location": i.location.value,
                "condition": None if i.condition is None else f"{i.condition}/{i.condition_max}",
            }
            for i in held.instances
        ],
        "unreconciled_not_counted": [
            {
                "claimed_in": u.claimed_location.value,
                "quantity": u.quantity,
                "raid": u.raid_report.id if u.raid_report else None,
                "stash_recounted_after": recounted_after(state, u),
            }
            for u in held.unreconciled
        ],
        "goals": sorted({r.goal.id for r in state.all(GoalRequirement) if r.item == item}),
    }


def loadout(state: State) -> list[LoadoutRow]:
    carried = (
        Location.EQUIPMENT,
        Location.BACKPACK,
        Location.QUICK_USE,
        Location.SAFE_POCKET,
        Location.CARRIED,
    )
    rows: list[LoadoutRow] = []
    attached = {a.mod.id for a in state.all(WeaponAttachment)}  # mods ride in their weapon's slot
    for i in state.all(ItemInstance):
        if i.location in carried and i.id not in attached:
            rows.append(
                {"location": i.location.value, "item": i.item.name, "quantity": 1, "piece": i.id}
            )
    for item in state.all(Item):
        for h in balance(state, item).holdings:
            if h.location in carried and h.quantity != 0:
                rows.append(
                    {
                        "location": h.location.value,
                        "item": item.name,
                        "quantity": h.quantity or 0,
                        "piece": None,
                    }
                )
    return sorted(rows, key=lambda r: (r["location"], r["item"]))


def audit(state: State) -> tuple[bool, list[str]]:
    findings = run(state)
    ok = not any(f.severity is Severity.ERROR for f in findings)
    lines = [f"{f.severity.upper():5} [{f.rule}] {f.message}" for f in findings]
    return ok, lines or ["clean"]


# Ammo, healing, grenades and deployables are carried, not stockpiled for crafting.
_RAID_SUPPLY = {ItemCategory.AMMUNITION, ItemCategory.QUICK_USE}
# Gear is a decision about a specific piece (durability, mods, plans), not a stack to trim.
_GEAR = {
    ItemCategory.WEAPON,
    ItemCategory.AUGMENT,
    ItemCategory.SHIELD,
    ItemCategory.MOD,
    ItemCategory.BLUEPRINT,
    ItemCategory.KEY,
}


def _goal_need(state: State, item: Item) -> tuple[int, list[str]]:
    short = still_needed(state, item)
    return sum(n for _, n in short), [f"{goal.id} ({n})" for goal, n in short]


def debrief(state: State, haul: dict[Item, int]) -> list[DebriefRow]:
    """Keep, sell or decide for each item: goals first, then the player's standing rules, then
    one full stack of anything a recipe uses. With an empty haul, the whole stash is judged."""
    if not haul:
        haul = {
            h.item: 0 for h in state.all(Holding) if h.location is Location.STASH and h.quantity
        }
    rules = {r.item.id: r for r in state.all(DispositionRule)}
    uses: dict[str, int] = defaultdict(int)
    for line in state.all(RecipeInput):
        uses[line.item.id] += 1
    rows: list[DebriefRow] = []
    for item, got in haul.items():
        after = (balance(state, item).stash or 0) + got
        need, goals = _goal_need(state, item)
        rule = rules.get(item.id)
        stack = state.find(StackSize, item.id)
        value = state.find(ItemValue, item.id)
        one_stack = stack.units_per_slot if stack and uses[item.id] else 0
        quest = next(
            (
                o.goal.id
                for o in state.all(Objective)
                if o.item == item and o.goal.status is not GoalStatus.COMPLETE
            ),
            None,
        )
        if quest is not None:
            keep, why = after, f"quest {quest} uses it"
        elif item.category in _GEAR:
            keep, why = after, "gear: decide on the piece"
        elif rule is not None and rule.action is DispositionAction.HOLD:
            keep, why = after, "your standing rule: hold"
        elif rule is not None:
            keep, why = max(need, rule.keep_total), f"your rule: keep {rule.keep_total}"
        elif item.category is ItemCategory.BASIC_MATERIAL:
            keep, why = after, "basic material: feeds most crafting"
        elif item.category in _RAID_SUPPLY:
            keep, why = after, "raid supply: you choose how many to carry"
        elif item.id in SCRAPPY_FOODS:
            keep, why = after, f"Scrappy food: +5 {SCRAPPY_FOODS[item.id]} when eaten"
        elif need and need >= one_stack:
            keep, why = need, "goals need it"
        elif one_stack:
            keep, why = max(need, one_stack), f"one stack; {uses[item.id]} recipes use it"
        elif item.category is ItemCategory.TRINKET:
            keep, why = 0, "a trinket: it only sells"
        else:
            # Unknown use is not no use (A2): quests, projects and research are not all
            # recorded, so the player checks before it goes.
            keep, why = 0, "no recorded use; check quests, projects and research before selling"
        keep = min(after, max(keep, need))
        surplus = max(0, after - keep)
        move = rule.action.value if rule and rule.action is not DispositionAction.HOLD else "sell"
        if why.startswith("no recorded use"):
            move = "check"
        slots_after = slots_needed(after, stack.units_per_slot) if stack and after else None
        slots_kept = slots_needed(keep, stack.units_per_slot) if stack and keep else 0
        rows.append(
            {
                "item": item.name,
                "haul": got,
                "stash_after": after,
                "needed_by": goals,
                "decision": f"{move} {surplus}, keep {keep}" if surplus else "keep",
                "why": why,
                "coins_if_sold": surplus * value.coins if value and surplus else None,
                "slots_freed": (slots_after or 0) - slots_kept if surplus and slots_after else 0,
                "your_call": None,
            }
        )
    return sorted(rows, key=lambda r: (r["decision"] == "keep", -(r["coins_if_sold"] or 0)))


def debrief_markdown(rows: list[DebriefRow]) -> str:
    head = (
        "| Item | Haul | Stash after | Needed by | Decision | Why | Coins | Slots freed "
        "| Your call |"
    )
    lines = [head, "|" + "---|" * 9]
    for r in rows:
        needed = ", ".join(r["needed_by"]) or "—"
        coins = f"{r['coins_if_sold']:,}" if r["coins_if_sold"] else "—"
        lines.append(
            f"| {r['item']} | {r['haul']} | {r['stash_after']} | {needed} | {r['decision']} | "
            f"{r['why']} | {coins} | {r['slots_freed'] or '—'} | ? |"
        )
    return "\n".join(lines)


def expected(
    state: State, add: dict[Item, int], remove: dict[Item, int], sell: dict[Item, int]
) -> Expected:
    """What the stash counter and coins should read after a raid's unload, sales and moves.

    Conservation as a check: before + changes = after. The player reads the real counter and
    coins; any difference is a missing input (an unmentioned pickup, a sale at another price).
    Merged stacks are assumed, as the stocktake does.
    """
    removed = dict(remove)
    for item, quantity in sell.items():
        removed[item] = removed.get(item, 0) + quantity
    after = stash_after(state, add, removed)
    counter = state.all(StashCounter)[0].used
    slot_delta = 0
    rows: list[SlotChange] = []
    unknown: list[str] = []
    for item in {*add, *removed}:
        before = balance(state, item).stash or 0
        stack = state.find(StackSize, item.id)
        if after[item] < 0:
            unknown.append(f"{item.name}: would go negative ({after[item]})")
            continue
        if stack is None:
            unknown.append(f"{item.name}: no stack size")
            continue
        was = slots_needed(before, stack.units_per_slot) if before else 0
        now = slots_needed(after[item], stack.units_per_slot) if after[item] else 0
        slot_delta += now - was
        if now != was:
            rows.append(
                {"item": item.name, "before": before, "after": after[item], "slots": now - was}
            )
    coins = metric(state, MetricKind.COINS)
    earned, unpriced = 0, []
    for item, quantity in sell.items():
        value = state.find(ItemValue, item.id)
        if value is None:
            unpriced.append(item.name)
        else:
            earned += value.coins * quantity
    return {
        "counter_now": counter,
        "counter_expected": counter + slot_delta,
        "slot_changes": sorted(rows, key=lambda r: r["item"]),
        "coins_now": coins,
        "coins_expected": None if coins is None else coins + earned,
        "sale_prices": "recorded item values; worn gear sells for less",
        "unpriced_sales": unpriced,
        "unknown": unknown,
    }
