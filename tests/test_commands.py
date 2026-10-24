from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from arc_companion import commands
from arc_companion.enums import GoalStatus, Location, MetricKind, RaidStatus
from arc_companion.model import (
    AccountMetric,
    Item,
    RaidReport,
    Reservation,
    UnreconciledHolding,
)
from arc_companion.queries import balance
from arc_companion.store import LoadError, load, write_lock

from .conftest import apply_change, snapshot


def test_set_count_records_a_sourced_confirmed_count(project: Path) -> None:
    apply_change(project, commands.set_count("Metal Parts", Location.STASH, 250))
    state = load(project / "data")
    held = balance(state, state.get(Item, "metal_parts"))
    assert held.stash == 250
    assert held.holdings[0].source.reference == "test observation"


def test_a_rule_violation_writes_nothing(project: Path) -> None:
    before = snapshot(project / "data")
    # 120 Light Ammo at 100 per slot cannot fit in one slot.
    with pytest.raises(commands.Refused, match="stack_physics"):
        apply_change(project, commands.set_count("Light Ammo", Location.STASH, 120, slots=1))
    assert snapshot(project / "data") == before


def test_reconcile_requires_every_claimed_location(legacy_project: Path) -> None:
    with pytest.raises(commands.Refused, match="backpack"):
        apply_change(legacy_project, commands.reconcile("ARC Alloy", {Location.STASH: 70}))


def test_reconcile_closes_rows_and_reports(legacy_project: Path) -> None:
    apply_change(
        legacy_project, commands.reconcile("ARC Alloy", {Location.STASH: 70, Location.BACKPACK: 0})
    )
    state = load(legacy_project / "data")
    alloy = state.get(Item, "arc_alloy")
    assert not [u for u in state.all(UnreconciledHolding) if u.item == alloy]
    assert balance(state, alloy).confirmed == 70
    # A report closes only once none of its rows remain open.
    open_reports = {u.raid_report.id for u in state.all(UnreconciledHolding) if u.raid_report}
    for report in state.all(RaidReport):
        expected = (
            RaidStatus.RETURNED_UNLOAD_UNCONFIRMED
            if report.id in open_reports
            else RaidStatus.RECONCILED
        )
        assert report.status is expected


def test_completing_a_goal_releases_its_reservations(legacy_project: Path) -> None:
    goal = next(iter(load(legacy_project / "data").all(Reservation))).goal.id
    summary = apply_change(legacy_project, commands.set_goal_status(goal, GoalStatus.COMPLETE))
    assert "released" in summary
    assert not [r for r in load(legacy_project / "data").all(Reservation) if r.goal.id == goal]


def test_a_second_writer_is_refused(project: Path) -> None:
    with write_lock(project), pytest.raises(LoadError, match="held by another writer"):
        apply_change(project, commands.set_stash(213, 232))


def test_a_note_is_mandatory(project: Path) -> None:
    with pytest.raises(commands.Refused, match="note"):
        commands.apply(project, " ", "pytest", commands.set_stash(1, 2), commit=False)


def _committed(project: Path) -> Path:
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.name", "t"),
        ("config", "user.email", "t@t"),
        ("add", "data"),
        ("commit", "-qm", "start"),
    ):
        subprocess.run(["git", "-C", str(project), *args], check=True, capture_output=True)
    return project


def _coins(project: Path) -> int:
    return load(project / "data").get(AccountMetric, MetricKind.COINS).value


def test_undo_reverts_the_last_data_write_once(project: Path) -> None:
    _committed(project)
    before = _coins(project)
    commands.apply(project, "misheard", "pytest", commands.set_metric(MetricKind.COINS, 9))
    summary = commands.undo(project, "it was 90k, not 9", "pytest")
    assert summary.startswith("undo ")
    assert _coins(project) == before
    with pytest.raises(commands.Refused, match="not a data write"):
        commands.undo(project, "again", "pytest")  # one step: never a redo
