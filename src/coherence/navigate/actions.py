"""Confirmed, typed remediation actions for navigation clients.

The service accepts a small enum of action shapes and dispatches directly to
the existing trace/register writers. It never accepts a shell command, a
module path, or an arbitrary callable from a browser request.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from coherence.register import write as register_write
from coherence.trace import write as trace_write

ActionKind = Literal["trace_link", "trace_defer", "register_bind"]


@dataclass(frozen=True)
class Action:
    kind: str
    args: dict[str, object]


class ActionValidationError(ValueError):
    """The request is not one of the typed remediation actions."""


class ConfirmationRequiredError(PermissionError):
    """A valid action was received without an explicit user confirmation."""


def _string(args: dict[str, object], name: str) -> str:
    value = args.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ActionValidationError(f"{name} is required and cannot be blank")
    return value.strip()


def _shape(action: Action, allowed: set[str], required: set[str]) -> None:
    unknown = set(action.args) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ActionValidationError(f"unexpected action argument(s): {names}")
    missing = required - set(action.args)
    if missing:
        names = ", ".join(sorted(missing))
        raise ActionValidationError(f"missing action argument(s): {names}")


def validate_action(action: Action) -> Action:
    """Validate an action's closed shape and return it unchanged."""
    if not isinstance(action, Action):
        raise ActionValidationError("action must be an Action instance")
    if action.kind == "trace_link":
        _shape(action, {"node_id", "relation", "target"}, {"node_id", "relation", "target"})
        _string(action.args, "node_id")
        relation = _string(action.args, "relation")
        if relation not in {"satisfies", "source_plan", "spec"}:
            raise ActionValidationError(f"unsupported trace relation: {relation}")
        _string(action.args, "target")
    elif action.kind == "trace_defer":
        _shape(action, {"node_id", "reason"}, {"node_id", "reason"})
        _string(action.args, "node_id")
        _string(action.args, "reason")
    elif action.kind == "register_bind":
        _shape(
            action,
            {"requirement_id", "experiment", "metric", "assert_expr", "harness", "trials", "window"},
            {"requirement_id", "experiment", "metric", "assert_expr", "trials"},
        )
        for name in ("requirement_id", "experiment", "metric", "assert_expr"):
            _string(action.args, name)
        trials = action.args["trials"]
        if isinstance(trials, bool) or not isinstance(trials, int) or trials < 1:
            raise ActionValidationError("trials must be a positive integer")
        harness = action.args.get("harness")
        if harness is not None and (not isinstance(harness, str) or not harness.strip()):
            raise ActionValidationError("harness must be a non-blank string when provided")
        window = action.args.get("window")
        if window is not None and not isinstance(window, dict):
            raise ActionValidationError("window must be an object when provided")
    else:
        raise ActionValidationError(f"unsupported action kind: {action.kind!r}")
    return action


def _requirement_path(root: Path, requirement_id: str) -> Path:
    if "/" in requirement_id or "\\" in requirement_id or requirement_id != Path(requirement_id).name:
        raise ActionValidationError("requirement_id must be a plain requirement id")
    path = root / "requirements" / f"{requirement_id}.md"
    if not path.is_file():
        raise ActionValidationError(f"requirement does not exist: {requirement_id}")
    return path


def execute_confirmed_action(root: Path, action: Action, *, confirmed: bool = False) -> dict[str, str]:
    """Execute one validated action only after explicit confirmation."""
    validate_action(action)
    if not confirmed:
        raise ConfirmationRequiredError("explicit confirmation is required")

    args = action.args
    if action.kind == "trace_link":
        relation = str(args["relation"])
        if relation == "satisfies":
            path = trace_write.link_satisfies(root, str(args["node_id"]), str(args["target"]))
        elif relation == "source_plan":
            path = trace_write.link_source_plan(root, str(args["node_id"]), str(args["target"]))
        else:
            path = trace_write.link_spec(root, str(args["node_id"]), str(args["target"]))
    elif action.kind == "trace_defer":
        path = trace_write.set_deferred(root, str(args["node_id"]), str(args["reason"]))
    else:
        path = _requirement_path(root, str(args["requirement_id"]))
        trials = args["trials"]
        if not isinstance(trials, int):
            raise ActionValidationError("trials must be a positive integer")
        window = args.get("window")
        if window is not None and not isinstance(window, dict):
            raise ActionValidationError("window must be an object when provided")
        register_write.write_binding(
            path,
            experiment=str(args["experiment"]),
            metric=str(args["metric"]),
            assert_expr=str(args["assert_expr"]),
            harness=str(args["harness"]) if args.get("harness") is not None else None,
            trials=trials,
            window=window,
        )

    return {"kind": action.kind, "path": str(path), "ref": str(path.relative_to(root))}


__all__ = [
    "Action",
    "ActionValidationError",
    "ConfirmationRequiredError",
    "execute_confirmed_action",
    "validate_action",
]
