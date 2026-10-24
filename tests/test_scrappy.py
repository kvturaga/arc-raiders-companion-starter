from __future__ import annotations

from pathlib import Path

import pytest

from arc_companion import commands
from arc_companion.enums import FeedStatus, SourceKind
from arc_companion.model import CompanionFeed, Holding, RewardLine
from arc_companion.store import load

from .conftest import apply_change


def _stash(project: Path, item: str) -> int | None:
    return load(project / "data").get(Holding, f"{item}@stash").quantity


def test_shorthand_reads_in_reward_order() -> None:
    assert commands.parse_scrappy("8s and 11") == [8, 8, 8, 8, 8, 11]
    assert commands.parse_scrappy("8 8 8 13 8 11") == [8, 8, 8, 13, 8, 11]
    with pytest.raises(commands.Refused):
        commands.parse_scrappy("8 8 8")


def test_a_claim_lands_in_the_stash_and_names_its_wiki_bracket(project: Path) -> None:
    apply_change(project, commands.import_scrappy_rates(), SourceKind.WEB)
    metal = _stash(project, "metal_parts")
    assert metal is not None
    summary = apply_change(project, commands.claim_scrappy("8s and 11", 1, [], {}, None))
    assert "matches level 4, over 15 min, extracted" in summary
    assert _stash(project, "metal_parts") == metal + 8
    lines = load(project / "data").all(RewardLine)
    assert any(r.item.id == "assorted_seeds" and r.quantity == 11 for r in lines)


def test_eaten_food_explains_its_plus_five(project: Path) -> None:
    apply_change(project, commands.import_scrappy_rates(), SourceKind.WEB)
    apricots = _stash(project, "apricots")
    assert apricots
    apply_change(project, commands.feed_scrappy("Apricots"))
    assert _stash(project, "apricots") == apricots - 1  # food leaves the stash when queued
    summary = apply_change(
        project, commands.claim_scrappy("8 8 8 13 8 11", 1, ["Apricots"], {}, None)
    )
    assert "matches level 4, over 15 min, extracted" in summary
    feeds = load(project / "data").all(CompanionFeed)
    assert not [f for f in feeds if f.status is FeedStatus.QUEUED]


def test_an_unexplained_claim_says_an_input_is_missing(project: Path) -> None:
    apply_change(project, commands.import_scrappy_rates(), SourceKind.WEB)
    summary = apply_change(project, commands.claim_scrappy("8 8 8 13 8 11", 1, [], {}, None))
    assert "matches no level-4 bracket" in summary


def test_only_foods_are_fed_and_the_queue_holds_six(project: Path) -> None:
    with pytest.raises(commands.Refused, match="not a Scrappy food"):
        apply_change(project, commands.feed_scrappy("Metal Parts"))
    with pytest.raises(commands.Refused, match="queue holds 6"):
        apply_change(project, commands.feed_scrappy("Apricots", 7))
