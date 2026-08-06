from __future__ import annotations

import pytest

from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.ledger import Task
from factory.orchestrator.nodes import run_dev
from factory.orchestrator.types import (
    AgentResult,
    AgentRole,
    InterruptionReason,
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
    )
    assert outcome is NodeOutcome.PASS
    assert event.attempts == 1
    assert [role for role, _prompt in backend.prompts] == [AgentRole.DEV, AgentRole.DEV]
    continuation = backend.prompts[1][1]
    assert "fresh agent session for the same factory attempt" in continuation
    assert '"prior_session_id": "old-session"' in continuation
    assert "Do not repeat completed work" in continuation


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
