from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SKILL = Path(__file__).resolve().parents[3] / ".pi" / "skills" / "doctor" / "SKILL.md"


def test_the_skill_exists_and_names_every_command():
    text = _SKILL.read_text(encoding="utf-8")
    for command in (
        "factory doctor context",
        "factory doctor mint",
        "factory doctor promote",
        "factory doctor task",
    ):
        assert command in text


def test_the_skill_gives_completion_to_the_agent_not_the_tools():
    text = _SKILL.read_text(encoding="utf-8").lower()
    assert "you decide when the pass is complete" in text
    # The inverse claim belongs to trace-fix, whose gap set is finite and on
    # disk. Copying it here would be the mistake the design's section 2.1 records.
    assert "the tools own enumeration" not in text


def test_the_skill_forbids_batching_approvals():
    assert "one proposal, one confirmation" in _SKILL.read_text(encoding="utf-8").lower()


def test_the_skill_forbids_inventing_a_threshold():
    assert "never invent an assertion threshold" in _SKILL.read_text(encoding="utf-8").lower()
