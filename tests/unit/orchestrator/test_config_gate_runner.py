import sys
from pathlib import Path

import pytest

from factory.config import GateStep
from factory.orchestrator.backends import ConfigGateRunner

pytestmark = pytest.mark.unit


def _ok(text: str = "ok") -> GateStep:
    return GateStep(cmd=f'{sys.executable} -c "print(\'{text}\')"')


def _fail(code: int) -> GateStep:
    return GateStep(cmd=f'{sys.executable} -c "import sys; sys.exit({code})"')


def test_runs_steps_in_order_and_passes(tmp_path):
    runner = ConfigGateRunner(tmp_path, {"unit": [_ok("one"), _ok("two")]}, log_dir=tmp_path / "logs")
    assert runner.run("unit") == 0
    log = (tmp_path / "logs" / "unit-gate.log").read_text(encoding="utf-8")
    assert log.index("one") < log.index("two")


def test_first_failure_short_circuits_and_returns_its_code(tmp_path):
    steps = [_fail(3), _ok("never runs")]
    runner = ConfigGateRunner(tmp_path, {"unit": steps}, log_dir=tmp_path / "logs")
    assert runner.run("unit") == 3
    assert "never runs" not in (tmp_path / "logs" / "unit-gate.log").read_text(encoding="utf-8")


def test_undeclared_gate_passes_and_is_recorded_as_skipped(tmp_path):
    runner = ConfigGateRunner(tmp_path, {"unit": [_ok()]}, log_dir=tmp_path / "logs")
    assert runner.run("sim") == 0
    assert runner.skipped == ["sim"]
    assert "not declared" in (tmp_path / "logs" / "sim-gate.log").read_text(encoding="utf-8")


def test_exit_five_is_a_pass_and_is_noted(tmp_path):
    # pytest returns 5 for "no tests collected" -- a declared gate that matches
    # nothing must not be a false red.
    runner = ConfigGateRunner(tmp_path, {"sim": [_fail(5), _ok("still runs")]}, log_dir=tmp_path / "logs")
    assert runner.run("sim") == 0
    log = (tmp_path / "logs" / "sim-gate.log").read_text(encoding="utf-8")
    assert "matched nothing" in log
    assert "still runs" in log


def test_python_placeholder_expands_to_this_interpreter(tmp_path):
    runner = ConfigGateRunner(
        tmp_path, {"unit": [GateStep(cmd='{python} -c "print(1)"')]}, log_dir=tmp_path / "logs"
    )
    assert runner.run("unit") == 0


def test_cwd_is_relative_to_the_repo_root(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "marker.txt").write_text("here", encoding="utf-8")
    step = GateStep(cmd=f'{sys.executable} -c "open(\'marker.txt\')"', cwd="sub")
    runner = ConfigGateRunner(tmp_path, {"unit": [step]}, log_dir=tmp_path / "logs")
    assert runner.run("unit") == 0


def test_without_log_dir_nothing_is_written(tmp_path):
    runner = ConfigGateRunner(tmp_path, {"unit": [_ok()]})
    assert runner.run("unit") == 0
    assert not (tmp_path / "unit-gate.log").exists()
