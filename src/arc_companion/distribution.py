"""Sharing the package: export a starter, set up a copy, and take updates from the starter repo.

Git is the transport. A copy's `UPSTREAM` file names the starter repo; `init` renames the clone's
`origin` so a player's data can never be pushed to the shared repo.
"""

from __future__ import annotations

import csv
import datetime as dt
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .model import (
    StackSize,
)
from .starter import PUBLIC_SOURCES, build_starter
from .store import State, load, write

# What a new player's package contains besides its game facts. `migration/`, `legacy/` and the
# debt notes describe one player's history and stay behind.
SHIPPED = (
    "src/arc_companion",
    "tests/__init__.py",
    "tests/conftest.py",
    "tests/test_starter.py",
    "docs/first_principles.md",
    "docs/data_layer.md",
    "docs/new_player_guide.md",
    "docs/strategy.md",
    "docs/raid_debrief.md",
    "AGENTS.md",
    "LICENSE",
    "NOTICE.md",
    "pyproject.toml",
    "uv.lock",
    ".gitignore",
)


STARTER_REPO = "https://github.com/kvturaga/arc-raiders-companion-starter.git"


STARTER_DATA = "starter_data"


UPSTREAM = "UPSTREAM"  # file holding the starter repo URL; its presence marks a shared copy


README = """# ARC Raiders companion

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
"""


DEBT_STUB = """# Architecture debt

Each entry: what is missing, what it costs to leave it, and what makes it worth fixing.
Record any shortcut knowingly left in the code here.
"""


def export(project: Path, dest: Path, today: dt.date, upstream: str = STARTER_REPO) -> State:
    """Write a new player's package to `dest` and return its game facts.

    `dest` is either new, or a clone of the starter repo whose tracked files are replaced, so
    each publish is one more commit friends can pull. Nobody's `data/` is ever written there.
    """
    if dest.exists() and not (dest / ".git").exists():
        raise FileExistsError(f"{dest} exists and is not a starter repo clone")
    seed = project / "data" if (project / "data").exists() else project / STARTER_DATA
    starter = build_starter(load(seed), today)
    for old in dest.glob("*") if dest.exists() else []:
        if old.name != ".git":
            shutil.rmtree(old) if old.is_dir() else old.unlink()
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".*_cache")
    for name in SHIPPED:
        source = project / name
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, ignore=ignore)
        else:
            shutil.copy2(source, target)
    (dest / "docs" / "architecture_debt.md").write_text(DEBT_STUB)
    pyproject = dest / "pyproject.toml"  # the legacy importer stays behind
    pyproject.write_text(
        pyproject.read_text()
        .replace('arc-legacy = "arc_legacy.cli:main"\n', "")
        .replace('"src/arc_companion", "src/arc_legacy"', '"src/arc_companion"')
    )
    (dest / "README.md").write_text(README)
    (dest / UPSTREAM).write_text(upstream + "\n")
    write(starter, dest / STARTER_DATA)
    load(dest / STARTER_DATA)  # prove it reloads
    write_observations(load(seed), dest / "contrib")
    return starter


def _git(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(project), *args], check=False, capture_output=True, text=True
    )


def upstream_url(project: Path) -> str | None:
    marker = project / UPSTREAM
    return marker.read_text().strip() if marker.exists() else None


def init(project: Path) -> str:
    """Create this player's `data/` from the starter's game facts, and commit it.

    If `origin` is the starter repo, it is renamed `starter`, so a plain `git push` can never
    send a player's data to the shared repo; they add their own private repo as `origin`.
    """
    data, facts = project / "data", project / STARTER_DATA
    if data.exists():
        raise FileExistsError(f"{data} exists; this package is already set up")
    if not facts.exists():
        raise FileNotFoundError(f"{facts} missing; this is not a starter package")
    write(load(facts), data)
    load(data)
    url = upstream_url(project)
    origin = _git(project, "remote", "get-url", "origin").stdout.strip()
    renamed = bool(url) and origin.removesuffix(".git") == (url or "").removesuffix(".git")
    if renamed:
        _git(project, "remote", "rename", "origin", "starter")
    _git(project, "add", "data")
    committed = _git(project, "commit", "-q", "-m", "arc init: my data from starter_data")
    return f"created data/ ({'committed' if committed.returncode == 0 else 'not committed'})" + (
        "; origin renamed to 'starter': add your own private repo as origin" if renamed else ""
    )


@dataclass(frozen=True, slots=True)
class UpdateCheck:
    upstream: str
    new_commits: list[str]

    @property
    def available(self) -> bool:
        return bool(self.new_commits)


def check_update(project: Path) -> UpdateCheck | None:
    """Fetch the starter repo and list commits this copy does not have. None: not a copy."""
    url = upstream_url(project)
    if url is None:
        return None
    fetched = _git(project, "fetch", "-q", url, "main")
    if fetched.returncode != 0:
        raise RuntimeError(f"could not reach {url}: {fetched.stderr.strip()}")
    log = _git(project, "log", "--format=%h %s", "HEAD..FETCH_HEAD").stdout.splitlines()
    return UpdateCheck(upstream=url, new_commits=log)


def take_update(project: Path) -> str:
    """Merge the fetched starter into this copy. Refuses on local changes or conflicts."""
    if _git(project, "status", "--porcelain").stdout.strip():
        raise RuntimeError("uncommitted changes; commit or discard them before updating")
    merged = _git(project, "merge", "--no-edit", "FETCH_HEAD")
    if merged.returncode != 0:
        _git(project, "merge", "--abort")
        raise RuntimeError(f"the update conflicts with local changes:\n{merged.stdout}")
    return _git(project, "rev-parse", "--short", "HEAD").stdout.strip()


CONTRIB_README = """# Observations to contribute back

Game facts players of this package read in game, published so community datasets can use them
(for example [RaidTheory/arcraiders-data](https://github.com/RaidTheory/arcraiders-data), which
this package's item data derives from). Only game facts: nothing here describes anyone's stash.

- `stack_sizes_observed.csv`: units per stash slot, read from a tooltip (`x/max`) or proven by two
  equal stacks after merging. Many are Frozen Trail 2.0 items the dataset does not have yet.

Each row is dated; the game changes between patches, so re-check old rows before relying on them.
To contribute, open an issue or pull request on the dataset with the rows it lacks.
"""


def write_observations(state: State, dest: Path) -> int:
    """Stack sizes recorded from a player's own reading (not a dataset). Returns the row count."""
    rows = sorted(
        (s.item.id, s.item.name, s.units_per_slot, s.source.observed_on.isoformat())
        for s in state.all(StackSize)
        if s.source.kind not in PUBLIC_SOURCES
    )
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "README.md").write_text(CONTRIB_README)
    with (dest / "stack_sizes_observed.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["item_id", "name", "units_per_slot", "observed_on"])
        writer.writerows(rows)
    return len(rows)
