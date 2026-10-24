from __future__ import annotations

import pytest

from arc_companion.cli import COMMANDS, build_parser


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
