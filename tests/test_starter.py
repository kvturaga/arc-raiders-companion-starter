from __future__ import annotations

import dataclasses
import datetime as dt
import subprocess
from pathlib import Path

import pytest

from arc_companion.checks import errors, run
from arc_companion.distribution import (
    STARTER_DATA,
    STARTER_REPO,
    UPSTREAM,
    check_update,
    export,
    init,
    take_update,
)
from arc_companion.enums import SourceKind
from arc_companion.model import (
    AccountMetric,
    Goal,
    GoalDependency,
    GoalRequirement,
    Holding,
    Item,
    ItemInstance,
    OpenQuestion,
    Preference,
    Source,
    StackSize,
    StashCounter,
    Station,
)
from arc_companion.starter import PLACEHOLDERS, build_starter, merge_starter
from arc_companion.store import State, load

from .conftest import PROJECT

TODAY = dt.date(2026, 10, 23)


# The source package keeps a player's data/; a shared copy has only starter_data/ until init.
SEED = PROJECT / "data" if (PROJECT / "data").exists() else PROJECT / STARTER_DATA


@pytest.fixture(scope="module")
def starter() -> State:
    return build_starter(load(SEED))


def test_the_starter_passes_every_rule(starter: State) -> None:
    assert errors(run(starter)) == []


def test_no_player_state_leaks_into_the_starter(starter: State) -> None:
    for cls in (Holding, ItemInstance, AccountMetric, OpenQuestion):
        assert starter.all(cls) == []
    assert starter.all(StashCounter)[0].used == 0
    assert not [i for i in starter.all(Item) if i.id in PLACEHOLDERS]
    # A player's own words can describe their stash; only public references keep text.
    public = (SourceKind.WEB, SourceKind.WEB_REFERENCE)
    for s in starter.all(Source):
        if s.kind not in public and not s.id.startswith("starter_"):
            assert s.reference == f"{s.kind} recorded by the companion's original player"


def test_a_new_player_starts_with_only_the_workbench(starter: State) -> None:
    levels = {s.id: s.level for s in starter.all(Station)}
    assert levels.pop("workbench") == 1
    assert set(levels.values()) == {0}


def test_bench_goals_climb_one_level_at_a_time(starter: State) -> None:
    after = {d.goal.id: d.prerequisite.id for d in starter.all(GoalDependency)}
    assert after["gunsmith_3"] == "gunsmith_2"
    assert after["gunsmith_2"] == "gunsmith_1"
    assert "gunsmith_1" not in after
    needs = {
        r.item.id: r.quantity for r in starter.all(GoalRequirement) if r.goal.id == "gunsmith_3"
    }
    assert needs == {
        "rusted_gears": 3,
        "advanced_mechanical_component": 5,
        "sentinel_firing_cores": 4,
    }


def test_backup_kits_follow_the_recipe_and_wait_for_gunsmith_i(starter: State) -> None:
    kit = starter.get(Goal, "backup_ferro_i")
    needs = {r.item.id: r.quantity for r in starter.all(GoalRequirement) if r.goal == kit}
    assert needs == {"metal_parts": 5, "rubber_parts": 2}
    assert any(
        d.goal == kit and d.prerequisite.id == "gunsmith_1" for d in starter.all(GoalDependency)
    )


def test_export_writes_a_package_without_history(tmp_path: Path) -> None:
    dest = tmp_path / "friend"
    export(PROJECT, dest)
    assert (dest / "src" / "arc_companion" / "starter.py").exists()
    assert (dest / "docs" / "new_player_guide.md").exists()
    assert (dest / ".github" / "workflows" / "ci.yml").exists()
    assert (dest / UPSTREAM).read_text().strip() == STARTER_REPO
    assert "MIT License" in (dest / "LICENSE").read_text()
    assert "arc_legacy" not in (dest / "pyproject.toml").read_text()
    assert "RaidTheory" in (dest / "NOTICE.md").read_text()
    assert "Embark Studios" in (dest / "README.md").read_text()
    observed = (dest / "contrib" / "stack_sizes_observed.csv").read_text().splitlines()
    assert observed[0] == "item_id,name,units_per_slot,observed_on"
    for absent in ("legacy", "migration", "data", "tests/test_migration.py", "src/arc_legacy"):
        assert not (dest / absent).exists()
    assert load(dest / STARTER_DATA).all(Holding) == []
    with pytest.raises(FileExistsError):  # exists, and is not a starter repo clone
        export(PROJECT, dest)


