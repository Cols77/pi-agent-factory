from __future__ import annotations

import pytest

from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.execution import RunExecution
from factory.orchestrator.git_ops import FakeGitOps
from factory.orchestrator.ledger import Task
from factory.orchestrator.runner import run_task
from factory.orchestrator.types import AgentRole, NodeEvent, NodeOutcome

pytestmark = pytest.mark.unit


def test_exception_after_dev_leaves_validation_as_deterministic_next_node(tmp_path, monkeypatch):
    task = Task("T-001", "Checkpoint", "todo", ["works"], "body", tmp_path / "task.md")
    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", task.id, git.head, git)
    monkeypatch.setattr(
        "factory.orchestrator.runner.run_context_gatherer",
        lambda *_args, **_kwargs: (
            NodeOutcome.PASS,
            {"context": {"source_files": []}},
            NodeEvent("context-gather", "pass"),
        ),
    )
    monkeypatch.setattr(
        "factory.orchestrator.runner.run_dev",
        lambda *_args, **_kwargs: (NodeOutcome.PASS, NodeEvent("dev", "pass")),
    )
    monkeypatch.setattr(
        "factory.orchestrator.runner.run_validation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("power loss")),
    )

    with pytest.raises(RuntimeError, match="power loss"):
        run_task(
            task,
            FakeAgentBackend({}),
            FakeGateRunner(),
            tmp_path,
            git_ops=git,
            execution=execution,
            start_commit=git.head,
        )

    checkpoint = execution.journal.latest()
    assert checkpoint is not None
    assert checkpoint.node == "validation"
    assert [item["node"] for item in checkpoint.completed] == ["context-gather", "dev"]


def test_resume_does_not_rerun_completed_context_or_dev(tmp_path, monkeypatch):
    task = Task("T-001", "Resume", "todo", ["works"], "body", tmp_path / "task.md")
    git = FakeGitOps(head="a" * 40)
    execution = RunExecution.create(tmp_path, "run-1", task.id, git.head, git)
    execution.record(
        node="context-gather",
        state="completed",
        attempt=1,
        next_node="dev",
        remaining={"dev": 3},
        data={
            "outcome": "pass",
            "manifest": {"context": {"source_files": []}},
            "event": {"node": "context-gather", "result": "pass", "attempts": 1, "extra": {}},
        },
    )
    checkpoint = execution.record(
        node="dev",
        state="completed",
        attempt=1,
        next_node="validation",
        remaining={"dev": 2},
        data={
            "outcome": "pass",
            "event": {"node": "dev", "result": "pass", "attempts": 1, "extra": {}},
        },
    )
    monkeypatch.setattr(
        "factory.orchestrator.runner.run_context_gatherer",
        lambda *_args, **_kwargs: pytest.fail("completed context gathering was rerun"),
    )
    monkeypatch.setattr(
        "factory.orchestrator.runner.run_dev",
        lambda *_args, **_kwargs: pytest.fail("completed development was rerun"),
    )
    monkeypatch.setattr(
        "factory.orchestrator.runner.run_validation",
        lambda *_args, **_kwargs: (NodeOutcome.PASS, NodeEvent("validation", "pass")),
    )
    monkeypatch.setattr(
        "factory.orchestrator.runner.run_review",
        lambda *_args, **_kwargs: (NodeOutcome.PASS, NodeEvent("review", "pass"), []),
    )

    result = run_task(
        task,
        FakeAgentBackend({AgentRole.DEV: []}),
        FakeGateRunner(),
        tmp_path,
        git_ops=git,
        execution=execution,
        resume=checkpoint,
        start_commit=git.head,
    )
    assert result.outcome == "completed"
    assert [event.node for event in result.events][:2] == ["context-gather", "validation"]
