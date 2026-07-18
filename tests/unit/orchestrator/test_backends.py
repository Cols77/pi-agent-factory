import pytest
from factory.orchestrator.types import AgentRole, AgentResult
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner

pytestmark = pytest.mark.unit


def test_fake_backend_pops_in_order():
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {"n": 1}), AgentResult(True, {"n": 2})]})
    assert b.run(AgentRole.DEV, "p").output["n"] == 1
    assert b.run(AgentRole.DEV, "p").output["n"] == 2


def test_fake_backend_exhausted_raises():
    b = FakeAgentBackend({AgentRole.DEV: []})
    with pytest.raises(AssertionError):
        b.run(AgentRole.DEV, "p")


def test_fake_gate_defaults_to_zero_then_scripted():
    g = FakeGateRunner({"unit": [1, 0]})
    assert g.run("unit") == 1
    assert g.run("unit") == 0
    assert g.run("sim") == 0  # unscripted default
