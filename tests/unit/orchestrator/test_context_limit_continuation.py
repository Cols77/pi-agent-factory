from __future__ import annotations

import pytest

from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.ledger import Task
from factory.orchestrator.nodes import run_context_gatherer, run_dev, run_review, run_session_review
from factory.orchestrator.types import (
    AgentResult,
    AgentRole,
    InterruptionReason,
    NodeEvent,
    NodeOutcome,
)

pytestmark = pytest.mark.unit


def test_context_limit_gets_fresh_call_without_spending_dev_retry(tmp_path):
    task = Task("T-001", "Continue", "todo", ["tests green"], "body", tmp_path / "task.md")
    backend = FakeAgentBackend(
        {
            AgentRole.DEV: [
                AgentResult(
                    False,
                    {},
                    raw="provider context length exceeded",
                    session_id="old-session",
                    interruption=InterruptionReason.CONTEXT_LIMIT,
                ),
                AgentResult(True, {"done": True}, raw="completed", session_id="new-session"),
            ]
        }
    )
    outcome, event = run_dev(
        backend,
        FakeGateRunner({"unit": [0]}),
        task,
        {"context": {"source_files": []}},
        [],
        tmp_path,
        max_iters=1,
        events=[NodeEvent("context-gather", "pass")],
    )
    assert outcome is NodeOutcome.PASS
    assert event.attempts == 1
    assert [role for role, _prompt in backend.prompts] == [AgentRole.DEV, AgentRole.DEV]
    continuation = backend.prompts[1][1]
    assert "fresh agent session for the same factory attempt" in continuation
    assert '"prior_session_id": "old-session"' in continuation
    assert "Do not repeat completed work" in continuation
    assert "## Completed work already recorded" in continuation
    assert '"context-gather"' in continuation


def test_context_limit_gets_fresh_call_for_context_gatherer(tmp_path):
    task = Task("T-001", "Continue", "todo", ["tests green"], "body", tmp_path / "task.md")
    (tmp_path / "task.md").write_text("body", encoding="utf-8")
    backend = FakeAgentBackend(
        {
            AgentRole.CONTEXT_GATHERER: [
                AgentResult(
                    False,
                    {},
                    raw="provider context length exceeded",
                    session_id="old-context",
                    interruption=InterruptionReason.CONTEXT_LIMIT,
                ),
                AgentResult(
                    True,
                    {
                        "task_id": "T-001",
                        "generated_by": "context-gatherer",
                        "generated_at": "2026-08-07T12:00:00Z",
                        "coherence": {"checks": []},
                        "context": {"task": "task.md", "source_files": [], "skills": []},
                        "reject": None,
                    },
                    raw="completed",
                    session_id="new-context",
                ),
            ]
        }
    )
    outcome, manifest, event = run_context_gatherer(backend, task, tmp_path)
    assert outcome is NodeOutcome.PASS
    assert manifest is not None
    assert event.attempts == 1
    assert [role for role, _prompt in backend.prompts] == [AgentRole.CONTEXT_GATHERER, AgentRole.CONTEXT_GATHERER]
    continuation = backend.prompts[1][1]
    assert "fresh agent session for the same factory attempt" in continuation
    assert "Do not repeat completed work" in continuation


def test_context_limit_gets_fresh_call_for_review(tmp_path):
    task = Task("T-001", "Review", "todo", ["tests green"], "body", tmp_path / "task.md")
    backend = FakeAgentBackend(
        {
            AgentRole.REVIEW: [
                AgentResult(
                    False,
                    {},
                    raw="maximum context length exceeded",
                    session_id="old-review",
                    interruption=InterruptionReason.CONTEXT_LIMIT,
                ),
                AgentResult(
                    True,
                    {"dod_met": True, "findings": [], "confidence": "ok", "verify": []},
                    raw="completed",
                    session_id="new-review",
                ),
            ]
        }
    )
    outcome, event, findings = run_review(
        backend,
        FakeGateRunner({"full": [0]}),
        task,
        [],
        tmp_path,
        events=[NodeEvent("context-gather", "pass")],
    )
    assert outcome is NodeOutcome.PASS
    assert event.attempts == 1
    assert findings == []
    assert [role for role, _prompt in backend.prompts] == [AgentRole.REVIEW, AgentRole.REVIEW]
    continuation = backend.prompts[1][1]
    assert "## Completed work already recorded" in continuation
    assert '"context-gather"' in continuation


def test_context_limit_gets_fresh_call_for_session_review(tmp_path):
    task = Task("T-001", "Session review", "todo", ["tests green"], "body", tmp_path / "task.md")
    backend = FakeAgentBackend(
        {
            AgentRole.SESSION_REVIEW: [
                AgentResult(
                    False,
                    {},
                    raw="context length",
                    session_id="old-session-review",
                    interruption=InterruptionReason.CONTEXT_LIMIT,
                ),
                AgentResult(True, {"done": True}, raw="completed", session_id="new-session-review"),
            ]
        }
    )
    result = run_session_review(
        backend,
        task,
        tmp_path,
        events=[NodeEvent("context-gather", "pass"), NodeEvent("dev", "pass")],
    )
    assert result.ok is True
    assert [role for role, _prompt in backend.prompts] == [AgentRole.SESSION_REVIEW, AgentRole.SESSION_REVIEW]
    continuation = backend.prompts[1][1]
    assert "## Completed work already recorded" in continuation
    assert '"dev"' in continuation


def test_non_context_process_exit_uses_existing_retry_behavior(tmp_path):
    task = Task("T-001", "Retry", "todo", ["tests green"], "body", tmp_path / "task.md")
    backend = FakeAgentBackend(
        {
            AgentRole.DEV: [
                AgentResult(False, {}, interruption=InterruptionReason.PROCESS_EXIT),
                AgentResult(True, {"done": True}),
            ]
        }
    )
    outcome, event = run_dev(
        backend,
        FakeGateRunner({"unit": [1, 0]}),
        task,
        {"context": {"source_files": []}},
        [],
        tmp_path,
        max_iters=2,
    )
    assert outcome is NodeOutcome.PASS
    assert event.attempts == 2
    assert len(backend.prompts) == 2
