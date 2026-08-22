"""Goal registry: load a goal set, keyed by declared id.

Mirrors `factory.system.adr.load_adrs`: an absent `goals/` directory is a
legitimate state (not an error), a document with no declared id is skipped
without aborting the rest of the set, and a duplicate id is the one hard
error — a `goal:GOAL-###` scope ref must resolve to exactly one document.

Persistence: `record` writes a deterministic evaluation outcome back into the
goal file's frontmatter (state + result + evidence + append-only history) and
appends one line to an append-only `goals/<id>-transitions.jsonl` audit log.
Lifecycle transitions are recorded here, never inferred from git history.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import frontmatter

from coherence.goals.evaluator import GoalResult
from coherence.goals.lifecycle import TransitionError, can_transition
from coherence.goals.schema import Goal, goal_dir, is_goal_file, parse_goal


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


def transition_log_path(goal_id: str, root: Path) -> Path:
    """The append-only audit log for one goal (`goals/<id>-transitions.jsonl`)."""
    return goal_dir(root) / f"{goal_id}-transitions.jsonl"


def _read_frontmatter(path: Path) -> tuple[frontmatter.Post, dict[str, Any]]:
    try:
        post = frontmatter.load(str(path))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot record to unreadable goal file {path}: {exc}") from exc
    return post, dict(post.metadata)


def _write_frontmatter_atomic(post: frontmatter.Post, meta: dict[str, Any], path: Path) -> None:
    post.metadata = meta
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(frontmatter.dumps(post), encoding="utf-8")
    os.replace(tmp, path)


def record(result: GoalResult, goal_path: Path) -> Goal:
    """Persist one evaluation outcome into the goal file and audit log.

    Reads the goal's frontmatter, sets `state`/`result`/`evidence`, appends a
    history entry, and writes the file back atomically. The transition log is
    appended, never rewritten — audit history is append-only (spec §15).
    Returns the freshly re-parsed `Goal`.
    """
    post, meta = _read_frontmatter(goal_path)
    prior_state = meta.get("state", "DECLARED")

    recorded_at = str(result.evidence.get("recorded_at", ""))
    meta["state"] = result.state
    meta["result"] = {
        "value": result.value,
        "target": result.target_value,
        "operator": result.operator,
        "passed": result.passed,
    }
    meta["evidence"] = result.evidence
    history = [h for h in meta.get("history", []) if isinstance(h, dict)]
    history.append(
        {
            "state": result.state,
            "value": result.value,
            "target": result.target_value,
            "operator": result.operator,
            "run": result.evidence.get("run"),
            "commit": result.evidence.get("commit"),
            "recorded_at": recorded_at,
        }
    )
    meta["history"] = history
    _write_frontmatter_atomic(post, meta, goal_path)

    _append_transition(goal_path, result, prior_state, recorded_at)
    return parse_goal(goal_path)


def _append_transition(goal_path: Path, result: GoalResult, prior_state: str, recorded_at: str) -> None:
    """Append one line to the goal's transition log (append-only, by timestamp)."""
    log = transition_log_path(result.goal_id, goal_path.parent.parent)
    log.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "goal_id": result.goal_id,
        "from_state": prior_state,
        "to_state": result.state,
        "value": result.value,
        "target": result.target_value,
        "operator": result.operator,
        "run": result.evidence.get("run"),
        "commit": result.evidence.get("commit"),
        "recorded_at": recorded_at,
    }
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")


def set_goal_state(goal_path: Path, to_state: str, *, reason: str = "") -> Goal:
    """Apply a spec §13 lifecycle transition and audit it (append-only).

    The transition must be legal from the goal's current recorded state;
    anything else raises `TransitionError`. The audit entry is appended, never
    rewriting earlier transitions.
    """
    post, meta = _read_frontmatter(goal_path)
    from_state = str(meta.get("state", "DECLARED"))
    if not can_transition(from_state, to_state):
        raise TransitionError(f"{from_state} -> {to_state} not allowed")
    meta["state"] = to_state
    _write_frontmatter_atomic(post, meta, goal_path)

    recorded_at = datetime.now(timezone.utc).isoformat()
    goal_id = str(meta.get("id", ""))
    entry = {
        "goal_id": goal_id,
        "from_state": from_state,
        "to_state": to_state,
        "reason": reason,
        "recorded_at": recorded_at,
    }
    log = transition_log_path(goal_id, goal_path.parent.parent)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return parse_goal(goal_path)
