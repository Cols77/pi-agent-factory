import pytest
from pathlib import Path
from factory.orchestrator.types import AgentRole
from factory.orchestrator.ledger import Task
from factory.orchestrator.prompts import compose_prompt

pytestmark = pytest.mark.unit

TASK = Task(id="T-001", title="Do X", status="todo", dod=["crit A"], body="body text", path=Path("t"))


def test_prompt_is_deterministic_and_includes_key_parts():
    kb = [{"id": "kb-0001", "title": "watch arming"}]
    a = compose_prompt(AgentRole.DEV, TASK, manifest=None, kb_entries=kb, feedback="fix Y")
    b = compose_prompt(AgentRole.DEV, TASK, manifest=None, kb_entries=kb, feedback="fix Y")
    assert a == b
    for needle in ["T-001", "Do X", "crit A", "kb-0001", "watch arming", "fix Y", "test-driven-development"]:
        assert needle in a


def test_no_feedback_no_kb_still_valid():
    out = compose_prompt(AgentRole.REVIEW, TASK)
    assert "T-001" in out and "crit A" in out


def test_compose_prompt_tolerates_non_dict_manifest_context():
    """Malformed manifest with context=None should not raise AttributeError."""
    manifest = {"context": None}
    out = compose_prompt(AgentRole.DEV, TASK, manifest=manifest)
    assert isinstance(out, str)
    assert "T-001" in out


def test_compose_prompt_tolerates_non_dict_context_value():
    """Malformed manifest with context as non-dict should degrade gracefully."""
    manifest = {"context": "invalid_string"}
    out = compose_prompt(AgentRole.DEV, TASK, manifest=manifest)
    assert isinstance(out, str)
    assert "T-001" in out
