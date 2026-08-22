from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def _seed_action_repo(root: Path) -> None:
    (root / "requirements").mkdir()
    (root / "tasks").mkdir()
    (root / "requirements" / "SR-001.md").write_text(
        "---\n"
        "id: SR-001\n"
        "title: A measurable requirement\n"
        "domain: navigation\n"
        "statement: The route is reachable.\n"
        "---\n",
        encoding="utf-8",
    )
    (root / "tasks" / "T-001.md").write_text(
        "---\n"
        "id: T-001\n"
        "title: Implement route\n"
        "---\n",
        encoding="utf-8",
    )


def test_actions_are_allow_listed_and_reject_shell_commands():
    from coherence.navigate.actions import Action, ActionValidationError, validate_action

    with pytest.raises(ActionValidationError):
        validate_action(Action("unknown", {}))
    with pytest.raises(ActionValidationError):
        validate_action(
            Action(
                "trace_defer",
                {"node_id": "T-001", "reason": "later", "command": "rm -rf ."},
            )
        )
    with pytest.raises(ActionValidationError, match="reason"):
        validate_action(Action("trace_defer", {"node_id": "T-001", "reason": "  "}))


def test_actions_require_confirmation_before_calling_typed_writers(tmp_path):
    from coherence.navigate.actions import (
        Action,
        ConfirmationRequiredError,
        execute_confirmed_action,
    )

    _seed_action_repo(tmp_path)
    action = Action(
        "trace_link",
        {"node_id": "T-001", "relation": "satisfies", "target": "SR-001"},
    )

    with pytest.raises(ConfirmationRequiredError):
        execute_confirmed_action(tmp_path, action, confirmed=False)
    assert "satisfies" not in (tmp_path / "tasks" / "T-001.md").read_text(encoding="utf-8")


def test_confirmed_actions_call_only_the_existing_typed_writers(tmp_path):
    from coherence.navigate.actions import Action, execute_confirmed_action

    _seed_action_repo(tmp_path)
    link = execute_confirmed_action(
        tmp_path,
        Action(
            "trace_link",
            {"node_id": "T-001", "relation": "satisfies", "target": "SR-001"},
        ),
        confirmed=True,
    )
    defer = execute_confirmed_action(
        tmp_path,
        Action("trace_defer", {"node_id": "T-001", "reason": "awaiting review"}),
        confirmed=True,
    )
    binding = execute_confirmed_action(
        tmp_path,
        Action(
            "register_bind",
            {
                "requirement_id": "SR-001",
                "experiment": "smoke",
                "metric": "reachability",
                "assert_expr": ">= 1",
                "trials": 1,
            },
        ),
        confirmed=True,
    )

    task_text = (tmp_path / "tasks" / "T-001.md").read_text(encoding="utf-8")
    req_text = (tmp_path / "requirements" / "SR-001.md").read_text(encoding="utf-8")
    assert link["kind"] == "trace_link"
    assert defer["kind"] == "trace_defer"
    assert binding["kind"] == "register_bind"
    assert "satisfies" in task_text and "SR-001" in task_text
    assert "trace_deferred" in task_text and "awaiting review" in task_text
    assert "binding" in req_text and "reachability" in req_text
