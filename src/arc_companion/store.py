"""CSV <-> typed object graph. One generic codec, driven by the dataclass type hints."""

from __future__ import annotations

import csv
import dataclasses
import datetime as dt
import os
import shutil
import types
import typing
from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeVar

from .model import ENTITIES, Entity

E = TypeVar("E", bound=Entity)
Key = str | tuple[str, ...]


class LoadError(ValueError):
    pass


@dataclasses.dataclass(frozen=True, slots=True)
class Column:
    field: str
    name: str
    kind: type
    optional: bool

    @property
    def is_ref(self) -> bool:
        return issubclass(self.kind, Entity)


def _columns(cls: type[Entity]) -> tuple[Column, ...]:
    hints = typing.get_type_hints(cls)
    result = []
    for field in dataclasses.fields(cls):
        hint = hints[field.name]
        optional = False
        if isinstance(hint, types.UnionType):
            members = [m for m in typing.get_args(hint) if m is not type(None)]
            if len(members) != 1:
                raise TypeError(f"{cls.__name__}.{field.name}: unsupported union {hint}")
            hint, optional = members[0], True
        if not isinstance(hint, type):
            raise TypeError(f"{cls.__name__}.{field.name}: unsupported type {hint}")
        name = f"{field.name}_id" if issubclass(hint, Entity) else field.name
        result.append(Column(field.name, name, hint, optional))
    return tuple(result)


COLUMNS: dict[type[Entity], tuple[Column, ...]] = {cls: _columns(cls) for cls in ENTITIES}


def _encode(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Entity):
        key = key_of(value)
        if not isinstance(key, str):
            raise TypeError(f"{type(value).__name__} has a composite key and cannot be referenced")
        return key
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)


def key_of(entity: Entity) -> Key:
    parts = tuple(_encode(getattr(entity, name)) for name in type(entity).KEY)
    return parts[0] if len(parts) == 1 else parts


class State:
    """All loaded entities, indexed by table and key. Entities are immutable."""

    def __init__(self) -> None:
        self._tables: dict[type[Entity], dict[Key, Entity]] = {cls: {} for cls in ENTITIES}

    def add(self, entity: Entity) -> None:
        table = self._tables[type(entity)]
        key = key_of(entity)
        if key in table:
            raise LoadError(f"{type(entity).TABLE}: duplicate key {key!r}")
        table[key] = entity

    def put(self, entity: Entity) -> None:
        """Insert or replace by key."""
        self._tables[type(entity)][key_of(entity)] = entity

    def remove(self, entity: Entity) -> None:
        del self._tables[type(entity)][key_of(entity)]

    def all(self, cls: type[E]) -> list[E]:
        return typing.cast(list[E], list(self._tables[cls].values()))

    def get(self, cls: type[E], key: Key) -> E:
        try:
            return typing.cast(E, self._tables[cls][key])
        except KeyError:
            raise KeyError(f"{cls.TABLE}: unknown {key!r}") from None

    def find(self, cls: type[E], key: Key) -> E | None:
        return typing.cast(E | None, self._tables[cls].get(key))

    def copy(self) -> State:
        clone = State()
        clone._tables = {cls: dict(rows) for cls, rows in self._tables.items()}
        return clone

    def replace_references(self) -> None:
        """Re-point every reference at the current object for its key.

        Needed after `put` replaces an entity that others reference (e.g. a Station level
        change), so the graph never holds two versions of one fact.
        """
        for cls in ENTITIES:
            refs = [c for c in COLUMNS[cls] if c.is_ref]
            if not refs:
                continue
            table = self._tables[cls]
            for key, entity in list(table.items()):
                changes = {}
                for col in refs:
                    target = getattr(entity, col.field)
                    if target is not None:
                        current = self._tables[col.kind][key_of(target)]
                        if current is not target:
                            changes[col.field] = current
                if changes:
                    table[key] = dataclasses.replace(entity, **changes)


