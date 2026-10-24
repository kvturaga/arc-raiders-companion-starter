# New player guide

This package is your ARC Raiders companion: it remembers what you own, what you are building
toward and why, so an AI agent can give you exact answers instead of guesses. You talk; the agent
runs `arc` commands; every change is checked, sourced and saved to git.

Game rules quoted here come from [first_principles.md](first_principles.md), which links each one
to its source. Anything marked *unsourced* there is not relied on.

## Setup (once)

1. Install [uv](https://docs.astral.sh/uv/) and git.
2. Clone the starter repo:
   `git clone https://github.com/kvturaga/arc-raiders-companion-starter.git arc-companion`
3. Open the folder in your agent:
   - **Claude Code:** open the folder; it reads [AGENTS.md](../AGENTS.md) on its own.
   - **ChatGPT:** use **Codex** (CLI or IDE extension), which also reads `AGENTS.md`. Plain
     ChatGPT chat cannot run commands, so it cannot keep this package up to date.
4. Run `uv sync`, then `uv run arc init`. That creates your own `data/` from the starter's game
   facts and renames the clone's remote to `starter`, so your data can never be pushed to the
   shared repo by accident.
5. Back up your data: create a **private** repo on your own GitHub, then
   `git remote add origin <your repo URL>` and `git push -u origin main`.
6. Run `uv run arc bootstrap`. You should see an empty stash and the starter goals.

## Staying up to date

The package improves over time (new game facts, fixes, better goals). At the start of every
session your agent runs `uv run arc check-update`, which asks the starter repo on GitHub whether
anything is new. If it is, the agent tells you what changed and, on your OK, runs
`uv run arc update`. That brings in the new engine and game facts and **keeps your stash, your
goals, your progress and anything you read in game yourself**. Your in-game readings always win
over a newer wiki value.

## What to tell the agent first

Read these off your screen and say them:

- Stash counter (e.g. `64/64`) and your coins.
- Your player level and skill points.
- Each bench's level (Workshop screen).
- Then do a **full stocktake**: sort the stash by category, merge all stacks, and either read it
  out item by item or send screenshots. The agent saves it in one checked step; the slot count has
  to match your stash counter exactly, which proves nothing was skipped.

## The starter goals

`uv run arc bootstrap` lists them in order. Lower priority numbers come first.

| Priority | Goals | Why |
| --- | --- | --- |
| 10 | Every bench to **level I** | Unlocks crafting at each station. |
| 15 | **Backup kits:** materials for a Ferro I and a Rattler I | So a death never leaves you unarmed (see below). |
| 20 | Every bench to **level II** | The bulk of useful recipes and upgrades. |
| 30 | Every bench to **level III** | Top-tier crafting. |

Ask "what does Gunsmith II still need?" and the agent runs `uv run arc goal gunsmith_2`. The bench
costs come from the wiki's Workshop page (edited after Frozen Trail 2.0). Your own in-game
reading outranks the wiki if they ever disagree: tell the agent and it records yours.

## Death, and why backups matter

- **When you die, you lose everything you carried except what is in your safe pocket.**
- Safe pocket size depends on your augment: the free loadout has **none**, Looting Mk. 1 has 1,
  Looting Mk. 2 has 2. Weapons cannot go in it (except with Looting Mk. 3 Safekeeper).
- So never take your only good weapon into a risky raid without a replacement waiting at home.

Two ways to keep a replacement ready, and the companion tracks both:

1. **Materials kit:** keep enough raw parts to craft a cheap gun right after you die (the starter
   backup-kit goals). Cheap, and it costs no stash slots beyond the materials.
2. **Crafted spare:** a finished weapon sitting in the stash. Faster, but it takes a slot.

Put your most valuable small items in the safe pocket. After a death, tell the agent "I died";
it records what was lost so your counts stay right.

## Building an economy

- **Coins are the scoreboard.** Every raid, the goal is to come home with more value than you took.
- **Extract.** Loot you die with is gone. A short raid you survive beats a long one you do not.
- **Sell what nothing needs.** After each raid, ask the agent which of your new items any goal,
  bench or recipe uses. Items nothing needs are sale candidates; items goals need are kept.
- **Keep hard-to-find items** your future goals need, even before you can use them. Having them is
  a cost already paid.
- **Stash space is money too.** Merging stacks and leaving mods attached to weapons saves slots.
  The companion knows every item's stack size, so it can tell you what a pickup will cost in space.
- **Keep a cash buffer** above your next big purchase (such as a stash expansion) instead of
  spending down to zero.

## Weapons and mods

- Tell the agent which mods are on which weapon. Mods on a weapon ride in the weapon's slot.
- Track durability (the `x/y` number on weapons, shields and augments): it decides when to repair
  and which piece to risk.
- Use cheap weapons for risky raids and keep your best one for runs you expect to win.

## Checklists

**Before a raid**

- [ ] Loadout set; backup kit or spare ready at home.
- [ ] Safe pocket holds the most valuable small items you are carrying.
- [ ] Ammo, healing and shield chargers in quick use.
- [ ] Tell the agent what you are taking and what you are hunting.

**After a raid**: say **"raid complete"** and the agent walks you through
[the debrief](raid_debrief.md):

- [ ] Extracted or died; a screenshot of your loadout before unloading.
- [ ] Durability on weapon, shield and augment; any mod changes.
- [ ] Scrappy's numbers, and any food he ate.
- [ ] Unload, merge stacks, then coins and the stash counter.
- [ ] Go through the keep/sell table and make your calls; standing calls become rules.

**Weekly**

- [ ] Full stocktake (merge stacks, read or screenshot the stash).
- [ ] Review goal order: what is blocking the next bench level?

## How it keeps your data safe

- Every change is checked by rules before it is written; a change that breaks one is refused and
  nothing is written.
- Every change is a git commit with your words as its source, so any mistake can be undone.
- Blank means "not counted yet"; `0` means "counted, none". The agent never guesses one for the
  other.
