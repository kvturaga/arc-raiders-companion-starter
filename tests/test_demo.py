from __future__ import annotations

from pathlib import Path

from arc_companion import views
from arc_companion.model import ItemInstance, WeaponAttachment
from arc_companion.queries import stash_slot_math
from arc_companion.store import load


def test_the_demo_player_is_a_consistent_save(project: Path) -> None:
    state = load(project / "data")
    ok, findings = views.audit(state)
    assert ok, findings
    math = stash_slot_math(state)
    assert math.complete
    assert math.implied == math.counter
    rattler = next(i for i in state.all(ItemInstance) if i.item.id == "rattler_ii")
    assert len([a for a in state.all(WeaponAttachment) if a.weapon == rattler]) == 3
