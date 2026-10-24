# Rules for any agent working in this package (Claude, ChatGPT, or other)

This package is the ARC Raiders companion's persistent memory. Conversation is the interface;
`data/` is the source of truth. These rules are enforced in code where possible; the rest are
binding anyway.

Before changing the model, read [docs/first_principles.md](docs/first_principles.md): system
principles, how the objects interact, and the sourced game rules (post Frozen Trail 2.0). A game
rule enters the code only with a source or a player observation behind it.

New player, or a package someone shared with you? Read
[docs/new_player_guide.md](docs/new_player_guide.md) first and walk the player through its setup
and first stocktake.

## Start of every session

```sh
uv run arc check-update   # shared copies (an UPSTREAM file exists): is a newer package out?
uv run arc bootstrap      # exact current state, open gaps, rule findings
```

**Updates.** In a shared copy, run `arc check-update` first, every session. If it reports an
update, tell the player what changed (it lists the commits) and run `uv run arc update` once they
agree. It merges the new engine and game facts from the starter repo on GitHub, keeps every
reading the player recorded themselves and all their progress, and refuses if there are
uncommitted changes. No `data/` yet? Run `uv run arc init` first. Never push to the `starter`
remote; the player's own data goes to their own private repo.

**Publishing (source package only, no UPSTREAM file).** After a change to the engine, game facts
or docs that other players should get, refresh the starter repo clone and push it:
`uv run arc export-starter <starter clone>`, review the diff, then `git push` there.

Then read the latest `journal/*.md` if one exists: open items and findings from the last session.
Do not crawl the repository or re-derive state from prose. If `bootstrap` reports unreconciled
rows, run `uv run arc count-check` before advising on any affected item.

## After a raid

When the player says "raid complete" (or reports a raid), follow
[docs/raid_debrief.md](docs/raid_debrief.md): the questionnaire, the `arc debrief` keep/sell
table, then one checked save. The reasoning behind priorities is in
[docs/strategy.md](docs/strategy.md).

## Writing

- **Never edit `data/*.csv` by hand or with ad-hoc scripts.** Use an `arc` setter. Each one
  takes the write lock, records the player's words as a new Source, runs every rule, refuses
  on any ERROR without writing, saves atomically and commits to git.
- **If an observation does not fit a setter, add a setter** (in `commands.py`, with a test).
  Every wrong value in the legacy tracker came from a write path that bypassed validation.
- Set `ARC_ACTOR` (e.g. `ARC_ACTOR=chatgpt`) so each commit says who wrote it.
- Do not use `--no-commit` outside tests.

## Meaning of the data

- Blank means **unobserved**. `0` means a recorded zero. Never substitute one for the other.
- `unreconciled_holdings` are recorded quantities with **no established location**. They are
  excluded from confirmed totals and goal plans. Only `arc reconcile` with live counts closes
  them. Never assume a slot is empty to close one.
- A fact is stored once. Savings-quest progress is the coin metric; it is never copied.
- Matchup rankings are `tactical_inference`, not measured. Say so when using them.
- `workbook_policies` are imported spreadsheet notes, not current rules or advice.
- Item names resolve by exact id, name or alias (case-insensitive). Never fuzzy-match; add an
  alias.

## After any code change

```sh
uv run ruff format src tests && uv run ruff check src tests && uv run mypy && uv run pytest
```

All four must pass. Record any shortcut you knowingly leave in `docs/architecture_debt.md`.

## Do not

- Touch `legacy/` if it exists. It is a frozen, checksummed import (`SHA256SUMS`).
- Copy one player's `data/` into a package for someone else. Use `arc export-starter`, which keeps
  game facts and leaves the player's stash, history and notes behind.