def test_nothing_identifying_survives_in_the_starter(starter: State) -> None:
    assert starter.all(Preference) == []
    for s in starter.all(Source):
        assert s.id.startswith(("src_", "starter_")), s.id
    # Public references are links; everything else carries only the neutral line.
    for s in starter.all(Source):
        if s.kind in (SourceKind.WEB, SourceKind.WEB_REFERENCE):
            assert "http" in s.reference or "RaidTheory" in s.reference, s.reference


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )
    return done.stdout


def _commit_all(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", message)


def test_a_friend_inits_checks_and_takes_an_update(tmp_path: Path) -> None:
    upstream = tmp_path / "starter"
    export(PROJECT, upstream, upstream=str(upstream))
    _git(upstream, "init", "-q", "-b", "main")
    _commit_all(upstream, "v1")
    friend = tmp_path / "friend"
    subprocess.run(["git", "clone", "-q", str(upstream), str(friend)], check=True)
    _git(friend, "config", "user.name", "t")
    _git(friend, "config", "user.email", "t@t")

    assert "renamed to 'starter'" in init(friend)
    assert _git(friend, "remote").split() == ["starter"]  # a bare `git push` goes nowhere
    with pytest.raises(FileExistsError):
        init(friend)

    found = check_update(friend)
    assert found is not None
    assert not found.available

    (upstream / "docs" / "new_player_guide.md").write_text("updated guide\n")
    _commit_all(upstream, "v2: guide")
    found = check_update(friend)
    assert found is not None
    assert found.new_commits[0].endswith("v2: guide")
    take_update(friend)
    assert (friend / "docs" / "new_player_guide.md").read_text() == "updated guide\n"
    assert (friend / "data").exists()  # the friend's data is untouched by the merge


def test_merge_keeps_the_players_own_readings_and_progress(starter: State) -> None:
    player = build_starter(load(SEED))
    mine = Source(
        id="obs_1", seq=10**6, kind=SourceKind.USER_REPORT, observed_on=TODAY, reference="x"
    )
    player.add(mine)
    zipline = player.get(StackSize, "zipline")
    player.put(dataclasses.replace(zipline, units_per_slot=7, source=mine))
    bench = player.get(Station, "gunsmith")
    player.put(dataclasses.replace(bench, level=2))
    player.remove(player.get(Goal, "backup_ferro_i"))
    for r in [r for r in player.all(GoalRequirement) if r.goal.id == "backup_ferro_i"]:
        player.remove(r)
    for d in [d for d in player.all(GoalDependency) if d.goal.id == "backup_ferro_i"]:
        player.remove(d)

    report = merge_starter(player, starter)
    assert player.get(StackSize, "zipline").units_per_slot == 7  # their reading wins
    assert "stack_sizes:zipline" in report.kept_yours
    assert player.get(Station, "gunsmith").level == 2  # progress never reset
    assert report.goals_added == ["backup_ferro_i"]
    assert errors(run(player)) == []


def test_a_starter_can_itself_be_exported(starter: State) -> None:
    again = build_starter(starter)
    assert errors(run(again)) == []
    assert len(again.all(Goal)) == len(starter.all(Goal))


def test_refiner_iii_follows_the_in_game_reading(starter: State) -> None:
    goal = starter.get(Goal, "refiner_3")
    assert goal.name == "Refiner III"
    assert goal.source.kind is SourceKind.USER_REPORT
    assert "no Outpost requirement" in goal.source.reference