def _decode(col: Column, raw: str, state: State, where: str) -> Any:
    if raw == "":
        if col.optional:
            return None
        raise LoadError(f"{where}: {col.name} is required")
    try:
        if col.is_ref:
            return state.get(typing.cast(type[Entity], col.kind), raw)
        if col.kind is bool:
            if raw not in ("true", "false"):
                raise ValueError(f"expected true/false, got {raw!r}")
            return raw == "true"
        if col.kind is int:
            return int(raw)
        if col.kind is dt.date:
            return dt.date.fromisoformat(raw)
        if issubclass(col.kind, StrEnum):
            return col.kind(raw)
        return raw
    except (ValueError, KeyError) as exc:
        raise LoadError(f"{where}: {col.name}={raw!r}: {exc}") from None


def load(root: Path) -> State:
    """Load and resolve every table. Structural problems raise; rule checks live in checks.py."""
    state = State()
    for cls in ENTITIES:
        path = root / f"{cls.TABLE}.csv"
        if not path.exists():
            raise LoadError(f"missing table {path.name}")
        columns = COLUMNS[cls]
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            expected = [c.name for c in columns]
            present = list(reader.fieldnames or [])
            absent = [c for c in columns if c.name not in present]
            # Data written before an optional column existed still loads: the column is
            # unobserved (blank). Unknown or missing required columns are refused.
            if set(present) - set(expected) or any(not c.optional for c in absent):
                raise LoadError(f"{path.name}: columns {present} != {expected}")
            for line, row in enumerate(reader, start=2):
                if None in row or None in row.values():
                    raise LoadError(f"{path.name}:{line}: wrong number of cells")
                where = f"{path.name}:{line}"
                values = {c.field: _decode(c, row.get(c.name, ""), state, where) for c in columns}
                state.add(cls(**values))
    return state


def write(state: State, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for cls in ENTITIES:
        columns = COLUMNS[cls]
        with (root / f"{cls.TABLE}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow([c.name for c in columns])
            for entity in state.all(cls):
                writer.writerow([_encode(getattr(entity, c.field)) for c in columns])


def save(state: State, root: Path) -> None:
    """Write to a sibling directory, prove it reloads, then swap it in."""
    staging, retired = _siblings(root)
    write(state, staging)
    load(staging)
    for extra in root.glob("*"):
        if extra.suffix != ".csv":
            shutil.copy2(extra, staging / extra.name)
    root.rename(retired)
    staging.rename(root)
    shutil.rmtree(retired)


def _siblings(root: Path) -> tuple[Path, Path]:
    return root.with_name(root.name + ".staging"), root.with_name(root.name + ".retired")


def recover(root: Path) -> None:
    """Finish or discard a save a crash interrupted. Call only while holding the write lock.

    `save` proves staging reloads before either rename, so: with `root` present, staging is an
    unfinished write and retired is the old copy of a finished swap, and both go; with `root`
    gone, the crash fell between the renames and the verified staging becomes `root`.
    """
    staging, retired = _siblings(root)
    if not root.exists():
        (staging if staging.exists() else retired).rename(root)
    for leftover in (staging, retired):
        if leftover.exists():
            shutil.rmtree(leftover)


@contextmanager
def write_lock(project: Path) -> Iterator[None]:
    lock = project / ".arc-write.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if not _stale(lock):
            raise LoadError(f"{lock} is held by another writer (pid inside); not writing") from None
        lock.unlink()  # its writer died without releasing it
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, "w") as handle:
        handle.write(str(os.getpid()))
    try:
        yield
    finally:
        lock.unlink()


def _stale(lock: Path) -> bool:
    """A lock whose writer process no longer exists."""
    try:
        os.kill(int(lock.read_text()), 0)
    except ProcessLookupError:
        return True
    except (ValueError, PermissionError, FileNotFoundError):
        return False  # unreadable, or another user's live process: leave it to a person
    return False


def ensure_tables(root: Path) -> list[str]:
    """Create empty tables a newer engine added, so older data still loads. Returns them."""
    created = []
    for cls in ENTITIES:
        path = root / f"{cls.TABLE}.csv"
        if not path.exists():
            with path.open("w", newline="", encoding="utf-8") as handle:
                csv.writer(handle, lineterminator="\n").writerow(c.name for c in COLUMNS[cls])
            created.append(cls.TABLE)
    return created
