"""A demo player, built only from the starter's game facts and the real setters.

Tests arrange their own state on top of this known save, so no test depends on any real
player's records. The script doubles as a worked example of a first session.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from arc_companion import commands
from arc_companion.commands import CountLine
from arc_companion.enums import Location, MetricKind, ModSlot
from arc_companion.queries import stash_slot_math
from arc_companion.starter import build_starter
from arc_companion.store import load, write

TODAY = dt.date(2026, 10, 23)
STASH, EQUIP = Location.STASH, Location.EQUIPMENT

# What the demo player's first stocktake reads: every stash slot, then every carried slot.
FIRST_COUNT: tuple[CountLine, ...] = (
    CountLine(STASH, "Metal Parts", (50, 50, 50, 50, 34)),
    CountLine(STASH, "Rubber Parts", (50, 50, 50, 26)),
    CountLine(STASH, "Fabric", (50, 50, 20)),
    CountLine(STASH, "Chemicals", (50, 40)),
    CountLine(STASH, "Plastic Parts", (50, 50, 10)),
    CountLine(STASH, "Assorted Seeds", (100, 19)),
    CountLine(STASH, "Light Ammo", (100, 20)),
    CountLine(STASH, "ARC Alloy", (15, 15, 15, 15, 5)),
    CountLine(STASH, "Wires", (15, 7)),
    CountLine(STASH, "Hornet Driver", (3, 3, 2)),
    CountLine(STASH, "Zipline", (3,)),
    CountLine(STASH, "Apricot", (10,)),
    CountLine(STASH, "Mushroom", (5,)),
    CountLine(STASH, "Sentinel Firing Core", (3,)),
    CountLine(STASH, "Burletta I", (1,)),
    CountLine(STASH, "Renegade I", (1,), condition=(57, 100)),
    CountLine(STASH, "Compensator III", (1,)),
    CountLine(STASH, "Extended Medium Mag I", (1,)),
    CountLine(STASH, "Extended Light Mag I", (1,)),
    CountLine(EQUIP, "Looting Mk. 2", (1,)),
    CountLine(EQUIP, "Light Shield", (1,), condition=(100, 100)),
    CountLine(EQUIP, "Rattler II", (1,), condition=(110, 110)),
    CountLine(EQUIP, "Silencer I", (1,)),
    CountLine(EQUIP, "Stable Stock II", (1,)),
    CountLine(EQUIP, "Vertical Grip II", (1,)),
    CountLine(Location.BACKPACK, "Medium Ammo", (80, 80)),
    CountLine(Location.QUICK_USE, "Bandage", (5,)),
    CountLine(Location.QUICK_USE, "Seeker Grenade", (5,)),
    CountLine(Location.SAFE_POCKET, "Grappling Hook", (1,), condition=(82, 100)),
    CountLine(Location.SAFE_POCKET, "Photoelectric Cloak", (1,), condition=(93, 100)),
)
MODS: tuple[tuple[str, str, ModSlot], ...] = (
    ("Rattler II", "Silencer I", ModSlot.MUZZLE),
    ("Rattler II", "Stable Stock II", ModSlot.STOCK),
    ("Rattler II", "Vertical Grip II", ModSlot.UNDERBARREL),
    ("Renegade I", "Compensator III", ModSlot.MUZZLE),
    ("Renegade I", "Extended Medium Mag I", ModSlot.MAGAZINE),
)


def _apply(project: Path, change: commands.Change) -> None:
    commands.apply(project, "demo player setup", "pytest", change, commit=False)


def build_demo(project: Path, seed: Path) -> None:
    """Write the demo player's data to `project / "data"`."""
    write(build_starter(load(seed), TODAY), project / "data")
    stash_tiles = sum(len(line.stacks) for line in FIRST_COUNT if line.location is STASH)
    _apply(project, commands.stocktake(list(FIRST_COUNT), stash_used=stash_tiles))
    for weapon, mod, slot in MODS:
        _apply(project, commands.attach_mod(weapon, mod, slot))
    # Mods on a weapon share its slot: the counter drops by the two mods put on the Renegade.
    implied = stash_slot_math(load(project / "data")).implied
    _apply(project, commands.set_stash(implied, 232))
    _apply(project, commands.set_metric(MetricKind.COINS, 100_000))
    _apply(project, commands.set_scrappy_level(4))
