"""GateRun / run_detail coverage (Task 4, Steps 1-2): run(name) keeps
returning its bare int for every existing caller; run_detail(name) returns
the structured GateRun the runner needs to extract canonical failure
signatures without ever re-running the gate."""
import subprocess
import sys

import pytest

from factory.config import GateStep
from factory.orchestrator.backends import (
    GATE_NOT_APPLICABLE,
    ConfigGateRunner,
    GateRun,
    PYTEST_NO_TESTS_COLLECTED,
)

pytestmark = pytest.mark.unit


def _ok(text: str = "ok") -> GateStep:
    return GateStep(cmd=f'{sys.executable} -c "print(\'{text}\')"')


def _fail(code: int, text: str = "boom") -> GateStep:
    return GateStep(
        cmd=f'{sys.executable} -c "import sys; print(\'{text}\'); sys.exit({code})"'
    )


def test_gate_run_literal_shape_matches_the_spec():
    detail = GateRun(
        name="unit",
        returncode=1,
        output="E ConnectionResetError: connection reset by peer",
        applicable=True,
        commands=("python -m pytest -q",),
        log_path=None,
    )
    assert detail.to_dict() == {
        "name": "unit",
        "returncode": 1,
        "output": "E ConnectionResetError: connection reset by peer",
        "applicable": True,
        "commands": ["python -m pytest -q"],
        "log_path": None,
    }


def test_to_dict_redacts_secrets_from_output():
    secret_line = "connect: postgres://svc_user:hunter2pass@db.internal:5432/prod"
    detail = GateRun(
        name="unit",
        returncode=1,
        output=f"E ConnectionError: could not connect\n{secret_line}\n",
        applicable=True,
    )
    dumped = detail.to_dict()
    assert "hunter2pass" not in dumped["output"]
    assert "svc_user" not in dumped["output"]
    # The in-memory attribute is left untouched -- only to_dict()'s output
    # is redacted/truncated, since that's the one path that reaches the
    # durable session record.
    assert "hunter2pass" in detail.output


def test_to_dict_truncates_output_to_a_bounded_tail():
    # Well past the 8000-char bound, with a distinctive marker at the very
    # end so we can prove the *tail* survives truncation, not the head.
    body = "x" * 20_000
    tail_marker = "END-OF-OUTPUT-MARKER"
    detail = GateRun(
        name="unit",
        returncode=1,
        output=body + tail_marker,
        applicable=True,
    )
    dumped = detail.to_dict()
    assert len(dumped["output"]) <= 8000 + len("…truncated…\n")
    assert dumped["output"].endswith(tail_marker)
    assert dumped["output"].startswith("…truncated…")
    # Full text is still available on the GateRun itself, unredacted and
    # untruncated -- it's only to_dict()'s serialized copy that is bounded.
    assert len(detail.output) == len(body) + len(tail_marker)


def test_run_still_returns_the_bare_int_for_a_pass(tmp_path):
    runner = ConfigGateRunner(tmp_path, {"unit": [_ok("one")]}, log_dir=tmp_path / "logs")
    assert runner.run("unit") == 0


def test_run_still_returns_the_bare_int_for_a_failure(tmp_path):
    runner = ConfigGateRunner(tmp_path, {"unit": [_fail(3)]}, log_dir=tmp_path / "logs")
    assert runner.run("unit") == 3


def test_run_detail_returns_a_gate_run_on_pass(tmp_path):
    runner = ConfigGateRunner(tmp_path, {"unit": [_ok("one")]}, log_dir=tmp_path / "logs")
    detail = runner.run_detail("unit")
    assert isinstance(detail, GateRun)
    assert detail.name == "unit"
    assert detail.returncode == 0
    assert detail.applicable is True
    assert "one" in detail.output


def test_run_detail_captures_output_and_writes_the_same_log_text(tmp_path):
    log_dir = tmp_path / "logs"
    runner = ConfigGateRunner(tmp_path, {"unit": [_fail(1, "kaboom")]}, log_dir=log_dir)
    detail = runner.run_detail("unit")
    assert detail.returncode == 1
    assert "kaboom" in detail.output
    log_text = (log_dir / "unit-gate.log").read_text(encoding="utf-8")
    assert log_text == detail.output
    assert detail.log_path == log_dir / "unit-gate.log"


def test_run_detail_echoes_captured_output_when_no_log_is_configured(tmp_path, capsys):
    runner = ConfigGateRunner(tmp_path, {"unit": [_fail(1, "kaboom")]})
    detail = runner.run_detail("unit")
    assert detail.returncode == 1
    assert "kaboom" in detail.output  # captured even though nothing was written to disk
    assert detail.log_path is None
    assert not (tmp_path / "unit-gate.log").exists()
    captured = capsys.readouterr()
    assert "kaboom" in captured.out
    assert captured.out == detail.output  # same combined text that would have been logged


def test_run_detail_records_every_command_run(tmp_path):
    runner = ConfigGateRunner(tmp_path, {"unit": [_ok("a"), _ok("b")]}, log_dir=tmp_path / "logs")
    detail = runner.run_detail("unit")
    assert len(detail.commands) == 2


def test_first_failure_short_circuits_run_detail_too(tmp_path):
    steps = [_fail(3, "first"), _ok("never runs")]
    runner = ConfigGateRunner(tmp_path, {"unit": steps}, log_dir=tmp_path / "logs")
    detail = runner.run_detail("unit")
    assert detail.returncode == 3
    assert len(detail.commands) == 1
    assert "never runs" not in detail.output


def test_exit_five_is_a_pass_in_run_detail_too(tmp_path):
    runner = ConfigGateRunner(
        tmp_path, {"sim": [_fail(PYTEST_NO_TESTS_COLLECTED), _ok("still runs")]},
        log_dir=tmp_path / "logs",
    )
    detail = runner.run_detail("sim")
    assert detail.returncode == 0
    assert "matched nothing" in detail.output
    assert "still runs" in detail.output


def test_undeclared_gate_is_not_applicable_never_a_fabricated_failure(tmp_path):
    runner = ConfigGateRunner(tmp_path, {"unit": [_ok()]}, log_dir=tmp_path / "logs")
    detail = runner.run_detail("sim")
    assert detail.returncode == GATE_NOT_APPLICABLE
    assert detail.applicable is False
    assert runner.skipped == ["sim"]


def test_run_delegates_to_run_detail_without_a_second_execution(tmp_path, monkeypatch):
    runner = ConfigGateRunner(tmp_path, {"unit": [_ok("one")]}, log_dir=tmp_path / "logs")
    calls = []
    real_run = subprocess.run

    def spy(*a, **kw):
        calls.append(1)
        return real_run(*a, **kw)

    monkeypatch.setattr(subprocess, "run", spy)
    assert runner.run("unit") == 0
    assert len(calls) == 1  # one execution total -- run() never re-runs after run_detail()
