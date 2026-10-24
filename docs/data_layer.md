# Data layer

Each table in `data/` is one class in `src/arc_companion/model.py`. A field typed as another
entity is stored as `<field>_id` and resolved to the object on load; an unknown id fails the
load. Categorical columns are enums (`enums.py`); free text in them fails the load.

## Layers

| Layer | Tables | Changes when |
| --- | --- | --- |
| Provenance | `sources` | every observation (setter) |
| Game reference | `items`, `item_families`, `aliases`, `recipes`, `recipe_inputs`, `recycle_yields`, `item_values`, `scrappy_rates`, `weapon_profiles`, `mod_fits`, `combat_weapons`, `enemies`, `enemy_parts`, `matchups`, `maps`, `map_encounters` | research, patches |
| Save state | `stash_counter`, `account_metrics`, `player_build`, `skill_ranks`, `feats`, `reward_gaps`, `stations`, `holdings`, `item_instances`, `weapon_attachments`, `unreconciled_holdings` | play |
| Plans and preferences | `goals`, `goal_requirements`, `goal_dependencies`, `reservations`, `project_contributions`, `objectives`, `loadout_targets`, `planned_sales`, `disposition_rules`, `preferences` | player decisions |
| History | `raid_reports`, `raid_lines`, `raid_intents`, `inventory_actions`, `transactions`, `reward_batches`, `reward_lines`, `companion_feeds`, `open_questions` | append-mostly |
| Imported reference | `workbook_policies` | never (spreadsheet notes) |

## Inventory: three kinds of row, never mixed

- `holdings`: a fungible stack, **one row per (item, location)**. Quantity blank = not counted.
- `item_instances`: one physical piece tracked individually because it has a condition or
  carries/is an attachment. Counts as 1.
- `unreconciled_holdings`: a recorded quantity whose location is unproven (backpack loot never
  confirmed unloaded; more safe-pocket rows than slots). **Excluded** from confirmed totals and
  plans. Whether a later stash count may already include it is computed from `Source.seq`
  (`queries.recounted_after`), never stored.

`Balance.confirmed` = holdings + instances. `Balance.stash` = the stash part, used for planning.

## Facts stored once

| Fact | Lives in | Not duplicated in |
| --- | --- | --- |
| Coins | `account_metrics.coins` | savings objective (progress computed) |
| Station level | `stations.level` | recipes read it through the reference |
| Goal priority | `goals.priority` | (legacy had a separate table) |
| Conditioning points | `player_build` | (legacy stored as an account metric) |
| Player choices (reserve slots, comfort threshold) | `preferences` | (legacy stored as metrics) |

## Joins worth knowing

- `objectives` target exactly one of `enemy`, `enemy_part`, `item`, chosen by `kind`; a savings
  objective targets none and reads coins.
- `weapon_attachments` link two `item_instances`; the fit and slot must exist in `mod_fits`, and
  the mod is wherever its weapon is.
- `open_questions.raid_report` links a question to its raid when the legacy source was a raid.
