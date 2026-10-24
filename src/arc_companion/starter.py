"""A clean starting profile for a new player: game facts kept, one player's save state left out.

Reference tables are copied whole. Everything that describes what a player owns, did or
decided is left out, except the singletons a profile needs (stash counter, build), which start
at a new player's values. Sources that came from a player's words keep their kind and date but
lose their text, which can describe that player's stash. Starter goals are added from the
Workshop page, so a new player can plan bench upgrades and backup weapons from day one."""

from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass

from .enums import Confidence, GoalStatus, SourceKind
from .model import (
    Alias,
    AugmentCapacity,
    CombatWeapon,
    Companion,
    Enemy,
    EnemyPart,
    Entity,
    GameMap,
    Goal,
    GoalDependency,
    GoalRequirement,
    Item,
    ItemFamily,
    ItemValue,
    MapEncounter,
    Matchup,
    ModFit,
    PlayerBuild,
    Preference,
    Recipe,
    RecipeInput,
    RecycleYield,
    RewardOrder,
    ScrappyRate,
    SkillRank,
    Source,
    StackSize,
    StashCounter,
    Station,
    WeaponProfile,
)
from .queries import resolve
from .store import COLUMNS, State, key_of

REFERENCE: tuple[type[Entity], ...] = (
    ItemFamily,
    Item,
    Alias,
    Station,
    Recipe,
    RecipeInput,
    RecycleYield,
    ItemValue,
    StackSize,
    AugmentCapacity,
    ScrappyRate,
    WeaponProfile,
    ModFit,
    CombatWeapon,
    GameMap,
    Enemy,
    EnemyPart,
    Matchup,
    MapEncounter,
    SkillRank,
    Companion,
    RewardOrder,
)


PUBLIC_SOURCES = {SourceKind.WEB, SourceKind.WEB_REFERENCE}


# Stand-ins one player's tracker created for things not yet identified. Not game items.
PLACEHOLDERS = frozenset(
    {
        "angled_grip_tier_unknown",
        "arc_item_segregatory_unidentified",
        "bandage_type_unconfirmed",
        "little_smoke_grenade_verify_exact_name",
        "renegade_looted_tier_unknown",
        "stitcher_looted_tier_unknown",
        "table_design_name_unconfirmed",
        "unidentified_mods",
        "unidentified_stencil_part",
    }
)


# The day the starter's own facts below were read. A source is dated by its reading, never by
# the export, so re-publishing leaves provenance (and the starter's diff) unchanged.
READ_ON = dt.date(2026, 10, 23)

WORKSHOP = "https://arcraiders.wiki/wiki/Workshop (edited 2026-10-10, after Frozen Trail 2.0)"


STASH = "https://arcraiders.wiki/wiki/Stash: 64 slots at level 1"


STARTED = "Starter profile defaults; edit to taste with arc set-preference"


REFINER_III = (
    "In-game Refiner III upgrade, read by a player on 2026-10-23: 3 Motor, 10 ARC Circuitry, "
    "6 Bombardier Cell, and no Outpost requirement (the Workshop wiki page says it needs one)"
)


# Goals whose costs a player read in game; the reading outranks the wiki.
PLAYER_READ = frozenset({"refiner_3"})


# (goal id, name, station, level, requirements by item name) from the Workshop page.
BENCH_LEVELS: tuple[tuple[str, str, str, int, dict[str, int]], ...] = (
    ("gunsmith_1", "Gunsmith I", "gunsmith", 1, {"Metal Parts": 20, "Rubber Parts": 30}),
    (
        "gunsmith_2",
        "Gunsmith II",
        "gunsmith",
        2,
        {"Rusted Tools": 3, "Mechanical Components": 5, "Wasp Driver": 8},
    ),
    (
        "gunsmith_3",
        "Gunsmith III",
        "gunsmith",
        3,
        {"Rusted Gear": 3, "Advanced Mechanical Components": 5, "Sentinel Firing Core": 4},
    ),
    ("gear_bench_1", "Gear Bench I", "gear_bench", 1, {"Plastic Parts": 25, "Fabric": 30}),
    (
        "gear_bench_2",
        "Gear Bench II",
        "gear_bench",
        2,
        {"Power Cable": 3, "Electrical Components": 5, "Hornet Driver": 5},
    ),
    (
        "gear_bench_3",
        "Gear Bench III",
        "gear_bench",
        3,
        {"Industrial Battery": 3, "Advanced Electrical Components": 5, "Bastion Cell": 6},
    ),
    ("medical_lab_1", "Medical Lab I", "medical_lab", 1, {"Fabric": 50, "ARC Alloy": 6}),
    (
        "medical_lab_2",
        "Medical Lab II",
        "medical_lab",
        2,
        {"Cracked Bioscanner": 2, "Durable Cloth": 5, "Tick Pod": 8},
    ),
    (
        "medical_lab_3",
        "Medical Lab III",
        "medical_lab",
        3,
        {"Rusted Shut Medical Kit": 3, "Antiseptic": 8, "Surveyor Vault": 5},
    ),
    ("explosives_1", "Explosives Station I", "explosives", 1, {"Chemicals": 50, "ARC Alloy": 6}),
    (
        "explosives_2",
        "Explosives Station II",
        "explosives",
        2,
        {"Synthesized Fuel": 3, "Crude Explosives": 5, "Pop Trigger": 5},
    ),
    (
        "explosives_3",
        "Explosives Station III",
        "explosives",
        3,
        {"Laboratory Reagents": 3, "Explosive Compound": 5, "Rocketeer Driver": 3},
    ),
    ("utility_1", "Utility Station I", "utility", 1, {"Plastic Parts": 50, "ARC Alloy": 6}),
    (
        "utility_2",
        "Utility Station II",
        "utility",
        2,
        {"Damaged Heat Sink": 2, "Electrical Components": 5, "Snitch Scanner": 6},
    ),
    (
        "utility_3",
        "Utility Station III",
        "utility",
        3,
        {"Fried Motherboard": 3, "Advanced Electrical Components": 5, "Leaper Pulse Unit": 4},
    ),
    ("refiner_1", "Refiner I", "refiner", 1, {"Metal Parts": 60, "ARC Powercell": 5}),
    (
        "refiner_2",
        "Refiner II",
        "refiner",
        2,
        {"Toaster": 3, "ARC Motion Core": 5, "Fireball Burner": 8},
    ),
    (
        "refiner_3",
        "Refiner III",
        "refiner",
        3,
        {"Motor": 3, "ARC Circuitry": 10, "Bombardier Cell": 6},
    ),
)


