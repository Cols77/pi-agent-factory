import pytest
from factory.orchestrator.types import AgentRole
from factory.orchestrator.roles import ROLE_SKILLS, ROLE_SCOPE, ROLE_PROMPTS, Scope

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


def test_planning_roles_have_minimal_artifact_scopes():
    assert ROLE_SCOPE[AgentRole.PLANNING_COMPLEXITY] == Scope(allow=[], bash="deny")
    assert ROLE_SCOPE[AgentRole.PLANNING_ALIGNMENT].allow == [
        ".intent/**",
        "docs/superpowers/specs/**",
    ]
    assert ROLE_SCOPE[AgentRole.PLANNING_PLAN_REVIEW].allow == [
        "docs/superpowers/plans/**",
        "tasks/**",
    ]
    assert ROLE_SCOPE[AgentRole.PLANNING_DERIVATION].allow == [
        "requirements/**",
        "docs/features/**",
        "bundles/**",
    ]
    for role in (
        AgentRole.PLANNING_ALIGNMENT,
        AgentRole.PLANNING_PLAN_REVIEW,
        AgentRole.PLANNING_DERIVATION,
    ):
        assert ROLE_SCOPE[role].bash == "deny"


def test_planning_roles_exclude_other_artifact_classes_and_sensitive_writes():
    alignment = ROLE_SCOPE[AgentRole.PLANNING_ALIGNMENT].allow
    plan = ROLE_SCOPE[AgentRole.PLANNING_PLAN_REVIEW].allow
    derivation = ROLE_SCOPE[AgentRole.PLANNING_DERIVATION].allow
    assert "requirements/**" not in alignment
    assert "bundles/**" not in alignment
    assert "requirements/**" not in plan
    assert "consent/**" not in plan
    assert "src/**" not in derivation
    assert "docs/superpowers/specs/**" not in derivation
    assert "docs/superpowers/plans/**" not in derivation
