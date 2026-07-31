from pathlib import Path

import pytest
from factory.orchestrator.types import AgentRole, AgentResult
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner, SubprocessGateRunner

pytestmark = pytest.mark.unit

# tests/unit/orchestrator/test_backends.py -> repo root is 3 parents up.
_REPO_ROOT = Path(__file__).resolve().parents[3]


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


def test_fake_backend_accepts_and_ignores_on_snippet():
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {"n": 1})]})
    seen: list[str] = []
    result = b.run(AgentRole.DEV, "p", on_snippet=seen.append)
    assert result.output["n"] == 1
    assert seen == []  # FakeAgentBackend never calls it -- no real streaming to report


def test_subprocess_gate_runner_writes_log_when_log_dir_set(tmp_path: Path):
    # "sim" (not "unit") on purpose: the unit gate shells out to `pytest -m
    # unit`, which would pick this very test file back up and recurse
    # forever. The sim suite is a separate, disjoint marker, so it is safe to
    # invoke for real here while still exercising a real gate script/process.
    log_dir = tmp_path / "logs"
    runner = SubprocessGateRunner(_REPO_ROOT, log_dir=log_dir)

    rc = runner.run("sim")

    log_path = log_dir / "sim-gate.log"
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert content.strip() != ""
    assert rc == 0


def test_subprocess_gate_runner_no_log_dir_writes_nothing(tmp_path: Path):
    runner = SubprocessGateRunner(_REPO_ROOT)  # log_dir defaults to None

    rc = runner.run("sim")

    assert rc == 0
    assert list(tmp_path.iterdir()) == []