# Backup weapons: cheap guns kept ready so a death never leaves the next raid unarmed.
BACKUP_KITS: tuple[tuple[str, str, str], ...] = (
    ("backup_ferro_i", "Backup kit: materials for one Ferro I", "ferro_i"),
    ("backup_rattler_i", "Backup kit: materials for one Rattler I", "rattler_i"),
)


def _scrub(source: Source, number: int) -> Source:
    """A neutral id (original ids can encode a player's coins or stash), and no private text."""
    reference = source.reference
    if source.kind not in PUBLIC_SOURCES:
        reference = f"{source.kind} recorded by the companion's original player"
    return dataclasses.replace(source, id=f"src_{number:04d}", reference=reference)


def _repoint(entity: Entity, sources: dict[str, Source]) -> Entity:
    changes = {
        col.field: sources[value.id]
        for col in COLUMNS[type(entity)]
        if isinstance(value := getattr(entity, col.field), Source) and value.id in sources
    }
    return dataclasses.replace(entity, **changes) if changes else entity


def _without_dangling(entities: list[Entity]) -> list[Entity]:
    """Drop placeholders, then anything that points at a dropped or uncopied row, until stable
    (a recipe for a placeholder takes its input lines with it)."""
    kept = [e for e in entities if not _mentions_placeholder(e)]
    while True:
        present = {(type(e), key_of(e)) for e in kept}
        survivors = [
            e
            for e in kept
            if all(
                (type(v), key_of(v)) in present
                for col in COLUMNS[type(e)]
                if col.is_ref
                and (v := getattr(e, col.field)) is not None
                and not isinstance(v, Source)
            )
        ]
        if len(survivors) == len(kept):
            return kept
        kept = survivors


def _mentions_placeholder(entity: Entity) -> bool:
    if isinstance(entity, Item):
        return entity.id in PLACEHOLDERS
    return any(
        isinstance(value := getattr(entity, col.field), Item) and value.id in PLACEHOLDERS
        for col in COLUMNS[type(entity)]
    )


def _sources_of(entity: Entity) -> list[Source]:
    return [
        value
        for col in COLUMNS[type(entity)]
        if isinstance(value := getattr(entity, col.field), Source)
    ]


def _fresh(entity: Entity, workshop: Source, defaults: Source) -> Entity:
    """Reset the parts of a reference row that describe one player's progress."""
    if isinstance(entity, Station):
        level = 1 if entity.id == "workbench" else 0  # the Workbench is free
        return dataclasses.replace(entity, level=level, source=workshop)
    if isinstance(entity, Companion):
        return dataclasses.replace(entity, level=1, source=workshop)  # Scrappy starts at I
    if isinstance(entity, SkillRank):
        return dataclasses.replace(
            entity, rank=None, confidence=Confidence.UNKNOWN, source=defaults, note=None
        )
    return entity


