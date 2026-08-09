import subprocess
import sys
from pathlib import Path

import pytest

from factory.config import GateStep
from factory.orchestrator.backends import GATE_NOT_APPLICABLE, ConfigGateRunner

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


def test_undeclared_gate_is_not_applicable_and_is_recorded_as_skipped(tmp_path):
    # Not 0: run_validation treats not-applicable and pass alike as non-failing,
    # but only 0 means a suite actually ran. Returning 0 here would report a gate
    # nobody declared as one that passed.
    runner = ConfigGateRunner(tmp_path, {"unit": [_ok()]}, log_dir=tmp_path / "logs")
    assert runner.run("sim") == GATE_NOT_APPLICABLE
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


def test_python_placeholder_is_quoted_when_the_interpreter_path_has_a_space(tmp_path, monkeypatch):
    """The runner uses shell=True, so an unquoted {python} expansion whose
    path contains a space (e.g. 'C:\\Users\\First Last\\...') splits into two
    shell tokens and every gate fails. Reproduce that path shape by making
    sys.executable resolve through a directory junction/symlink whose name
    contains a space, pointing at the real interpreter's install root (not
    just its immediate directory -- a venv's python.exe locates pyvenv.cfg
    relative to itself, so only mirroring the whole root keeps it runnable)."""
    exe = Path(sys.executable).resolve()
    real_root = exe.parent.parent  # venv root: real_root/Scripts|bin/python(.exe)
    rel_exe = exe.relative_to(real_root)
    spaced_dir = tmp_path / "a b"

    if sys.platform == "win32":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(spaced_dir), str(real_root)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            pytest.skip(f"could not create a directory junction: {result.stderr or result.stdout}")
    else:
        spaced_dir.symlink_to(real_root)

    spaced_python = spaced_dir / rel_exe
    assert spaced_python.exists(), "junction/symlink did not expose the interpreter"

    monkeypatch.setattr(sys, "executable", str(spaced_python))

    runner = ConfigGateRunner(
        tmp_path, {"unit": [GateStep(cmd='{python} -c "print(1)"')]}, log_dir=tmp_path / "logs"
    )
    assert runner.run("unit") == 0


def test_python_placeholder_uses_the_target_repos_interpreter(tmp_path, monkeypatch):
    """`{python}` must be the TARGET repo's interpreter, not the orchestrator's.

    On a cross-repo run (`--repo <other>`), sys.executable is the factory's own
    venv, which does not have the target project installed. Every gate then ran
    in the wrong environment: in cool_physical_ai_project this surfaced as 33
    collection errors, `ModuleNotFoundError: No module named 'drone'`, which
    escalated T-059 as "unit tests red" even though the code was importable in
    its own venv.
    """
    venv_bin = tmp_path / ".venv" / ("Scripts" if sys.platform == "win32" else "bin")
    venv_bin.mkdir(parents=True)
    target_python = venv_bin / ("python.exe" if sys.platform == "win32" else "python")
    # A real interpreter, reachable only via the target repo's .venv path.
    target_python.write_bytes(Path(sys.executable).read_bytes())

    runner = ConfigGateRunner(
        tmp_path, {"unit": [GateStep(cmd="{python} -c \"pass\"")]}, log_dir=tmp_path / "logs"
    )
    captured = {}
    real_run = subprocess.run

    def spy(cmd, *a, **kw):
        captured["cmd"] = cmd
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(subprocess, "run", spy)
    runner.run("unit")
    assert str(target_python) in captured["cmd"], (
        f"gate used {captured['cmd']!r}; expected the target repo's venv interpreter"
    )


def test_python_placeholder_falls_back_when_target_has_no_venv(tmp_path, monkeypatch):
    """A target repo without a .venv still has to run: fall back to the
    orchestrator's own interpreter rather than failing to resolve."""
    runner = ConfigGateRunner(
        tmp_path, {"unit": [GateStep(cmd="{python} -c \"pass\"")]}, log_dir=tmp_path / "logs"
    )
    captured = {}
    real_run = subprocess.run

    def spy(cmd, *a, **kw):
        captured["cmd"] = cmd
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(subprocess, "run", spy)
    assert runner.run("unit") == 0
    assert sys.executable in captured["cmd"]
