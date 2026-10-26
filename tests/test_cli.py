from __future__ import annotations

from pathlib import Path

import pytest

from arc_companion import cli
from arc_companion.cli import COMMANDS, build_parser
from arc_companion.queries import resolve
from arc_companion.store import load


def test_every_command_parses_and_writers_require_a_note() -> None:
    parser = build_parser()
    assert len(COMMANDS) >= 39
    for name, command in COMMANDS.items():
        flags = {f for spec, _ in command.args for f in spec}
        if "--note" in flags:
            with pytest.raises(SystemExit):  # a write without the player's words is refused
                parser.parse_args([name])


def test_a_read_needs_no_note() -> None:
    args = build_parser().parse_args(["bootstrap"])
    assert args.command == "bootstrap"


def test_an_item_named_twice_adds_up(project: Path) -> None:
    state = load(project / "data")
    pairs = [("Metal Parts", 3), ("metal parts", 2)]
    assert cli._items(state, pairs) == {resolve(state, "Metal Parts"): 5}
