"""/goal command shim (spec §12 UX, brief §5.3).

Parses the `/goal` user command into goal config and creates a goal artifact
through the deterministic `factory.goals` core. The shim never re-derives
goal state or re-parses a goal file; it maps user input to the core's
functions.

`create_goal` enforces the brief §5.3 contract: a goal is an engineering
contract, so `/goal create` rejects anything without a guardrail set and a
stop rule, listing the missing fields. A goal is never created as REACHED.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import frontmatter

from factory.goals.registry import load_goals
from factory.goals.schema import Goal, parse_goal

_KV = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*)=(\"[^\"]*\"|\S+)")
_CONTRACT_REQUIRED = ("guardrails", "stop_rule")


def parse_goal_cmd(arg: str) -> dict[str, Any]:
    """Parse a `/goal` argument line into goal config (spec §12).

    Two forms are understood:

    * short form -- ``NAV-REQ-021 reacquisition_rate >= 0.90``
      -> ``{requirement, metric, target}``
    * long form -- ``FEAT-NAV-017 "intent" metric=reacquisition_rate
      target=">= 0.90" experiment=SIM-047``
      -> key=value config (feature, title, metric, target, experiment)

    Missing config that is unambiguous to infer is left for the caller to fill
    (the agent may infer, per spec §12); anything contradictory raises.
    """
    kv: dict[str, str] = {}
    for key, value in _KV.findall(arg):
        kv[key.lower()] = value.strip('"')

    # Long form: any key=value config present.
    if kv:
        parsed: dict[str, Any] = dict(kv)
        if "experiment" in kv:
            parsed["source_experiment"] = kv["experiment"]
        # A leading positional that is not part of an assignment is the feature.
        head = re.split(r"\s+", arg.strip(), maxsplit=1)[0]
        if head and "=" not in head:
            parsed.setdefault("feature", head)
        return parsed

    # Short form: <requirement> <metric> <target-expr...>
    head = re.split(r"\s+", arg.strip(), maxsplit=2)
    if len(head) >= 3 and head[1]:
        return {"requirement": head[0], "metric": head[1], "target": head[2]}
    return {}


def create_goal(root: Path, parsed: dict[str, Any]) -> Goal:
    """Create a goal artifact from parsed config; enforce the §5.3 contract.

    Rejects a goal without at least `guardrails` and `stop_rule` (the
    measurable-contract fields), listing what is missing. Never creates as
    REACHED.
    """
    missing = [field for field in _CONTRACT_REQUIRED if not parsed.get(field)]
    if missing:
        raise ValueError(
            f"/goal create requires measurable-contract fields, missing: {', '.join(missing)}"
        )

    goal_id = str(parsed.get("id", "")).strip() or _next_goal_id(root)
    feature = str(parsed.get("feature", "")).strip()
    req = str(parsed.get("requirement", "")).strip()
    requirements = [req] if req else []
    metric = str(parsed.get("metric", "")).strip()
    experiment = str(parsed.get("source_experiment") or parsed.get("experiment") or "").strip()
    target = str(parsed.get("target", "")).strip()
    if not (feature and req and metric and target):
        raise ValueError("/goal create requires feature, requirement, metric and target")

    top = root / "goals"
    top.mkdir(parents=True, exist_ok=True)
    path = top / f"{goal_id}.md"
    if path.exists():
        raise ValueError(f"goal file already exists: {path}")

    meta = {
        "id": goal_id,
        "title": str(parsed.get("title", goal_id)).strip(),
        "feature": [feature],
        "requirements": requirements,
        "metric": {"name": metric, "source_experiment": experiment},
        "target": target,
        "state": "DECLARED",
        "guardrails": list(parsed.get("guardrails", [])),
        "stop_rule": parsed.get("stop_rule"),
        "version": int(parsed.get("version", 1)),
    }
    if parsed.get("confidence"):
        meta["confidence"] = parsed["confidence"]
    if parsed.get("baseline"):
        meta["baseline"] = parsed["baseline"]
    if parsed.get("population"):
        meta["population"] = parsed["population"]

    post = frontmatter.Post(meta["title"], **meta)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return parse_goal(path)


def _next_goal_id(root: Path) -> str:
    existing = set(load_goals(root))
    n = 1
    while f"GOAL-AUTO-{n:03d}" in existing:
        n += 1
    return f"GOAL-AUTO-{n:03d}"


def notify_goal_transition(prev: str, result) -> None:
    """Emit the spec §16/§17 goal-reached/regression notice (Python shim).

    The rich cockpit notification is Inc 4/6; this prints the funnel text so a
    `/goal evaluate` invocation reports the transition deterministically.
    """
    if result.state == "REACHED":
        print("✓ GOAL REACHED")
        print(f"  {result.goal_id}: value {result.value} {result.operator} target {result.target_value}")
    elif result.state == "REGRESSED":
        print("⚠ GOAL REGRESSED")
        print(f"  {result.goal_id}: value {result.value} falls below target {result.target_value} after REACHED")
    else:
        print(f"goal {result.goal_id}: state {result.state}")