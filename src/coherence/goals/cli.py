"""`factory goals` command-line interface.

Additive on v1: a new `python -m factory.goals` entry model over the same
argparse-subparser pattern `factory.evidence` uses. Subcommands:
`list`, `show`, `create`, `set-state`, `evaluate`, `history`.

Determinism: `list`/`show`/`history` order by recorded/declared identity, never
by filesystem mtime. State changes go through the lifecycle machine.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import frontmatter

from coherence.goals.evaluator import evaluate
from coherence.goals.lifecycle import can_transition
from coherence.goals.registry import load_goals, record, set_goal_state
from coherence.goals.schema import Goal, parse_goal

_VALID_STATES = ("DECLARED", "ACTIVE", "EVALUATING", "NOT_REACHED", "REACHED", "REGRESSED", "BLOCKED")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="factory.goals")
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list")
    listing.add_argument("--repo", default=".")
    listing.add_argument("--json", action="store_true")

    show = sub.add_parser("show")
    show.add_argument("goal_id")
    show.add_argument("--repo", default=".")
    show.add_argument("--json", action="store_true")

    create = sub.add_parser("create")
    create.add_argument("--id", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--feature", required=True)
    create.add_argument("--requirements", required=True, action="append")
    create.add_argument("--metric", required=True)
    create.add_argument("--source-experiment", required=True)
    create.add_argument("--target", required=True)
    create.add_argument("--state", default="DECLARED")
    create.add_argument("--repo", default=".")
    create.add_argument("--json", action="store_true")

    setstate = sub.add_parser("set-state")
    setstate.add_argument("goal_id")
    setstate.add_argument("state", choices=_VALID_STATES)
    setstate.add_argument("--repo", default=".")
    setstate.add_argument("--json", action="store_true")

    ev = sub.add_parser("evaluate")
    ev.add_argument("goal_id")
    ev.add_argument("--value", type=float, required=True)
    ev.add_argument("--run", required=True)
    ev.add_argument("--commit", default="")
    ev.add_argument("--metrics", default="")
    ev.add_argument("--repo", default=".")
    ev.add_argument("--json", action="store_true")

    history = sub.add_parser("history")
    history.add_argument("goal_id")
    history.add_argument("--repo", default=".")
    history.add_argument("--json", action="store_true")
    return parser


def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload))
    else:
        print(json.dumps(payload, indent=2))


def _load_one(root: Path, goal_id: str) -> Goal:
    goals = load_goals(root)
    if goal_id not in goals:
        raise SystemExit(f"no goal with id {goal_id!r}")
    return goals[goal_id]


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(args.repo)
    command = args.command

    if command == "list":
        goals = load_goals(root)
        payload = {
            "goals": [
                {"id": g.id, "title": g.title, "state": g.state, "feature": g.feature}
                for g in goals.values()
            ]
        }
        _emit(payload, args.json)
        return 0

    if command == "show":
        goal = _load_one(root, args.goal_id)
        from coherence.navigate.obligations import obligations_open_count

        obligations_open, obligations_error = obligations_open_count(root, f"goal:{goal.id}")
        _emit(
            {
                "id": goal.id,
                "title": goal.title,
                "state": goal.state,
                "version": goal.version,
                "feature": goal.feature,
                "requirements": goal.requirements,
                "metric": goal.metric,
                "target": goal.target,
                "evidence": goal.evidence,
                "history": goal.history,
                "scope_errors": goal.scope_errors,
                "obligations_open": obligations_open,
                "obligations_error": obligations_error,
            },
            args.json,
        )
        return 0

    if command == "create":
        body = args.title or f"Goal {args.id}"
        top = root / "goals"
        top.mkdir(parents=True, exist_ok=True)
        path = top / f"{args.id}.md"
        if path.exists():
            raise SystemExit(f"goal file already exists: {path}")
        meta = {
            "id": args.id,
            "title": args.title,
            "feature": [args.feature],
            "requirements": list(args.requirements),
            "metric": {"name": args.metric, "source_experiment": args.source_experiment},
            "target": args.target,
            "state": args.state,
        }
        post = frontmatter.Post(body, **meta)
        path.write_text(frontmatter.dumps(post), encoding="utf-8")
        goal = parse_goal(path)
        _emit({"id": goal.id, "path": str(path), "scope_errors": goal.scope_errors}, args.json)
        return 0

    if command == "set-state":
        goal = _load_one(root, args.goal_id)
        if not can_transition(goal.state, args.state):
            raise SystemExit(
                f"illegal transition {goal.state} -> {args.state} (spec §13)"
            )
        updated = set_goal_state(goal.path, args.state, reason=f"CLI set-state {goal.state}->{args.state}")
        _emit({"id": updated.id, "state": updated.state}, args.json)
        return 0

    if command == "evaluate":
        goal = _load_one(root, args.goal_id)
        result = evaluate(
            goal,
            args.value,
            run_id=args.run,
            commit=args.commit,
            metrics_path=Path(args.metrics) if args.metrics else Path(""),
        )
        updated = record(result, goal.path)
        _emit(
            {
                "id": updated.id,
                "state": result.state,
                "passed": result.passed,
                "value": result.value,
                "target": result.target_value,
                "blocked_reason": result.blocked_reason,
            },
            args.json,
        )
        return 0

    if command == "history":
        goal = _load_one(root, args.goal_id)
        _emit({"id": goal.id, "history": goal.history}, args.json)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
