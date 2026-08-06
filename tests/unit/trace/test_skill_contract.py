from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SKILL = Path(__file__).resolve().parents[3] / ".pi" / "skills" / "trace-fix" / "SKILL.md"


def test_the_skill_no_longer_claims_the_tools_own_enumeration():
    # next_gap now returns every pending gap, so the agent chooses which to take.
    assert "own enumeration" not in _SKILL.read_text(encoding="utf-8").lower()


def test_the_skill_says_the_agent_chooses_the_gap():
    text = _SKILL.read_text(encoding="utf-8").lower()
    assert "node_id" in text
    assert "not a queue" in text


def test_the_skill_says_excerpts_may_be_clipped():
    text = _SKILL.read_text(encoding="utf-8").lower()
    assert "truncated" in text
    assert "read the file" in text


def test_the_skill_still_forbids_batching():
    assert "Do not batch" in _SKILL.read_text(encoding="utf-8")


def test_the_skill_still_points_at_the_gate():
    assert "trace_check" in _SKILL.read_text(encoding="utf-8")
