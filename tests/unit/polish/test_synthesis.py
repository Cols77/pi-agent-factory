import pytest

from factory.orchestrator.backends import FakeAgentBackend
from factory.orchestrator.types import AgentResult, AgentRole
from factory.polish.synthesis import synthesize

pytestmark = pytest.mark.unit


def _backend(findings):
    return FakeAgentBackend(
        {AgentRole.SYNTHESIS: [AgentResult(ok=True, output={"findings": findings})]}
    )


def test_synthesize_parses_multiple_findings():
    backend = _backend([
        {"description": "sign-in button does nothing", "sr": "SR-010"},
        {"description": "PDF is blank", "snapshot": {"route": "/tailor"}},
    ])
    out = synthesize(backend, "the sign in is broken and the pdf is blank", "sign-in")
    assert [f.description for f in out] == ["sign-in button does nothing", "PDF is blank"]
    assert out[0].sr == "SR-010"
    assert out[0].usecase == "sign-in"
    assert out[1].snapshot == {"route": "/tailor"}


def test_prompt_demands_a_fenced_json_block():
    # parse_pi_json returns the LAST ```json block; a prompt that merely asks for
    # "JSON" gets prose or a bare object, parses to {}, and yields zero findings.
    # FakeAgentBackend skips the parser, so only this guards the real contract.
    from factory.polish.synthesis import _PROMPT

    assert "```json" in _PROMPT


def test_synthesize_empty_when_backend_not_ok():
    backend = FakeAgentBackend({AgentRole.SYNTHESIS: [AgentResult(ok=False, output={})]})
    assert synthesize(backend, "nothing actionable", "sign-in") == []
