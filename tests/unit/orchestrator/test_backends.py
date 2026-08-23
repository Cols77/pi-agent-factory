import subprocess

import pytest
from factory.config import GateStep
from factory.orchestrator.types import AgentRole, AgentResult
from factory.orchestrator.backends import (
    GATE_NOT_APPLICABLE,
    ConfigGateRunner,
    FakeAgentBackend,
    FakeGateRunner,
    GateRun,
)

pytestmark = pytest.mark.unit


class _FakeSubprocessRunner:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode
        self.commands: list[str] = []

    def __call__(self, command: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        return subprocess.CompletedProcess(command, self.returncode, stdout="", stderr="")


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


def test_fake_gate_run_detail_wraps_a_scripted_int():
    g = FakeGateRunner({"unit": [1, 0]})
    first = g.run_detail("unit")
    assert first.returncode == 1
    assert first.applicable is True  # only GATE_NOT_APPLICABLE (-1) means absent
    assert first.output == ""
    second = g.run_detail("unit")
    assert second.returncode == 0


def test_fake_gate_run_detail_wraps_gate_not_applicable_as_inapplicable():
    g = FakeGateRunner({"sim": [GATE_NOT_APPLICABLE]})
    detail = g.run_detail("sim")
    assert detail.returncode == GATE_NOT_APPLICABLE
    assert detail.applicable is False


def test_fake_gate_run_detail_returns_scripted_gate_run_verbatim():
    scripted = GateRun(
        name="unit",
        returncode=1,
        output="E ConnectionResetError: connection reset by peer",
        applicable=True,
        commands=("python -m pytest -q",),
    )
    g = FakeGateRunner({"unit": [scripted]})
    assert g.run_detail("unit") is scripted


def test_fake_gate_run_returns_scripted_gate_runs_returncode():
    scripted = GateRun(
        name="unit",
        returncode=1,
        output="E ConnectionResetError: connection reset by peer",
        applicable=True,
        commands=("python -m pytest -q",),
    )
    g = FakeGateRunner({"unit": [scripted]})
    assert g.run("unit") == 1  # run() still just the int, backward compatible


def test_fake_gate_run_still_returns_int_when_scripted_with_gate_run():
    g = FakeGateRunner({"unit": [GateRun(name="unit", returncode=0, output="ok", applicable=True)]})
    assert g.run("unit") == 0


def test_fake_gate_run_detail_default_is_applicable_pass():
    g = FakeGateRunner()
    detail = g.run_detail("unit")
    assert detail.returncode == 0
    assert detail.applicable is True


def test_fake_backend_accepts_and_ignores_on_snippet():
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {"n": 1})]})
    seen: list[str] = []
    result = b.run(AgentRole.DEV, "p", on_snippet=seen.append)
    assert result.output["n"] == 1
    assert seen == []  # FakeAgentBackend never calls it -- no real streaming to report


@pytest.mark.parametrize("command", ["pytest -q", "python -m pytest -q"])
def test_config_gate_runner_treats_exit_five_as_pass_for_exact_pytest_tokens(
    tmp_path, monkeypatch, command
):
    fake_run = _FakeSubprocessRunner(5)
    monkeypatch.setattr(subprocess, "run", fake_run)

    runner = ConfigGateRunner(tmp_path, {"unit": [GateStep(cmd=command)]})

    assert runner.run_detail("unit").returncode == 0
    assert fake_run.commands == [command]


def test_config_gate_runner_rejects_pytest_substrings_when_exit_five_is_returned(
    tmp_path, monkeypatch
):
    command = "python -m ruff check pytest-config"
    fake_run = _FakeSubprocessRunner(5)
    monkeypatch.setattr(subprocess, "run", fake_run)

    runner = ConfigGateRunner(tmp_path, {"unit": [GateStep(cmd=command)]})

    assert runner.run_detail("unit").returncode == 5
    assert fake_run.commands == [command]
