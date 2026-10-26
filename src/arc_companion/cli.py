"""`arc` command line. Reads print JSON packets; writes go through commands.apply.

Every command is declared once, next to its handler, with `@reader`, `@writer` or `@action`;
the parser is built from that registry. Writers get `--note`, `--actor` and `--no-commit`.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import commands, views
from .checks import errors, run
from .distribution import STARTER_REPO, check_update, export, init, take_update
from .enums import (
    ActionKind,
    DispositionAction,
    GoalStatus,
    ItemCategory,
    Location,
    MetricKind,
    ModSlot,
    PreferenceKey,
    SourceKind,
    WeaponType,
)
from .model import Goal, Item
from .queries import open_questions, plan, resolve, stash_after
from .reference import read_dataset
from .store import LoadError, State, ensure_tables, load, recover, write_lock

PROJECT = Path(__file__).resolve().parents[2]

Arg = tuple[tuple[str, ...], dict[str, Any]]


def arg(*flags: str, **options: Any) -> Arg:
    return flags, options


@dataclass(frozen=True, slots=True)
class Command:
    name: str
    help: str
    args: tuple[Arg, ...]
    run: Callable[[argparse.Namespace], None]


COMMANDS: dict[str, Command] = {}


def _register(name: str, help: str, args: tuple[Arg, ...], run: Callable[..., None]) -> None:
    if name in COMMANDS:
        raise ValueError(f"command {name} declared twice")
    COMMANDS[name] = Command(name, help, args, run)


def action(
    name: str, help: str, *args: Arg
) -> Callable[[Callable[..., None]], Callable[..., None]]:
    """A command that does its own output (git, files)."""

    def register(fn: Callable[[argparse.Namespace], None]) -> Callable[..., None]:
        _register(name, help, args, fn)
        return fn

    return register


def reader(name: str, help: str, *args: Arg) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """A read: `fn(state, args)` returns a packet, printed as JSON."""

    def register(fn: Callable[[State, argparse.Namespace], Any]) -> Callable[..., Any]:
        _register(name, help, args, lambda a: _emit(fn(_state(a), a)))
        return fn

    return register


def writer(
    name: str, help: str, *args: Arg, kind: SourceKind = SourceKind.USER_REPORT
) -> Callable[[Callable[..., commands.Change]], Callable[..., commands.Change]]:
    """A write: `fn(args)` returns a Change, applied as one sourced, checked transaction."""

    def register(fn: Callable[[argparse.Namespace], commands.Change]) -> Callable[..., Any]:
        def run_write(a: argparse.Namespace) -> None:
            summary = commands.apply(
                a.project, a.note, a.actor, fn(a), commit=not a.no_commit, kind=kind
            )
            _emit({"applied": summary})

        _register(name, help, (*args, *_WRITE_ARGS), run_write)
        return fn

    return register


# --- shared parsing ---------------------------------------------------------------------------


def _emit(payload: Any) -> None:
    print(json.dumps(payload, indent=2, default=str))


def _state(args: argparse.Namespace) -> State:
    root = commands.data_dir(args.project)
    if not root.exists():  # a crash mid-save; finish it under the lock before reading
        with write_lock(args.project):
            recover(root)
    return load(root)


def _stack_pair(raw: str) -> tuple[str, int]:
    name, sep, units = raw.rpartition("=")
    if not sep or not name.strip():
        raise argparse.ArgumentTypeError(f"expected ITEM=QTY, got {raw!r}")
    return name.strip(), int(units)


def _location(raw: str) -> Location:
    return Location(raw.replace("-", "_"))


def _condition(raw: str | None) -> tuple[int, int] | None:
    """`103/110` -> (103, 110)."""
    if not raw or not raw.strip():
        return None
    current, _, maximum = raw.strip().partition("/")
    return int(current), int(maximum)


def _items(state: State, pairs: list[tuple[str, int]]) -> dict[Item, int]:
    """Quantities per item; an item named twice (learned one, sold one) adds up."""
    totals: dict[Item, int] = {}
    for name, quantity in pairs:
        item = resolve(state, name)
        totals[item] = totals.get(item, 0) + quantity
    return totals


def _actor() -> str:
    return os.environ.get("ARC_ACTOR", "unknown-agent")


def _pairs(flag: str, help: str | None = None) -> Arg:
    return arg(flag, nargs="*", type=_stack_pair, default=[], metavar="ITEM=QTY", help=help)


_WRITE_ARGS: tuple[Arg, ...] = (
    arg("--note", required=True, help="what the player observed, in their words"),
    arg("--actor", default=_actor()),
    arg("--no-commit", action="store_true"),
)


def read_count(path: Path) -> list[commands.CountLine]:
    """Rows of `location,item,stacks[,condition]`; stacks like `50x4+43`, condition `103/110`."""
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            commands.CountLine(
                location=_location(row["location"].strip()),
                item=row["item"].strip(),
                stacks=commands.parse_stacks(row["stacks"]),
                condition=_condition(row.get("condition")),
            )
            for row in csv.DictReader(handle)
        ]


# --- reads ------------------------------------------------------------------------------------


@reader("bootstrap", "session start: exact state, open gaps, rule findings")
def _bootstrap(state: State, args: argparse.Namespace) -> Any:
    return views.bootstrap(state)


@reader("count-check", "items whose real count is unproven, most important first")
def _count_check(state: State, args: argparse.Namespace) -> Any:
    return views.count_check(state)


@reader("loadout", "what is carried, by slot")
def _loadout(state: State, args: argparse.Namespace) -> Any:
    return views.loadout(state)


@reader("questions", "open questions only the player can answer")
def _questions(state: State, args: argparse.Namespace) -> Any:
    return [
        {"id": q.id, "topic": q.topic, "raid": q.raid_report.id if q.raid_report else None}
        for q in open_questions(state)
    ]


@reader("item", "one item: counts, stack size, pieces, goals", arg("item"))
def _item(state: State, args: argparse.Namespace) -> Any:
    return views.item_packet(state, resolve(state, args.item))


@reader("goal", "what a goal still needs", arg("goal"))
def _goal(state: State, args: argparse.Namespace) -> Any:
    return plan(state, state.get(Goal, args.goal))


@reader(
    "expect",
    "expected stash counter and coins after a raid's changes",
    _pairs("--add"),
    _pairs("--remove"),
    _pairs("--sell"),
)
def _expect(state: State, args: argparse.Namespace) -> Any:
    add, remove, sell = (_items(state, getattr(args, k)) for k in ("add", "remove", "sell"))
    return views.expected(state, add, remove, sell)


@action(
    "debrief",
    "keep/sell table for a haul (or the whole stash)",
    arg("haul", nargs="*", type=_stack_pair, metavar="ITEM=QTY"),
    arg("--markdown", action="store_true"),
)
def _debrief(args: argparse.Namespace) -> None:
    state = _state(args)
    rows = views.debrief(state, _items(state, args.haul))
    if args.markdown:
        print(views.debrief_markdown(rows))
    else:
        _emit(rows)


@action("audit", "every rule; exits 1 on any ERROR")
def _audit(args: argparse.Namespace) -> None:
    ok, lines = views.audit(_state(args))
    print("\n".join(lines))
    if not ok:
        raise SystemExit(1)


@writer("record-death", "the raider died: carried slots to zero, the safe pocket kept (C1)")
def _record_death(args: argparse.Namespace) -> commands.Change:
    return commands.record_death()


@action(
    "undo",
    "revert the last data write, as a commit of its own",
    arg("--note", required=True, help="why it is being undone"),
    arg("--actor", default=_actor()),
)
def _undo(args: argparse.Namespace) -> None:
    _emit({"applied": commands.undo(args.project, args.note, args.actor)})


# --- writes: inventory ------------------------------------------------------------------------


@writer(
    "set-count",
    "a live count for one stack",
    arg("item"),
    arg("location", type=_location),
    arg("quantity", help="integer, or 'unknown'"),
    arg("--slots", type=int),
)
def _set_count(args: argparse.Namespace) -> commands.Change:
    quantity = None if args.quantity == "unknown" else int(args.quantity)
    return commands.set_count(args.item, args.location, quantity, args.slots)


@writer("set-stash", "the stash counter", arg("used", type=int), arg("capacity", type=int))
def _set_stash(args: argparse.Namespace) -> commands.Change:
    return commands.set_stash(args.used, args.capacity)


@writer(
    "set-metric",
    "coins and other account counters",
    arg("metric", type=MetricKind),
    arg("value", type=int),
)
def _set_metric(args: argparse.Namespace) -> commands.Change:
    return commands.set_metric(args.metric, args.value)


@writer(
    "reconcile",
    "close unreconciled rows for one item with live counts",
    arg("item"),
    *(
        arg(f"--{loc.value.replace('_', '-')}", type=int, dest=f"count_{loc.value}")
        for loc in Location
    ),
)
def _reconcile(args: argparse.Namespace) -> commands.Change:
    counts = {
        loc: value for loc in Location if (value := getattr(args, f"count_{loc.value}")) is not None
    }
    return commands.reconcile(args.item, counts)


@writer(
    "stocktake",
    "a complete live count; the stash must reproduce the counter",
    arg("file", type=Path, help="CSV: location,item,stacks[,condition]"),
    arg("--stash-used", type=int, help="the in-game stash counter, e.g. 213"),
    arg("--carry", action="store_true", help="stash = records + --add/--remove; FILE = carried"),
    _pairs("--add", help="came in: loot unloaded, claimed, bought"),
    _pairs("--remove", help="left otherwise: used, recycled, crafted in, moved out"),
    _pairs("--sell"),
)
def _stocktake(args: argparse.Namespace) -> commands.Change:
    seen = read_count(args.file)
    events = (
        *((ActionKind.LOOT, n, q) for n, q in args.add),
        *((ActionKind.USED, n, q) for n, q in args.remove),
        *((ActionKind.SELL, n, q) for n, q in args.sell),
    )
    if args.carry:
        state = _state(args)
        removed = _items(state, [*args.remove, *args.sell])
        seen += commands.carried_stash(state, stash_after(state, _items(state, args.add), removed))
    return commands.stocktake(seen, args.stash_used, events)


@writer(
    "set-condition",
    "durability of one piece",
    arg("instance", help="instance id, or an item with exactly one unit"),
    arg("current", type=int),
    arg("maximum", type=int),
)
def _set_condition(args: argparse.Namespace) -> commands.Change:
    return commands.set_condition(args.instance, args.current, args.maximum)


# --- writes: one action as it happens (commands/events.py) ------------------------------------

_HELD = arg("items", nargs="+", type=_stack_pair, metavar="ITEM=QTY")
_READING: tuple[Arg, ...] = (
    arg("--stash-used", type=int, help="the counter after the action; checked against records"),
    arg("--coins", type=int, help="coins after the action, as read"),
)


def _reading(a: argparse.Namespace) -> commands.Reading:
    return commands.Reading(stash_used=a.stash_used, coins=a.coins)


def _at(flag: str, default: Location) -> Arg:
    return arg(flag, type=_location, default=default)


@writer(
    "move",
    "items moved between places",
    _HELD,
    _at("--from", Location.STASH),
    arg("--to", type=_location, required=True),
    *_READING,
)
def _move(a: argparse.Namespace) -> commands.Change:
    return commands.move(a.items, getattr(a, "from"), a.to, _reading(a))


@writer(
    "craft",
    "made at a bench from stash inputs",
    _HELD,
    _pairs("--using"),
    _at("--into", Location.STASH),
    *_READING,
)
def _craft(a: argparse.Namespace) -> commands.Change:
    return commands.craft(a.items, a.using, a.into, _reading(a))


@writer("recycle", "broken down into parts", _HELD, _pairs("--into"), *_READING)
def _recycle(a: argparse.Namespace) -> commands.Change:
    return commands.recycle(a.items, a.into, _reading(a))


@writer("sell", "sold for coins", _HELD, _at("--from", Location.STASH), *_READING)
def _sell(a: argparse.Namespace) -> commands.Change:
    return commands.sell(a.items, getattr(a, "from"), _reading(a))


@writer(
    "loot",
    "came in: raid unload, reward, purchase",
    _HELD,
    _at("--into", Location.STASH),
    *_READING,
)
def _loot(a: argparse.Namespace) -> commands.Change:
    return commands.loot(a.items, a.into, _reading(a))


@writer("use", "consumed: meds, ammo, keys", _HELD, _at("--from", Location.BACKPACK), *_READING)
def _use(a: argparse.Namespace) -> commands.Change:
    return commands.use(a.items, getattr(a, "from"), _reading(a))


@writer("trade", "an Envoy or trader swap", _pairs("--give"), _pairs("--get"), *_READING)
def _trade(a: argparse.Namespace) -> commands.Change:
    return commands.trade(a.give, a.get, _reading(a))


@writer(
    "repair",
    "a repair: its cost and the new durability",
    arg("piece"),
    arg("condition", type=_condition, metavar="CUR/MAX"),
    _pairs("--using"),
    *_READING,
)
def _repair(a: argparse.Namespace) -> commands.Change:
    current, maximum = a.condition
    condition = commands.set_condition(a.piece, current, maximum)
    return commands.repair(a.using, condition, _reading(a))


@writer(
    "contribute",
    "commit items to a project",
    arg("goal"),
    arg("item"),
    arg("quantity", type=int),
    arg(
        "--from",
        dest="location",
        type=lambda raw: None if raw == "raid" else _location(raw),
        default=Location.STASH,
        help="where it was held, or 'raid' if it went in straight from a raid",
    ),
)
def _contribute(args: argparse.Namespace) -> commands.Change:
    return commands.contribute(args.goal, args.item, args.quantity, args.location)


# --- writes: gear -----------------------------------------------------------------------------


@writer(
    "add-item",
    "a new game item, named as the game shows it",
    arg("id"),
    arg("name"),
    arg("category", type=ItemCategory),
    arg("--tier", type=int),
)
def _add_item(args: argparse.Namespace) -> commands.Change:
    return commands.add_item(args.id, args.name, args.category, args.tier)


@writer(
    "attach-mod",
    "a mod seen on a weapon",
    arg("weapon", help="instance id, or an item with exactly one unit"),
    arg("mod"),
    arg("slot", type=ModSlot),
    arg("--weapon-type", type=WeaponType),
)
def _attach_mod(args: argparse.Namespace) -> commands.Change:
    return commands.attach_mod(args.weapon, args.mod, args.slot, args.weapon_type)


@writer("detach-mod", "a mod taken off a weapon", arg("weapon"), arg("slot", type=ModSlot))
def _detach_mod(args: argparse.Namespace) -> commands.Change:
    return commands.detach_mod(args.weapon, args.slot)


@writer(
    "upgrade",
    "a tracked piece becomes its next tier",
    arg("piece", help="instance id, or an item with exactly one unit"),
    arg("to_item"),
    _pairs("--cost"),
    arg("--condition", type=_condition, help="new durability, e.g. 120/120"),
)
def _upgrade(args: argparse.Namespace) -> commands.Change:
    return commands.upgrade_piece(args.piece, args.to_item, dict(args.cost), args.condition)


# --- writes: plans ----------------------------------------------------------------------------


@writer("set-goal-status", "mark a goal", arg("goal"), arg("status", type=GoalStatus))
def _set_goal_status(args: argparse.Namespace) -> commands.Change:
    return commands.set_goal_status(args.goal, args.status)


@writer(
    "set-goal-priority",
    "lower runs first",
    arg("goal"),
    arg("priority", help="integer, or 'none'"),
)
def _set_goal_priority(args: argparse.Namespace) -> commands.Change:
    priority = None if args.priority == "none" else int(args.priority)
    return commands.set_goal_priority(args.goal, priority)


@writer(
    "add-goal",
    "a new goal with requirements and prerequisites",
    arg("id"),
    arg("name"),
    arg("--priority", type=int),
    _pairs("--require"),
    arg("--after", nargs="*", default=[], metavar="GOAL"),
)
def _add_goal(args: argparse.Namespace) -> commands.Change:
    return commands.add_goal(args.id, args.name, args.priority, dict(args.require), args.after)


@writer(
    "set-disposition",
    "a standing keep/sell rule",
    arg("item"),
    arg("action", type=DispositionAction),
    arg("keep_total", type=int),
)
def _set_disposition(args: argparse.Namespace) -> commands.Change:
    return commands.set_disposition(args.item, args.action, args.keep_total)


@writer("set-preference", "a player choice", arg("key", type=PreferenceKey), arg("value", type=int))
def _set_preference(args: argparse.Namespace) -> commands.Change:
    return commands.set_preference(args.key, args.value)


@writer(
    "set-build",
    "level and points per tree",
    arg("level", type=int),
    arg("--mobility", type=int),
    arg("--conditioning", type=int),
    arg("--survival", type=int),
    arg("--unspent", type=int, default=0),
)
def _set_build(args: argparse.Namespace) -> commands.Change:
    return commands.set_build(
        args.level, args.mobility, args.conditioning, args.unspent, args.survival
    )


@writer(
    "set-skill",
    "a skill's rank",
    arg("skill"),
    arg("rank", type=int),
    arg("--maximum", type=int),
)
def _set_skill(args: argparse.Namespace) -> commands.Change:
    return commands.set_skill(args.skill, args.rank, args.maximum)


@writer("resolve-question", "answer an open question", arg("question"))
def _resolve_question(args: argparse.Namespace) -> commands.Change:
    return commands.resolve_question(args.question)


# --- writes: Scrappy --------------------------------------------------------------------------


@writer(
    "feed-scrappy",
    "queue food",
    arg("food"),
    arg("quantity", type=int, nargs="?", default=1),
)
def _feed_scrappy(args: argparse.Namespace) -> commands.Change:
    return commands.feed_scrappy(args.food, args.quantity)


@writer("set-scrappy-level", "Scrappy's level after an upgrade", arg("level", type=int))
def _set_scrappy_level(args: argparse.Namespace) -> commands.Change:
    return commands.set_scrappy_level(args.level)


@writer(
    "claim-scrappy",
    "claim his haul into the stash",
    arg("shorthand", help="'8 8 8 8 8 11' in reward order, or '8s and 11'"),
    arg("--rounds", type=int, default=1),
    arg("--ate", nargs="*", default=[], metavar="FOOD", help="queued foods eaten"),
    _pairs("--extra"),
    arg("--stash-used", type=int, help="the stash counter after claiming"),
)
def _claim_scrappy(args: argparse.Namespace) -> commands.Change:
    return commands.claim_scrappy(
        args.shorthand, args.rounds, args.ate, dict(args.extra), args.stash_used
    )


# --- writes: game facts -----------------------------------------------------------------------


@writer(
    "set-stack-size",
    "stack sizes read in game",
    arg("pairs", nargs="+", type=_stack_pair, metavar="ITEM=UNITS"),
)
def _set_stack_size(args: argparse.Namespace) -> commands.Change:
    return commands.set_stack_sizes(dict(args.pairs))


@writer(
    "import-reference",
    "stack sizes, types, values and recipes from the RaidTheory dataset",
    arg("items_dir", type=Path, help="RaidTheory arcraiders-data items/ directory"),
    arg("--add-missing", action="store_true", help="add dataset items not held here"),
    kind=SourceKind.WEB_REFERENCE,
)
def _import_reference(args: argparse.Namespace) -> commands.Change:
    dataset = read_dataset(args.items_dir)
    return commands.import_reference(dataset, add_missing=args.add_missing)


@writer("import-scrappy-rates", "Scrappy's rates for every level (wiki)", kind=SourceKind.WEB)
def _import_scrappy_rates(args: argparse.Namespace) -> commands.Change:
    return commands.import_scrappy_rates()


@writer("import-augment-capacities", "carry limits per augment (wiki)", kind=SourceKind.WEB)
def _import_augment_capacities(args: argparse.Namespace) -> commands.Change:
    return commands.import_augment_capacities()


# --- sharing and schema -----------------------------------------------------------------------


@action(
    "export-starter",
    "write a clean package for a new player",
    arg("dest", type=Path, help="new folder, or a clone of the starter repo"),
    arg("--upstream", default=STARTER_REPO),
)
def _export_starter(args: argparse.Namespace) -> None:
    dest = args.dest.resolve()
    fresh = not dest.exists()
    starter = export(args.project, dest, args.upstream)
    if problems := errors(run(starter)):
        raise SystemExit("rules failed:\n" + "\n".join(f.message for f in problems))
    git = ["git", "-C", str(dest)]
    if fresh:
        subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    committed = subprocess.run(
        [*git, "commit", "-q", "-m", f"Starter package {dt.date.today().isoformat()}"],
        check=False,
        capture_output=True,
    )
    _emit(
        {
            "exported": str(dest),
            "items": len(starter.all(Item)),
            "starter_goals": len(starter.all(Goal)),
            "committed": committed.returncode == 0,
            "next": "review, then git push" if not fresh else f"cd {dest} && uv run arc init",
        }
    )


@action("init", "once, in a starter package: create your data/")
def _init(args: argparse.Namespace) -> None:
    _emit({"init": init(args.project)})


@action("check-update", "is a newer starter package on GitHub?")
def _check_update(args: argparse.Namespace) -> None:
    found = check_update(args.project)
    if found is None:
        _emit({"update": "this is the source package; nothing to check"})
        return
    _emit(
        {
            "upstream": found.upstream,
            "update_available": found.available,
            "new_commits": found.new_commits,
            "next": "uv run arc update" if found.available else None,
        }
    )


@action("update", "take the newer starter; your data is kept", arg("--actor", default=_actor()))
def _update(args: argparse.Namespace) -> None:
    found = check_update(args.project)
    if found is None:
        raise SystemExit("this is the source package; nothing to update")
    if not found.available:
        _emit({"update": "already up to date"})
        return
    head = take_update(args.project)
    created = ensure_tables(commands.data_dir(args.project))
    note = f"starter update to {head} from {found.upstream}: " + "; ".join(found.new_commits)
    change = commands.starter_update(args.project)
    summary = commands.apply(args.project, note, args.actor, change, kind=SourceKind.WEB_REFERENCE)
    _emit({"updated_to": head, "new_tables": created, "applied": summary})


@action("migrate-schema", "create tables a newer engine added, then commit")
def _migrate_schema(args: argparse.Namespace) -> None:
    created = ensure_tables(commands.data_dir(args.project))
    if created and (args.project / ".git").exists():
        git = ["git", "-C", str(args.project)]
        subprocess.run([*git, "add", "data"], check=True)
        message = "migrate-schema: new tables " + ", ".join(created)
        subprocess.run([*git, "commit", "-q", "-m", message], check=True)
    _emit({"new_tables": created})


# --- entry point ------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="arc", description=__doc__)
    parser.add_argument("--project", type=Path, default=PROJECT)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in COMMANDS.values():
        p = sub.add_parser(command.name, help=command.help)
        for flags, options in command.args:
            p.add_argument(*flags, **options)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        COMMANDS[args.command].run(args)
    except (commands.Refused, LoadError, KeyError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
