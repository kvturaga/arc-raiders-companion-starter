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
8. A trinket: sell. Anything else with no recorded use is **check**, not sell: quests,
   projects and research (studying items for points) are not all recorded. Search before selling.

When the player makes a call that should stick ("always keep Hornet Drivers"), record it with
`arc set-disposition` so the next debrief follows it without asking.

## 3. Save each action as the player reports it

Information arrives as a stream: the haul, then a sale, a craft, a move, a reward, a repair.
Save each one when it is said, in its own command, never batched for later. Pass the counter
whenever the player reads it (`--stash-used`, and `--coins` after a sale): the records must
reproduce it, so a missing input is caught on the action that caused it.

| The player says | Command |
| --- | --- |
| unloaded the haul, got a reward, bought | `arc loot "Metal Parts=30" ...` |
| used meds or ammo in the raid | `arc use "Herbal Bandage=2" --from backpack` |
| sold | `arc sell "Toaster=1" ... --coins <n>` |
| crafted | `arc craft "Heavy Ammo=30" --using "Chemicals=6" "Metal Parts=9" --into backpack` |
| recycled | `arc recycle "Mini Centrifuge=1" --into "Advanced Mechanical Components=1" "Canister=2"` |
| moved items | `arc move "Herbal Bandage=2" --from stash --to backpack` |
| traded with an Envoy | `arc trade --give "Bobcat I=1" ... --get "Anvil II=1"` |
| repaired | `arc repair "Light Shield" 100/100 --using "Plastic Parts=4"` |
| Scrappy | `arc claim-scrappy "8s and 11"` |
| mods, upgrades, hand-ins | `arc attach-mod` / `detach-mod` / `upgrade` / `contribute` |

Every one takes `--stash-used <counter>`. If it refuses, an input is missing (A9): ask, never
force. `arc expect --add ... --remove ... --sell ...` states the counter and coins to expect
before the player looks. `arc stocktake` is the full recount: run it from screenshots when the
records and the counter disagree and nobody knows why.

**Playing on another machine, with friends talking.** The game runs on the player's PC with
voice chat on it; the agent listens on a separate machine and cannot see the game (there is no
inventory API). Voice is the input; do not ask for screenshots.

- **Fragments are fine, in any order.** Save each one the moment it is said and echo it back in
  one short line ("saved: +5 Green Light Sticks, stash"), so a mishearing is caught while the
  player still remembers. Nothing waits in the conversation.
- **Mishearings become aliases.** When the transcript renders a name oddly ("secret grenade" for
  Seeker Grenade), confirm once, then `arc add-alias` it so it resolves next time. Never guess.
- **One number per break: the stash counter.** If the records reproduce it, the break is right;
  if not, the gap is inside that break, not three raids back.
- **Pausing costs nothing.** Every fragment is already saved, so "later" is always safe.

**If the raider died**, run `arc record-death` first: every carried slot goes to zero except the
safe pocket, and the losses are recorded. Then save the rest as above.

**If a write was wrong** (a misheard number, the wrong item), `arc undo --note "<why>"` reverts the
last data write as a commit of its own. It undoes one step; correct anything older with a setter.

Then `uv run arc bootstrap` and tell the player the next targets.
