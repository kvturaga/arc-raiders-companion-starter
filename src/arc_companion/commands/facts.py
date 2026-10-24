"""Game reference facts: stack sizes, dataset imports, augment and Scrappy tables, updates."""

from __future__ import annotations

from pathlib import Path

from ..distribution import STARTER_DATA
from ..enums import (
    SourceKind,
)
from ..model import (
    AugmentCapacity,
    Item,
    ScrappyRate,
    Source,
    StackSize,
)
from ..queries import resolve
from ..reference import (
    AUGMENTS,
    SCRAPPY_RATES,
    DatasetItem,
    apply_dataset,
)
from ..starter import merge_starter
from ..store import State, load
from .core import (
    Change,
    Refused,
)


def set_stack_sizes(observed: dict[str, int]) -> Change:
    """Record stack sizes the player read in game (tooltip "2/3", or two equal merged stacks).

    These outrank dataset rows, which `import_reference` never overwrites.
    """
    if bad := [name for name, units in observed.items() if units < 1]:
        raise Refused(f"a stack holds at least one unit: {', '.join(bad)}")

    def change(state: State, source: Source) -> str:
        shown = []
        for name, units in observed.items():
            item = resolve(state, name)
            state.put(StackSize(item=item, units_per_slot=units, source=source))
            shown.append(f"{item.id}={units}")
        return f"set-stack-size {', '.join(shown)}"

    return change


def import_reference(dataset: dict[str, DatasetItem], *, add_missing: bool = False) -> Change:
    """Apply with `kind=SourceKind.WEB_REFERENCE`; the note names the dataset and commit."""

    def change(state: State, source: Source) -> str:
        if source.kind is not SourceKind.WEB_REFERENCE:
            raise Refused("import-reference must be recorded as a web_reference source")
        return apply_dataset(state, source, dataset, add_missing=add_missing).summary()

    return change


def starter_update(project: Path) -> Change:
    """Bring the merged starter's game facts and goals into this player's data."""

    def change(state: State, source: Source) -> str:
        return merge_starter(state, load(project / STARTER_DATA)).summary()

    return change


def import_scrappy_rates() -> Change:
    """Scrappy's per-round rewards for every level, from the wiki table in `reference.py`."""

    def change(state: State, source: Source) -> str:
        for level, minutes, mat, seeds, ext_mat, ext_seeds in SCRAPPY_RATES:
            for extracted, material, seed in ((False, mat, seeds), (True, ext_mat, ext_seeds)):
                state.put(
                    ScrappyRate(
                        level=level,
                        min_minutes_exclusive=minutes,
                        extracted=extracted,
                        material_quantity=material,
                        seed_quantity=seed,
                        source=source,
                    )
                )
        return f"import-scrappy-rates: {len(SCRAPPY_RATES) * 2} rows, levels 1-5"

    return change


def import_augment_capacities() -> Change:
    """Carry limits per augment, from the wiki table in `reference.py`."""

    def change(state: State, source: Source) -> str:
        missing = []
        for item_id, weight, backpack, quick_use, safe_pocket in AUGMENTS:
            if (item := state.find(Item, item_id)) is None:
                missing.append(item_id)
                continue
            state.put(
                AugmentCapacity(
                    item=item,
                    backpack_slots=backpack,
                    quick_use_slots=quick_use,
                    safe_pocket_slots=safe_pocket,
                    weight_limit=weight,
                    source=source,
                )
            )
        skipped = f"; not in the item list: {', '.join(missing)}" if missing else ""
        return f"import-augment-capacities: {len(AUGMENTS) - len(missing)} augments{skipped}"

    return change
