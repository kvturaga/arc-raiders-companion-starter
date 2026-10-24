"""The read packets an agent starts every session with."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arc_companion import cli, views
from arc_companion.enums import Location
from arc_companion.queries import resolve
from arc_companion.store import load


def test_bootstrap_reports_state_goals_and_gaps(project: Path) -> None:
    packet = views.bootstrap(load(project / "data"))
    assert packet["stash"]["capacity"] >= packet["stash"]["used"] >= 0
    assert packet["stash"]["free"] == packet["stash"]["capacity"] - packet["stash"]["used"]
    assert packet["build"]["level"] > 0
    priorities = [g["priority"] for g in packet["active_goals"] if g["priority"] is not None]
    assert priorities == sorted(priorities)  # lower runs first
    assert packet["stash"]["slot_math"]["complete"]  # the demo's counts reproduce its counter
    assert packet["unproven"]["unreconciled_rows"] == 0
    assert packet["coins"] == 100_000


def test_count_check_lists_goal_items_first(legacy_project: Path) -> None:
    rows = views.count_check(load(legacy_project / "data"))
    assert rows
    seen_goal_less = False
    for row in rows:
        if not row["active_goals"]:
            seen_goal_less = True
        assert not (seen_goal_less and row["active_goals"]), "goal items must come first"
        assert row["command"].startswith("arc reconcile")


def test_item_packet_shows_counts_pieces_and_goals(project: Path) -> None:
    state = load(project / "data")
    rattler = views.item_packet(state, resolve(state, "Rattler II"))
    assert rattler["instances"]
    assert rattler["instances"][0]["location"] == Location.EQUIPMENT.value
    metal = views.item_packet(state, resolve(state, "Metal Parts"))
    assert metal["stash"] == sum(
        h["quantity"] or 0 for h in metal["holdings"] if h["location"] == "stash"
    )


def test_loadout_lists_carried_stacks_and_pieces(project: Path) -> None:
    rows = views.loadout(load(project / "data"))
    assert rows == sorted(rows, key=lambda r: (r["location"], r["item"]))
    assert any(r["piece"] for r in rows)  # tracked pieces carry their id
    assert all(r["quantity"] > 0 for r in rows)


def test_read_commands_print_json(capsys: pytest.CaptureFixture[str], project: Path) -> None:
    for argv in (["bootstrap"], ["loadout"], ["questions"], ["goal", "gunsmith_3"]):
        cli.main(["--project", str(project), *argv])
        json.loads(capsys.readouterr().out)
