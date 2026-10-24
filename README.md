# ARC Raiders companion

Your ARC Raiders memory: what you own, what you are building toward, and the game rules behind
it, kept as checked data so an AI agent (Claude Code, or ChatGPT through Codex) gives exact
answers. Start with the [new player guide](docs/new_player_guide.md). Rules for agents:
[AGENTS.md](AGENTS.md). Sourced game rules: [docs/first_principles.md](docs/first_principles.md).

```sh
uv sync
uv run arc init                 # once: creates your own data/ from starter_data/
uv run arc check-update         # every session: is a newer package on GitHub?
uv run arc update               # take it: new engine and game facts, your data kept
uv run arc bootstrap            # where you stand, and the next goals
uv run arc goal gunsmith_2      # what one goal still needs
uv run arc item "Metal Parts"   # one item: counts, stack size, which goals use it
uv run arc audit                # every rule
```

Every change goes through an `arc` command, which checks it, records your words as its source
and commits it to git. Never edit `data/` by hand, and never push to the starter repo.

## License and credits

[MIT](LICENSE), © kvturaga; provided as is, with no warranty. A fan project, not affiliated with
or endorsed by Embark Studios AB, who own ARC Raiders and its content. Item data derives from
[RaidTheory/arcraiders-data](https://github.com/RaidTheory/arcraiders-data) and
[arctracker.io](https://arctracker.io) (MIT). Built with Claude Code.
Details: [NOTICE.md](NOTICE.md).
