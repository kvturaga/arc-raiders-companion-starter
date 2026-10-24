"""The whole after-raid loop through the real CLI, as an agent runs it (docs/raid_debrief.md)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from arc_companion import cli, commands, views
from arc_companion.enums import Location
from arc_companion.model import AccountMetric, Holding, StashCounter
from arc_companion.queries import stash_after
from arc_companion.store import load


def _arc(capsys: pytest.CaptureFixture[str], project: Path, *argv: str) -> Any:
    cli.main(["--project", str(project), *argv])
    return json.loads(capsys.readouterr().out)


def _write(capsys: pytest.CaptureFixture[str], project: Path, *argv: str) -> Any:
    return _arc(capsys, project, *argv, "--note", "test", "--no-commit")


def _baseline(capsys: pytest.CaptureFixture[str], project: Path, loadout: Path) -> int:
    """Make the records and the counter agree, as a first full stocktake would."""
    _write(capsys, project, "set-stack-size", "Metal Parts=50", "Rubber Parts=50")
    state = load(project / "data")
    slots = sum(len(x.stacks) for x in commands.carried_stash(state, stash_after(state, {}, {})))
    _write(capsys, project, "stocktake", str(loadout), "--carry", "--stash-used", str(slots))
    return slots


def test_predict_then_save_a_raid_then_claim_scrappy(
    capsys: pytest.CaptureFixture[str], project: Path, tmp_path: Path
) -> None:
    loadout = tmp_path / "loadout.csv"
    loadout.write_text("location,item,stacks,condition\n")
    counter = _baseline(capsys, project, loadout)
    metal = load(project / "data").get(Holding, "metal_parts@stash").quantity or 0
    spill = (50 - metal % 50) % 50 + 1  # one more than fills the last stack: a new stack

    # 1. Predict what the screen should show after unloading the haul.
    predicted = _arc(capsys, project, "predict", "--add", f"Metal Parts={spill}")
    assert predicted["counter_predicted"] == counter + 1
    assert predicted["slot_changes"][0]["item"] == "Metal Parts"

    # 2. A wrong counter reading is refused; nothing is written.
    with pytest.raises(SystemExit) as refused:
        cli.main(["--project", str(project), "stocktake", str(loadout), "--carry",
                  "--add", f"Metal Parts={spill}", "--stash-used", str(counter),
                  "--note", "test", "--no-commit"])  # fmt: skip
    assert refused.value.code == 2
    capsys.readouterr()
    assert load(project / "data").get(Holding, "metal_parts@stash").quantity == metal

    # 3. The predicted counter saves.
    saved = _write(capsys, project, "stocktake", str(loadout), "--carry",
                   "--add", f"Metal Parts={spill}", "--stash-used",
                   str(predicted["counter_predicted"]))  # fmt: skip
    assert "stocktake stash" in saved["applied"]
    state = load(project / "data")
    assert state.get(Holding, "metal_parts@stash").quantity == metal + spill
    assert state.all(StashCounter)[0].used == counter + 1

    # 4. Scrappy and coins finish the loop.
    _write(capsys, project, "import-scrappy-rates")
    claim = _write(capsys, project, "claim-scrappy", "3 3 3 3 3 3")
    assert "matches level 4, over 1 min, extracted" in claim["applied"]
    _write(capsys, project, "set-metric", "coins", "123456")
    after = load(project / "data")
    assert after.get(Holding, "metal_parts@stash").quantity == metal + spill + 3
    assert after.get(AccountMetric, "coins").value == 123456
    audit = views.audit(after)
    assert audit[0], audit[1]


def test_contributing_and_upgrading_through_the_cli(
    capsys: pytest.CaptureFixture[str], project: Path
) -> None:
    _write(capsys, project, "set-count", "Metal Parts", "stash", "100")
    _write(capsys, project, "add-goal", "demo", "Demo project", "--require", "Metal Parts=30")
    result = _write(capsys, project, "contribute", "demo", "Metal Parts", "10")
    assert "10 given" in result["applied"]
    up = _write(capsys, project, "upgrade", "Rattler II", "Rattler III", "--cost",
                "Metal Parts=5", "--condition", "120/120")  # fmt: skip
    assert "rattler_ii -> rattler_iii" in up["applied"]
    state = load(project / "data")
    assert state.get(Holding, f"metal_parts@{Location.STASH}").quantity == 85
