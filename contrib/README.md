# Observations to contribute back

Game facts players of this package read in game, published so community datasets can use them
(for example [RaidTheory/arcraiders-data](https://github.com/RaidTheory/arcraiders-data), which
this package's item data derives from). Only game facts: nothing here describes anyone's stash.

- `stack_sizes_observed.csv`: units per stash slot, read from a tooltip (`x/max`) or proven by two
  equal stacks after merging. Many are Frozen Trail 2.0 items the dataset does not have yet.

Each row is dated; the game changes between patches, so re-check old rows before relying on them.
To contribute, open an issue or pull request on the dataset with the rows it lacks.
