"""Closed vocabularies. Every categorical column in data/ is one of these; free text is rejected."""

from enum import StrEnum


class Location(StrEnum):
    STASH = "stash"
    EQUIPMENT = "equipment"
    BACKPACK = "backpack"
    QUICK_USE = "quick_use"
    SAFE_POCKET = "safe_pocket"
    # Undivided total across carried slots when the exact split was not reported.
    CARRIED = "carried"
    # Owned, destination not yet confirmed.
    UNALLOCATED = "unallocated"


class Confidence(StrEnum):
    """Ordered strongest to weakest; `weakest()` relies on declaration order."""

    CONFIRMED = "confirmed"
    DERIVED = "derived"
    IMPORTED = "imported"
    NEEDS_REFRESH = "needs_refresh"
    UNKNOWN = "unknown"

    @classmethod
    def weakest(cls, values: "list[Confidence]") -> "Confidence":
        order = list(cls)
        return max(values, key=order.index) if values else cls.UNKNOWN


class SourceKind(StrEnum):
    USER_REPORT = "user_report"
    PARTIAL_USER_REPORT = "partial_user_report"
    USER_PREFERENCE = "user_preference"
    WEB = "web"
    WEB_REFERENCE = "web_reference"
    IMPORT = "import"
    ANALYSIS = "analysis"
    MIGRATION = "migration"


class ItemCategory(StrEnum):
    """In-game item types. `UNCLASSIFIED` means not yet sourced, never 'misc'."""

    AMMUNITION = "ammunition"
    AUGMENT = "augment"
    BASIC_MATERIAL = "basic_material"
    BLUEPRINT = "blueprint"
    COSMETIC = "cosmetic"
    CURRENCY = "currency"
    DESIGN = "design"
    KEY = "key"
    MOD = "mod"
    NATURE = "nature"
    QUICK_USE = "quick_use"
    RECYCLABLE = "recyclable"
    REFINED_MATERIAL = "refined_material"
    SHIELD = "shield"
    TOPSIDE_MATERIAL = "topside_material"
    TRINKET = "trinket"
    WEAPON = "weapon"
    UNCLASSIFIED = "unclassified"


class GoalStatus(StrEnum):
    ACTIVE = "active"
    DEFERRED = "deferred"
    BLOCKED = "blocked"
    COMPLETE = "complete"


class ObjectiveKind(StrEnum):
    DESTROY_ENEMY = "destroy_enemy"
    DESTROY_ENEMY_PART = "destroy_enemy_part"
    # Destroy any ARC using a specific item.
    DESTROY_WITH_ITEM = "destroy_with_item"
    # Progress is the live coin metric; it is never stored twice.
    SAVE_COINS = "save_coins"


class MetricKind(StrEnum):
    COINS = "coins"
    RAIDER_TOKENS = "raider_tokens"
    STASH_VALUATION = "stash_valuation"
    NEXT_STASH_EXPANSION_COST = "next_stash_expansion_cost"
    WEEKLY_FEAT_COMPLETIONS_REMAINING = "weekly_feat_completions_remaining"


class PreferenceKey(StrEnum):
    MEDIUM_AMMO_EXTRACTION_RESERVE = "medium_ammo_extraction_reserve"
    STASH_EMERGENCY_RESERVE_SLOTS = "stash_emergency_reserve_slots"
    STASH_COMFORT_USED = "stash_comfort_used"
    STASH_HIGH_CASH_THRESHOLD = "stash_high_cash_threshold"
    USE_FULL_CORE_ITEM_NAMES = "use_full_core_item_names"


class RaidStatus(StrEnum):
    RETURNED_UNLOAD_UNCONFIRMED = "returned_unload_unconfirmed"
    RECONCILED = "reconciled"


class RaidLineKind(StrEnum):
    LOOT = "loot"
    REMAINING = "remaining"
    CONSUMED = "consumed"
    CARRIED_TOTAL = "carried_total"
    RETAINED = "retained"


class IntentStatus(StrEnum):
    PROPOSED = "proposed"
    PLANNED = "planned"
    ON_HOLD = "on_hold"
    BLOCKED = "blocked"
    ATTEMPTED_INCOMPLETE = "attempted_incomplete"
    COMPLETED = "completed"


class TransactionStatus(StrEnum):
    COMPLETED = "completed"
    COMPLETED_COST_UNKNOWN = "completed_cost_unknown"


class ActionKind(StrEnum):
    SELL = "sell"
    RECYCLE = "recycle"
    RECYCLE_OUTPUT = "recycle_output"
    CRAFT_INPUT = "craft_input"
    CRAFT_OUTPUT = "craft_output"
    REPAIR_INPUT = "repair_input"
    COUNT_OBSERVATION = "count_observation"
    LOSS = "loss"
    CARRIED_UNAVAILABLE = "carried_unavailable"


class QuestionStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class RewardBatchStatus(StrEnum):
    PENDING_CLAIM = "pending_claim"
    CLAIMED = "claimed"


class FeedStatus(StrEnum):
    QUEUED = "queued"
    CONSUMED = "consumed"
    RETURNED = "returned"


class UnreconciledReason(StrEnum):
    # Raid loot recorded in the backpack with no confirmed unload.
    UNLOAD_UNCONFIRMED = "unload_unconfirmed"
    # More rows claimed for a location than it can physically hold.
    LOCATION_OVER_CAPACITY = "location_over_capacity"


class DispositionAction(StrEnum):
    SELL = "sell"
    RECYCLE = "recycle"
    HOLD = "hold"


class MatchupRole(StrEnum):
    PREFERRED = "preferred"
    VIABLE = "viable"
    BACKUP = "backup"
    AVOID_PRIMARY = "avoid_primary"


class Basis(StrEnum):
    """How a claim is known. Inference is never presented as a sourced fact."""

    SOURCED = "sourced"
    TACTICAL_INFERENCE = "tactical_inference"


class BlueprintState(StrEnum):
    CONFIRMED = "confirmed"
    NOT_REQUIRED = "not_required"
    UNKNOWN = "unknown"


class Penetration(StrEnum):
    STRONG = "strong"
    VERY_STRONG = "very_strong"


class WeaponType(StrEnum):
    ASSAULT_RIFLE = "assault_rifle"
    BATTLE_RIFLE = "battle_rifle"
    HAND_CANNON = "hand_cannon"
    LMG = "lmg"
    PISTOL = "pistol"
    SHOTGUN = "shotgun"
    SMG = "smg"
    SNIPER_RIFLE = "sniper_rifle"
    SPECIAL = "special"


class ModSlot(StrEnum):
    MUZZLE = "muzzle"
    UNDERBARREL = "underbarrel"
    MAGAZINE = "magazine"
    STOCK = "stock"


class Severity(StrEnum):
    ERROR = "error"
    WARN = "warn"
    INFO = "info"
