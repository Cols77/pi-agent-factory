from __future__ import annotations

import pytest

from factory.orchestrator.roles import ROLE_PROMPTS
from factory.orchestrator.types import AgentRole

pytestmark = pytest.mark.unit


def test_context_gatherer_prompt_documents_typed_checks():
    prompt = ROLE_PROMPTS[AgentRole.CONTEXT_GATHERER]
    # The vocabulary the factory re-runs must be named so the agent emits it.
    for kind in ("files_exist", "file_contains", "symbol_defined", "anchor_resolves", "test_result"):
        assert kind in prompt
    # Self-attestation is gone: the old "set coherence.proven=false" instruction
    # must not remain (the prompt may still tell the agent NOT to set proven).
    assert "proven=false" not in prompt
    assert "proven=true" not in prompt
    # Coverage requirement is stated.
    assert "Modify:" in prompt


def test_context_gatherer_prompt_bans_invented_file_contains_literals():
    # Regression: T-064 (repo cool_physical_ai_project) was rejected because the
    # gatherer asserted a `file_contains` literal that only exists as a comment in
    # scripts/gates/_proc.py, then resubmitted the identical failing check on the
    # retry. The prompt must require verbatim literals and forbid resubmitting a
    # check the validator already rejected.
    prompt = ROLE_PROMPTS[AgentRole.CONTEXT_GATHERER]
    assert "verbatim" in prompt
    assert "Feedback to address" in prompt
    assert "rejects the run" in prompt


def test_review_prompt_tells_the_agent_bash_is_disabled():
    # roles.py gives REVIEW Scope(bash="deny"), but only CONTEXT_GATHERER's prompt
    # said so. Without it the agent hit the denial at runtime with no guidance and
    # improvised by asking the human to run commands itself.
    prompt = ROLE_PROMPTS[AgentRole.REVIEW]
    assert "bash" in prompt


def test_every_bash_denied_role_says_so_in_its_prompt():
    from factory.orchestrator.roles import ROLE_SCOPE

    for role, scope in ROLE_SCOPE.items():
        if scope.bash == "deny":
            assert "bash" in ROLE_PROMPTS[role], f"{role.value} denies bash without saying so"