def build_starter(state: State) -> State:
    starter = State()
    kept = _without_dangling([e for cls in REFERENCE for e in state.all(cls)])
    used = {s.id: s for e in kept for s in _sources_of(e)}
    seq = max(s.seq for s in state.all(Source))

    def new_source(source_id: str, kind: SourceKind, reference: str) -> Source:
        nonlocal seq
        seq += 1
        return Source(id=source_id, seq=seq, kind=kind, observed_on=READ_ON, reference=reference)

    renamed: dict[str, Source] = {}
    for source in sorted(used.values(), key=lambda s: s.seq):
        if not source.id.startswith("starter_"):  # re-created below, so a starter re-exports
            renamed[source.id] = _scrub(source, len(renamed) + 1)
            starter.add(renamed[source.id])
    workshop = new_source("starter_workshop", SourceKind.WEB, WORKSHOP)
    stash = new_source("starter_stash", SourceKind.WEB, STASH)
    defaults = new_source("starter_defaults", SourceKind.USER_PREFERENCE, STARTED)
    refiner = new_source("starter_refiner_iii", SourceKind.USER_REPORT, REFINER_III)
    for source in (workshop, stash, defaults, refiner):
        starter.add(source)

    for entity in kept:
        starter.add(_fresh(_repoint(entity, renamed), workshop, defaults))
    starter.replace_references()

    starter.add(
        StashCounter(id="stash", used=0, capacity=64, confidence=Confidence.UNKNOWN, source=stash)
    )
    starter.add(
        PlayerBuild(
            id="player",
            level=1,
            mobility_points=None,
            conditioning_points=None,
            unspent_points=0,
            reset_cost_coins=None,
            source=defaults,
        )
    )
    _add_starter_goals(starter, workshop, refiner)
    return starter


def _goal(state: State, goal_id: str, name: str, priority: int, source: Source) -> Goal:
    goal = Goal(id=goal_id, name=name, status=GoalStatus.ACTIVE, priority=priority, source=source)
    state.add(goal)
    return goal


def _add_starter_goals(state: State, workshop: Source, player_read: Source) -> None:
    """Every bench to II before any to III; backup weapons right after Gunsmith I."""
    by_id: dict[str, Goal] = {}
    for goal_id, name, _station, level, requirements in BENCH_LEVELS:
        source = player_read if goal_id in PLAYER_READ else workshop
        goal = _goal(state, goal_id, name, level * 10, source)
        by_id[goal_id] = goal
        for item_name, quantity in requirements.items():
            item = resolve(state, item_name)
            state.add(GoalRequirement(goal=goal, item=item, quantity=quantity))
        if level > 1:
            previous = by_id[goal_id[:-1] + str(level - 1)]
            state.add(GoalDependency(goal=goal, prerequisite=previous))
    for goal_id, name, recipe_id in BACKUP_KITS:
        recipe = state.get(Recipe, recipe_id)
        goal = _goal(state, goal_id, name, 15, recipe.source)
        for line in state.all(RecipeInput):
            if line.recipe == recipe:
                state.add(GoalRequirement(goal=goal, item=line.item, quantity=line.quantity))
        state.add(GoalDependency(goal=goal, prerequisite=by_id["gunsmith_1"]))


# Rows that record a player's progress or choices: a starter update only adds missing ones.
PLAYER_OWNED: tuple[type[Entity], ...] = (Station, SkillRank, Preference, Companion)


@dataclass
class MergeReport:
    added: int = 0
    updated: int = 0
    kept_yours: list[str] = dataclasses.field(default_factory=list)
    goals_added: list[str] = dataclasses.field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"starter update: {self.added} game facts added, {self.updated} updated, "
            f"{len(self.goals_added)} starter goals added"
        ]
        if self.kept_yours:
            lines.append("kept your own reading for: " + ", ".join(self.kept_yours))
        return "\n".join(lines)


def merge_starter(player: State, starter: State) -> MergeReport:
    """Bring a newer starter's game facts and goals into a player's data.

    A fact the player recorded themselves (any source the starter does not have) is never
    replaced, and their progress (bench levels, skills, preferences) is never reset.
    """
    report = MergeReport()
    starter_sources = {s.id for s in starter.all(Source)}
    seq = max(s.seq for s in player.all(Source))

    def adopt(entity: Entity) -> None:
        nonlocal seq
        for source in _sources_of(entity):
            if player.find(Source, source.id) is None:
                seq += 1
                player.add(dataclasses.replace(source, seq=seq))

    for cls in REFERENCE:
        for fact in starter.all(cls):
            mine = player.find(cls, key_of(fact))
            if mine == fact:
                continue
            if mine is None:
                report.added += 1
            elif isinstance(mine, PLAYER_OWNED):
                continue
            elif any(s.id not in starter_sources for s in _sources_of(mine)):
                report.kept_yours.append(f"{cls.TABLE}:{key_of(fact)}")
                continue
            else:
                report.updated += 1
            adopt(fact)
            player.put(fact)
    for goal in starter.all(Goal):
        if player.find(Goal, goal.id) is not None:
            continue
        adopt(goal)
        player.add(goal)
        report.goals_added.append(goal.id)
        for req in starter.all(GoalRequirement):
            if req.goal == goal:
                player.add(req)
        for dep in starter.all(GoalDependency):
            if dep.goal == goal and player.find(Goal, dep.prerequisite.id) is not None:
                player.add(dep)
    player.replace_references()
    return report
