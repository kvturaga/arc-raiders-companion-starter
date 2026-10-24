"""The player's plans and choices: goals, priorities, standing keep/sell rules, build, skills."""

from __future__ import annotations

import dataclasses

from ..enums import (
    Confidence,
    DispositionAction,
    GoalStatus,
    PreferenceKey,
    QuestionStatus,
)
from ..model import (
    DispositionRule,
    Goal,
    GoalDependency,
    GoalRequirement,
    OpenQuestion,
    PlayerBuild,
    Preference,
    Reservation,
    SkillRank,
    Source,
)
from ..queries import resolve
from ..store import State
from .core import (
    Change,
    Refused,
)


def set_goal_status(goal_id: str, status: GoalStatus) -> Change:
    """Completing a goal releases its reservations in the same write."""

    def change(state: State, source: Source) -> str:
        goal = state.get(Goal, goal_id)
        state.put(dataclasses.replace(goal, status=status, source=source))
        released = []
        if status is GoalStatus.COMPLETE:
            for r in state.all(Reservation):
                if r.goal.id == goal_id:
                    state.remove(r)
                    released.append(f"{r.item.id} x{r.quantity}")
        suffix = f"; released {', '.join(released)}" if released else ""
        return f"set-goal-status {goal_id} = {status}{suffix}"

    return change


def set_skill(skill_id: str, rank: int, maximum: int | None) -> Change:
    def change(state: State, source: Source) -> str:
        skill = state.get(SkillRank, skill_id)
        state.put(
            dataclasses.replace(
                skill,
                rank=rank,
                maximum=skill.maximum if maximum is None else maximum,
                confidence=Confidence.CONFIRMED,
                source=source,
            )
        )
        return f"set-skill {skill_id} = {rank}"

    return change


def resolve_question(question_id: str) -> Change:
    def change(state: State, source: Source) -> str:
        question = state.get(OpenQuestion, question_id)
        state.put(dataclasses.replace(question, status=QuestionStatus.RESOLVED, resolution=source))
        return f"resolve-question {question_id}"

    return change


def set_goal_priority(goal_id: str, priority: int | None) -> Change:
    """Lower runs first. `None` leaves the goal unranked."""

    def change(state: State, source: Source) -> str:
        goal = state.get(Goal, goal_id)
        state.put(dataclasses.replace(goal, priority=priority, source=source))
        return f"set-goal-priority {goal_id} = {priority}"

    return change


def add_goal(
    goal_id: str,
    name: str,
    priority: int | None,
    requirements: dict[str, int],
    after: list[str],
) -> Change:
    """A new active goal with its item requirements and the goals it waits on."""
    if bad := [item for item, qty in requirements.items() if qty < 1]:
        raise Refused(f"requirements must be positive: {', '.join(bad)}")

    def change(state: State, source: Source) -> str:
        if state.find(Goal, goal_id) is not None:
            raise Refused(f"goal {goal_id} already exists")
        goal = Goal(
            id=goal_id, name=name, status=GoalStatus.ACTIVE, priority=priority, source=source
        )
        state.add(goal)
        for item_name, quantity in requirements.items():
            item = resolve(state, item_name)
            state.add(GoalRequirement(goal=goal, item=item, quantity=quantity))
        for prerequisite in after:
            state.add(GoalDependency(goal=goal, prerequisite=state.get(Goal, prerequisite)))
        return f"add-goal {goal_id} ({name}), priority {priority}"

    return change


def set_preference(key: PreferenceKey, value: int) -> Change:
    def change(state: State, source: Source) -> str:
        state.put(Preference(id=key, value=value, source=source))
        return f"set-preference {key} = {value}"

    return change


def set_disposition(item_name: str, action: DispositionAction, keep_total: int) -> Change:
    """A standing keep/sell rule for one item. `hold` keeps everything; `sell`/`recycle` keep
    `keep_total` and move the rest. Goals still outrank it: their needs are always kept."""
    if keep_total < 0:
        raise Refused("keep_total cannot be negative")

    def change(state: State, source: Source) -> str:
        item = resolve(state, item_name)
        state.put(DispositionRule(item=item, action=action, keep_total=keep_total, source=source))
        return f"set-disposition {item.id} = {action}, keep {keep_total}"

    return change


def set_build(
    level: int,
    mobility: int | None,
    conditioning: int | None,
    unspent: int,
    survival: int | None = None,
) -> Change:
    """The player's level and points per tree, read off the skill screen. `None` keeps a tree."""

    def change(state: State, source: Source) -> str:
        build = state.all(PlayerBuild)[0]
        state.put(
            dataclasses.replace(
                build,
                level=level,
                mobility_points=build.mobility_points if mobility is None else mobility,
                conditioning_points=build.conditioning_points
                if conditioning is None
                else conditioning,
                survival_points=build.survival_points if survival is None else survival,
                unspent_points=unspent,
                source=source,
            )
        )
        return f"set-build level {level}, unspent {unspent}"

    return change
