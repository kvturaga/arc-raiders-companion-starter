"""The entity base class and provenance: every fact points at the Source that observed it."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import ClassVar

from ..enums import (
    SourceKind,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class Entity:
    TABLE: ClassVar[str]
    KEY: ClassVar[tuple[str, ...]] = ("id",)


@dataclass(frozen=True, slots=True, kw_only=True)
class Source(Entity):
    """Where a fact came from. `seq` is the proven write order (append order of sources)."""

    TABLE = "sources"
    id: str
    seq: int
    kind: SourceKind
    observed_on: dt.date
    reference: str
