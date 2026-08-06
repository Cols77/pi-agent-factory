from __future__ import annotations

import pytest

from factory.orchestrator.continuation import build_continuation_context
from factory.orchestrator.ledger import Task

pytestmark = pytest.mark.unit


def test_continuation_contains_exact_task_checkpoint_diff_and_gates(tmp_path):
    task = Task(
        id="T-001",
        title="Continue safely",
        status="todo",
        dod=["unit tests pass", "evidence retained"],
        path=tmp_path / "T-001.md",
        body="## Definition of Done\n- unit tests pass\n- evidence retained",
        satisfies=["SR-001"],
    )
    prompt = build_continuation_context(
        task,
        {"node": "dev", "completed": ["context-gather"]},
        "partial agent output",
        "diff --git a/a.py b/a.py\n+change",
        {"unit": "failed"},
    )
    assert "T-001: Continue safely" in prompt
    assert "- unit tests pass" in prompt
    assert '"node": "dev"' in prompt
    assert "+change" in prompt
    assert '"unit": "failed"' in prompt
    assert "partial agent output" in prompt
    assert "Do not repeat completed work" in prompt


def test_continuation_bounds_untrusted_bulk_output(tmp_path):
    task = Task("T-1", "t", "todo", ["x"], "body", tmp_path / "t.md")
    prompt = build_continuation_context(task, {}, "x" * 30_000, "y" * 30_000, {})
    assert len(prompt) < 45_000
    assert prompt.count("earlier content omitted") == 2
