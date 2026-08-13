"""Goal registry: load a goal set, keyed by declared id.

Mirrors `factory.system.adr.load_adrs`: an absent `goals/` directory is a
legitimate state (not an error), a document with no declared id is skipped
without aborting the rest of the set, and a duplicate id is the one hard
error — a `goal:GOAL-###` scope ref must resolve to exactly one document.
"""
from __future__ import annotations

from pathlib import Path

from factory.goals.schema import Goal, goal_dir, is_goal_file, parse_goal


class DuplicateGoalIdError(ValueError):
    """Two goal files declare the same `id`."""


def load_goals(root: Path) -> dict[str, Goal]:
    """Load every goal under `goals/`, keyed by declared id."""
    directory = goal_dir(root)
    if not directory.is_dir():
        return {}
    loaded: dict[str, Goal] = {}
    for path in sorted(p for p in directory.iterdir() if is_goal_file(p)):
        goal = parse_goal(path)
        if not goal.id:
            continue
        if goal.id in loaded:
            raise DuplicateGoalIdError(
                f"Goal id {goal.id!r} is declared by both {loaded[goal.id].path} and {path}"
            )
        loaded[goal.id] = goal
    return loaded


def load_goal(path: Path) -> Goal:
    """Load one goal by file path (convenience over `parse_goal`)."""
    return parse_goal(path)