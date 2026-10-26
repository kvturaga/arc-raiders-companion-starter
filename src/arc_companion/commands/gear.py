"""Items and tracked pieces: new items, their spoken names, mods on and off weapons, upgrades."""

from __future__ import annotations

import dataclasses

from ..enums import (
    ItemCategory,
    Location,
    ModSlot,
    WeaponType,
)
from ..model import (
    Alias,
    Holding,
    Item,
    ItemInstance,
    ModFit,
    Source,
    WeaponAttachment,
    WeaponProfile,
)
from ..queries import resolve
from ..store import State
from .core import (
    Change,
    Refused,
    _holding_id,
    _one_piece,
    _piece_from_stock,
    adjust_holding,
)


def add_item(item_id: str, name: str, category: ItemCategory, tier: int | None) -> Change:
    """A new game item, named exactly as the game shows it. `unique_names` refuses a clash."""

    def change(state: State, source: Source) -> str:
        if state.find(Item, item_id) is not None:
            raise Refused(f"item {item_id} already exists")
        state.add(Item(id=item_id, name=name, category=category, family=None, tier=tier))
        return f"add-item {item_id} ({name}, {category})"

    return change


def add_alias(item_name: str, aliases: list[str]) -> Change:
    """Other exact names for an item, e.g. how a voice transcript hears it ("secret grenade").
    An alias that already names a different item is refused; matching stays exact (no fuzz)."""

    def change(state: State, source: Source) -> str:
        item = resolve(state, item_name)
        for alias in aliases:
            try:
                taken = resolve(state, alias)
            except KeyError:
                state.add(Alias(alias=alias, item=item))
                continue
            if taken != item:
                raise Refused(f"{alias!r} already names {taken.id}")
        return f"add-alias {item.id}: {', '.join(aliases)}"

    return change


def attach_mod(
    weapon: str, mod: str, slot: ModSlot, weapon_type: WeaponType | None = None
) -> Change:
    """Record a mod seen on a weapon. The observation is also the source for the fit.

    The weapon may be an instance id or an item with exactly one unit. The mod is taken from
    a free piece or stack where the weapon is, else from the stash (fitting a mod to a carried
    gun takes it from there); only if neither has one is it new to the records.
    """

    def change(state: State, source: Source) -> str:
        attached = {a.mod.id for a in state.all(WeaponAttachment)}
        gun = _one_piece(state, weapon, attached, source)
        if state.find(WeaponProfile, gun.item.id) is None:
            if weapon_type is None:
                raise Refused(f"{gun.item.id} has no weapon profile; pass --weapon-type")
            state.add(WeaponProfile(item=gun.item, weapon_type=weapon_type))
        mod_item = resolve(state, mod)
        for a in state.all(WeaponAttachment):
            if a.weapon.id == gun.id and a.slot is slot:
                raise Refused(f"{gun.id} {slot} already holds {a.mod.item.id}")
        piece = _free_mod(state, mod_item, gun.location, attached, source)
        fit = state.find(ModFit, (mod_item.id, gun.item.id))
        if fit is None:
            state.add(ModFit(mod=mod_item, weapon=gun.item, slot=slot, source=source))
        elif fit.slot is not slot:
            raise Refused(f"{mod_item.id} fits {gun.item.id} in {fit.slot}, not {slot}")
        state.add(WeaponAttachment(weapon=gun, mod=piece, slot=slot, source=source))
        return f"attach-mod {mod_item.id} -> {gun.id} ({slot})"

    return change


def _free_mod(
    state: State, item: Item, at: Location, attached: set[str], source: Source
) -> ItemInstance:
    for place in dict.fromkeys((at, Location.STASH)):
        loose = [
            i
            for i in state.all(ItemInstance)
            if i.item == item and i.location is place and i.id not in attached
        ]
        held = state.find(Holding, _holding_id(item, place))
        if loose:
            piece = loose[0]
        elif held is not None and held.quantity:
            piece = _piece_from_stock(state, item, place, source)
        else:
            continue
        moved = dataclasses.replace(piece, location=at)
        state.put(moved)
        return moved
    return _piece_from_stock(state, item, at, source)


def detach_mod(weapon: str, slot: ModSlot) -> Change:
    """A mod taken off a weapon becomes its own tile where the weapon is (one more slot)."""

    def change(state: State, source: Source) -> str:
        gun = _one_piece(state, weapon, {a.mod.id for a in state.all(WeaponAttachment)}, source)
        fitted = [
            a for a in state.all(WeaponAttachment) if a.weapon.id == gun.id and a.slot is slot
        ]
        if not fitted:
            raise Refused(f"{gun.id} has no mod in {slot}")
        state.remove(fitted[0])
        state.put(dataclasses.replace(fitted[0].mod, source=source))
        return f"detach-mod {fitted[0].mod.item.id} from {gun.id} ({slot})"

    return change


def upgrade_piece(
    piece: str, to_item: str, costs: dict[str, int], condition: tuple[int, int] | None
) -> Change:
    """A tracked piece becomes its next tier: same piece and mods, new item, costs paid from the
    stash. The new durability is recorded when read."""

    def change(state: State, source: Source) -> str:
        attached = {a.mod.id for a in state.all(WeaponAttachment)}
        before = _one_piece(state, piece, attached, source)
        after_item = resolve(state, to_item)
        for name, quantity in costs.items():
            adjust_holding(state, resolve(state, name), -quantity, source)
        current, maximum = condition if condition else (None, None)
        upgraded = dataclasses.replace(
            before,
            item=after_item,
            condition=current,
            condition_max=maximum,
            condition_source=source if condition else None,
            source=source,
        )
        state.put(upgraded)
        if state.find(WeaponProfile, after_item.id) is None:
            old = state.find(WeaponProfile, before.item.id)
            if old is not None:
                state.add(WeaponProfile(item=after_item, weapon_type=old.weapon_type))
        for a in state.all(WeaponAttachment):
            if a.weapon.id == before.id:
                fit = state.find(ModFit, (a.mod.item.id, before.item.id))
                if fit is not None and state.find(ModFit, (a.mod.item.id, after_item.id)) is None:
                    state.add(
                        ModFit(mod=a.mod.item, weapon=after_item, slot=fit.slot, source=source)
                    )
        paid = ", ".join(f"{q} {n}" for n, q in costs.items())
        return f"upgrade {before.item.id} -> {after_item.id} ({paid})"

    return change
