"""Validated setters. The only sanctioned way to change data/.

Every command: lock -> load -> apply a typed change to a copy -> attach a new Source carrying
the player's words -> run every rule -> refuse on any ERROR -> atomic save -> git commit.
If an observation does not fit an existing command, add a command; do not edit CSVs.
"""

from .core import (
    Change,
    Refused,
    apply,
    data_dir,
    undo,
)
from .facts import (
    import_augment_capacities,
    import_reference,
    import_scrappy_rates,
    set_stack_sizes,
    starter_update,
)
from .gear import (
    add_item,
    attach_mod,
    detach_mod,
    upgrade_piece,
)
from .inventory import (
    contribute,
    reconcile,
    set_condition,
    set_count,
    set_metric,
    set_stash,
)
from .plans import (
    add_goal,
    resolve_question,
    set_build,
    set_disposition,
    set_goal_priority,
    set_goal_status,
    set_preference,
    set_skill,
)
from .scrappy import (
    claim_scrappy,
    feed_scrappy,
    parse_scrappy,
    set_scrappy_level,
)
from .stocktake import CountLine, carried_stash, parse_stacks, record_death, stocktake

__all__ = [
    "Change",
    "CountLine",
    "Refused",
    "add_goal",
    "add_item",
    "apply",
    "attach_mod",
    "carried_stash",
    "claim_scrappy",
    "contribute",
    "data_dir",
    "detach_mod",
    "feed_scrappy",
    "import_augment_capacities",
    "import_reference",
    "import_scrappy_rates",
    "parse_scrappy",
    "parse_stacks",
    "reconcile",
    "record_death",
    "resolve_question",
    "set_build",
    "set_condition",
    "set_count",
    "set_disposition",
    "set_goal_priority",
    "set_goal_status",
    "set_metric",
    "set_preference",
    "set_scrappy_level",
    "set_skill",
    "set_stack_sizes",
    "set_stash",
    "starter_update",
    "stocktake",
    "undo",
    "upgrade_piece",
]
