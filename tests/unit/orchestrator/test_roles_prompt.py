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
