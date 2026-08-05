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


def test_subprocess_gate_reports_not_applicable_when_the_project_has_no_such_gate(tmp_path):
    # The factory has no sim tests once the drone leaves. A gate the project does
    # not provide must be distinguishable from a gate that ran and failed.
    from factory.orchestrator.backends import GATE_NOT_APPLICABLE, SubprocessGateRunner

    assert SubprocessGateRunner(tmp_path).run("sim") == GATE_NOT_APPLICABLE


def test_subprocess_gate_runs_a_script_the_project_does_provide(tmp_path):
    from factory.orchestrator.backends import GATE_NOT_APPLICABLE, SubprocessGateRunner

    gates = tmp_path / "scripts" / "gates"
    gates.mkdir(parents=True)
    (gates / "sim_smoke.py").write_text("import sys\nsys.exit(0)\n", encoding="utf-8")

    result = SubprocessGateRunner(tmp_path).run("sim")

    assert result == 0
    assert result != GATE_NOT_APPLICABLE


def test_a_provided_gate_that_fails_still_reports_its_failure(tmp_path):
    from factory.orchestrator.backends import GATE_NOT_APPLICABLE, SubprocessGateRunner

    gates = tmp_path / "scripts" / "gates"
    gates.mkdir(parents=True)
    (gates / "sim_smoke.py").write_text("import sys\nsys.exit(3)\n", encoding="utf-8")

    result = SubprocessGateRunner(tmp_path).run("sim")

    assert result == 3
    assert result != GATE_NOT_APPLICABLE


def test_a_gate_that_collects_no_tests_is_not_applicable(tmp_path):
    # pytest exits 5 when nothing is collected -- "the project has no such suite",
    # not "the suite failed".
    from factory.orchestrator.backends import GATE_NOT_APPLICABLE, SubprocessGateRunner

    gates = tmp_path / "scripts" / "gates"
    gates.mkdir(parents=True)
    (gates / "sim_smoke.py").write_text("import sys\nsys.exit(5)\n", encoding="utf-8")

    assert SubprocessGateRunner(tmp_path).run("sim") == GATE_NOT_APPLICABLE


def test_integration_gate_on_a_repo_without_that_suite_is_not_applicable(tmp_path):
    from factory.orchestrator.backends import GATE_NOT_APPLICABLE, SubprocessGateRunner

    assert SubprocessGateRunner(tmp_path).run("integration") == GATE_NOT_APPLICABLE
