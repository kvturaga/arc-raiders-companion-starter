# Strategy

How the companion decides what matters, top down. Game facts live in
[first_principles.md](first_principles.md) with sources; this page is the reasoning that uses
them. Each principle names where it shows up in the code or data.

## 1. Progression is the multiplier

Better weapons kill bigger ARC faster, bigger ARC drop more valuable parts, and those parts buy
the next weapon and bench. A weak gun spends a raid's time on enemies that pay little.

- Prioritize the bench levels and blueprints that unlock the next weapon tier (for example
  Gunsmith III opens weapons that need it). Goal order in `arc bootstrap` reflects this.
- Count the ammo supply, not just the gun: a launcher needs a stockpile of ARC Motion Cores and
  Crude Explosives, which come from ARC Alloy. Hold rules protect the inputs.
- Treat weapons that are worn and unused as trade stock rather than repairing them
  (see the Envoy, below).

## 2. Hold what is hard to find

Rare items a future goal needs are a cost already paid. Keep them even before they can be used
(research items, Outpost materials, quest items). Goals and `hold` rules make this explicit, so a
debrief never suggests selling them.

## 3. Barter currencies are money

Some loot is worth more as trade than as coins. The Nomadic Envoy sells weapons (for example an
Anvil II) for a trade value paid in specific items such as ARC drivers and Firefly Burners, and
it refuses others. Keep the items it takes; check its offers before selling them. Trophy Display
pages ask for the same items, so the two compete: decide by which reward moves the top goal.

## 4. Projects clear space

Committing items to a project (Trophy Display, quests) removes them from the stash for good and
pays a reward. When an item is only waiting for a project, commit it as soon as the page allows.

## 5. Stash space is a budget

- Merge stacks; leave mods on weapons (a mod on a weapon shares its slot).
- Keep one full stack of a common crafting input, sell the surplus (debrief rule 7).
- Keep 10–20 slots free for friends and surprises; tighten what is kept as the stash fills.
- Every stash item has a stack size, so the cost of a pickup in slots is known before it is kept.

## 6. Cash is optionality: buy when needed, not when affordable

Coins are the scoreboard, and coins on hand are options: an Envoy trade, a repair, a bargain, a
string of deaths. Free cash beats a purchase you do not need yet.

- Keep a **cash floor** (the `stash_high_cash_threshold` preference). Reaching it makes a big
  purchase *available*; it does not make it due.
- Buy a stash expansion when the **space is needed**: free slots fall into the reserve band
  (`stash_emergency_reserve_slots`), not merely because coins cover the price.
- A purchase must leave coins **at or above the floor**: buying needs the price plus the floor in
  hand (a 150,000 expansion on a 180,000 floor needs 330,000). Then set the next target the same
  way.
- Record the next price when the screen shows it; never plan against a guessed price.

## 7. Death is planned for

Only the safe pocket survives a death. Keep a replacement weapon ready at home, either as a
crafting kit or a finished spare, and put the most valuable small finds in the safe pocket.

## 8. Every number is checked

A count that cannot be physically right (more stacks than slots, a safe pocket over its size)
is a missing input, not noise. Ask, then save. In-game readings outrank the wiki, and the wiki
outranks community datasets.
