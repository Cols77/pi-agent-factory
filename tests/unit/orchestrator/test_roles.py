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


def test_dev_can_write_code_and_traceability_artifacts_and_run_bash():
    s = ROLE_SCOPE[AgentRole.DEV]
    assert "src/**" in s.allow
    assert "tests/**" in s.allow
    assert "docs/traceability/**" in s.allow
    assert "requirements/**" not in s.allow
    assert s.bash == "allow"


def test_session_review_role_has_kb_write_scope():
    scope = ROLE_SCOPE[AgentRole.SESSION_REVIEW]
    assert "kb/**" in scope.allow
    assert "sessions/**" in scope.allow
    assert scope.bash == "deny"


def test_session_review_role_names_session_report_skill():
    assert ROLE_SKILLS[AgentRole.SESSION_REVIEW] == ["session-report"]


def test_session_writer_role_no_longer_exists():
    assert not hasattr(AgentRole, "SESSION_WRITER")
