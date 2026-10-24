# Raid debrief protocol

When the player says **"raid complete"** (or "back from a raid", "just extracted", "I died"),
the agent runs this protocol. It turns a loose voice report into one checked save and a
keep/sell table. Agents: follow it in order, and ask only for what the player has not said yet.

## 1. Questionnaire

Ask for these, one short list at a time. Screenshots answer most of them at once.

| # | Ask | Why |
| --- | --- | --- |
| 1 | **Extracted or died?** | On death everything carried is lost except the safe pocket. |
| 2 | **Loadout screen as it is now**, before unloading (screenshot is best) | Backpack, quick use, safe pocket, equipment, slot by slot. |
| 3 | **Durability** of weapons, shield and augment (`x/y`) | Decides repair, risk and trade value. |
| 4 | **Mod changes**: anything put on or taken off a weapon | Mods on a weapon share its slot; a detached mod takes its own. |
| 5 | **Used up**: ammo, healing, grenades, deployables | The loadout screenshot usually covers this. |
| 6 | **Scrappy**: the six numbers (or "8s and 11"), rounds collected, any food eaten or queued | Claimed into the stash; checked against the wiki's rate table. |
| 7 | **Projects and trades**: items committed (Trophy Display, quests), Envoy trades, sales | Committed items leave the inventory for good. |
| 8 | **Coins** and the **stash counter** after unloading (stacks merged) | The counter is the proof that the count is complete. |
| 9 | **Where good loot came from**: map, area, container | Builds the loot-location record (player observations outrank guides). |

Never assume an answer. If a number cannot be physically right (more items than slots, a safe
pocket over its size), say so and ask before saving.

## 2. Debrief table

Run `uv run arc debrief "Item=qty" ... --markdown` with the haul and show the table:

| Column | Meaning |
| --- | --- |
| Item, Haul | What came home. |
| Stash after | Stash count once unloaded. |
| Needed by | Open goals still short of it, and by how much. |
| Decision | `keep`, or `sell N, keep M` (or `recycle`). |
| Why | The rule that decided it (below). |
| Coins, Slots freed | What the suggested sale is worth and what it frees. |
| Your call | The player's answer. The agent never sells for them. |

**One row per item, always.** Never merge items into one row ("Metal Parts, Mechanical
Components, Seeds: keep"): each row shows its own decision and the rule behind it. When an agent
overrides the tool's suggestion, the row says so and why ("Keep all (tool said sell 17)").

The rules, in order (code: `views.debrief`):

1. **Gear** (weapons, augments, shields, mods, blueprints, keys): the player decides per piece.
2. **The player's standing rule** for the item (`arc set-disposition`): `hold` keeps everything;
   `sell`/`recycle` keeps the stated number.
3. **Basic materials** are always kept: they feed most crafting.
4. **Raid supplies** (ammo, healing, grenades, deployables) are kept: the player chooses how much
   to carry.
5. **Scrappy food** is kept: each eaten food is +5 of a material.
6. **Goal needs** are always kept, whatever else applies.
7. Anything a recipe uses: keep **one full stack**, sell the rest.
8. Nothing uses it: sell.

When the player makes a call that should stick ("always keep Hornet Drivers"), record it with
`arc set-disposition` so the next debrief follows it without asking.

## 3. Predict, then save

1. `arc predict --add <haul unloaded> --remove <sold, recycled, used, moved out> --sell <sold>`
   states the stash counter and coins the player should now see, and which items spill into or
   free a stack. Tell the player; they read the real numbers.
2. If both match, save in one checked step: `arc stocktake loadout.csv --carry --add ... --remove
   ... --stash-used <counter>`. `loadout.csv` lists the carried slots (with durability in the
   `condition` column); the stash is the records plus the changes. It refuses unless the stash
   reproduces the counter.
3. If they do not match, an input is missing (A9): ask before saving. Never force the numbers.
4. Then: `arc claim-scrappy "8s and 11" --stash-used <counter>` (and `--ate` for eaten food),
   `arc set-metric coins <n>`, `arc attach-mod` / `detach-mod` / `upgrade` for gear changes,
   `arc contribute <goal> <item> <n> [--from raid]` for project hand-ins, and `arc set-disposition`
   or `arc add-goal` for calls the player wants to keep.

Then `uv run arc bootstrap` and tell the player the next targets.
