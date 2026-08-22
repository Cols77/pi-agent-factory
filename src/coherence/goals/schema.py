"""Goal artifact parsing and the frozen `Goal` model.

A `goal` is an engineering contract (brief §5.3), not a wish: it carries a
deterministic metric comparison, a target, and — for `/goal create` — the
measurable-contract fields (guardrails, population, baseline, confidence,
budget, stop rule, version).

Parsing mirrors `factory.system.adr.parse_adr`: identity comes from the
frontmatter `id`, a malformed document degrades itself into recorded
`scope_errors` instead of raising, and duplicate ids are the one hard error
(raised by the registry, not here).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import frontmatter

from coherence.goals.lifecycle import GoalState
from substrate.validators.schema import SCHEMA_DIR, validate

_SCHEMA = SCHEMA_DIR / "goal.schema.json"

_GOAL_DIR_PARTS = ("goals",)

DEFAULT_STATE: GoalState = "DECLARED"
DEFAULT_VERSION = 1


@dataclass(frozen=True)
class Goal:
    """One parsed goal. Absent fields are `None`, never a substituted default."""

    id: str
    title: str
    path: Path
    feature: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    metric: dict[str, Any] | None = None
    target: dict[str, Any] | None = None
    state: GoalState = DEFAULT_STATE
    version: int = DEFAULT_VERSION
    created_from: str | None = None
    scope_errors: list[str] = field(default_factory=list)
    # brief §5.3 measurable contract (optional in schema, REQUIRED for `/goal create`).
    guardrails: list[dict[str, Any]] = field(default_factory=list)
    population: dict[str, Any] | None = None
    baseline: dict[str, Any] | None = None
    confidence: dict[str, Any] | None = None
    budget: dict[str, Any] | None = None
    stop_rule: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    evidence: dict[str, Any] | None = None


def _str_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def _as_dict(value: object) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _metric_dict(value: object) -> dict[str, Any] | None:
    """Normalize the schema's string form (`MET-NAV-004`) to the object form.

    The object form requires `source_experiment`; a bare metric id has none
    yet, so the evaluator treats the goal as BLOCKED until one is declared.
    """
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        return {"name": value}
    return None


def _target_dict(value: object) -> dict[str, Any] | None:
    """Normalize the schema's string form (`>= 0.90`) to the object form.

    The string form is `<operator> <value>`; anything unparseable stays as
    recorded and the evaluator refuses to compare it (BLOCKED).
    """
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parts = value.split()
        if len(parts) == 2:
            try:
                return {"operator": parts[0], "value": float(parts[1])}
            except ValueError:
                return None
    return None


def parse_goal(path: Path) -> Goal:
    """Parse one goal file. Never raises: a bad document degrades itself."""
    try:
        post = frontmatter.load(str(path))
    except (OSError, ValueError) as exc:
        return Goal(id="", title="", path=path, scope_errors=[f"{path}: unreadable ({exc})"])

    meta = dict(post.metadata)
    errors = validate(meta, _SCHEMA)

    state = meta.get("state", DEFAULT_STATE)
    if state not in ("DECLARED", "ACTIVE", "EVALUATING", "NOT_REACHED", "REACHED", "REGRESSED", "BLOCKED"):
        state = DEFAULT_STATE
        errors.append("state: unknown GoalState, defaulted to DECLARED")

    return Goal(
        id=str(meta.get("id", "")),
        title=str(meta.get("title", "")),
        path=path,
        feature=_str_list(meta.get("feature")),
        requirements=_str_list(meta.get("requirements")),
        metric=_metric_dict(meta.get("metric")),
        target=_target_dict(meta.get("target")),
        state=state,
        version=int(meta.get("version", DEFAULT_VERSION)),
        created_from=meta.get("created_from"),
        scope_errors=errors,
        guardrails=[g for g in meta.get("guardrails", []) if isinstance(g, dict)],
        population=_as_dict(meta.get("population")),
        baseline=_as_dict(meta.get("baseline")),
        confidence=_as_dict(meta.get("confidence")),
        budget=_as_dict(meta.get("budget")),
        stop_rule=meta.get("stop_rule"),
        history=[h for h in meta.get("history", []) if isinstance(h, dict)],
        evidence=_as_dict(meta.get("evidence")),
    )


def goal_dir(root: Path) -> Path:
    """The directory a goal set lives in (additive glob, mirrors model.py)."""
    return root.joinpath(*_GOAL_DIR_PARTS)


def is_goal_file(path: Path) -> bool:
    return path.name.startswith("GOAL-") and path.suffix == ".md"
