import pytest
from factory.orchestrator.types import AgentRole
from factory.orchestrator.roles import ROLE_SKILLS, ROLE_SCOPE, ROLE_PROMPTS

pytestmark = pytest.mark.unit


def test_every_role_has_skills_scope_prompt():
    for role in AgentRole:
        assert ROLE_SKILLS[role]
        assert role in ROLE_SCOPE
        assert ROLE_PROMPTS[role]


def test_review_is_read_only():
    s = ROLE_SCOPE[AgentRole.REVIEW]
    assert s.allow == []
    assert s.bash == "deny"


def test_dev_can_write_src_and_run_bash():
    s = ROLE_SCOPE[AgentRole.DEV]
    assert "src/**" in s.allow
    assert s.bash == "allow"
