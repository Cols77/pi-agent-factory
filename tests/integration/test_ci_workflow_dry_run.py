import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from coherence.policy.ci import required_ci_commands


pytestmark = pytest.mark.integration


def _workflow_steps(repo_root: Path) -> list[dict]:
    workflow = yaml.safe_load(
        (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    return workflow["jobs"]["gates"]["steps"]


def _workflow_step(repo_root: Path, name: str) -> dict:
    return next(step for step in _workflow_steps(repo_root) if step.get("name") == name)


def test_required_ci_commands_resolves_a_well_formed_list_against_this_repo():
    repo_root = Path(__file__).resolve().parents[2]
    commands = required_ci_commands(repo_root)

    assert commands, "required_ci_commands must resolve at least one command"
    assert all(isinstance(command, str) and command.strip() for command in commands)
    assert "coherence trace check" in commands
    assert "coherence register check" in commands
    assert any("pytest" in command and "-m unit" in command for command in commands)


def test_workflow_installs_the_runtime_and_locked_dependencies():
    repo_root = Path(__file__).resolve().parents[2]
    steps = _workflow_steps(repo_root)

    assert any(step.get("uses") == "actions/setup-python@v5" for step in steps)
    assert any(step.get("uses") == "actions/setup-node@v4" for step in steps)
    assert any(step.get("run") == "python -m pip install uv" for step in steps)
    assert any("npm ci --prefix pi-ext/factory-watch" in step.get("run", "") for step in steps)
    assert any(step.get("run") == "uv sync --locked" for step in steps)


def _write_fake_executables(
    fake_bin: Path, exits: dict[str, int], marker: Path
) -> None:
    by_executable: dict[str, list[tuple[list[str], str, int]]] = {}
    for command, exit_code in exits.items():
        argv = shlex.split(command)
        assert argv
        by_executable.setdefault(Path(argv[0]).name, []).append(
            (argv[1:], command, exit_code)
        )

    for executable, cases in by_executable.items():
        lines = ["#!/usr/bin/env bash", "set -u"]
        if executable == "python":
            lines.extend(
                [
                    'if [ "${1-}" = "-c" ]; then',
                    f"  exec {shlex.quote(sys.executable)} \"$@\"",
                    "fi",
                ]
            )
        for args, command, exit_code in cases:
            expected_args = shlex.quote(" ".join(args))
            lines.extend(
                [
                    f'if [ "$*" = {expected_args} ]; then',
                    f"  printf '%s\\n' {shlex.quote(command)} >> \"$GATE_MARKER\"",
                    f"  exit {exit_code}",
                    "fi",
                ]
            )
        lines.append("exit 127")
        script = fake_bin / executable
        script.write_text("\n".join(lines) + "\n", encoding="utf-8")
        script.chmod(0o755)


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="requires bash on a non-Windows system",
)
def test_workflow_executes_install_commands_in_order_against_fake_tools(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    fake_bin = tmp_path / "bin"
    marker = tmp_path / "install-marker"
    fake_bin.mkdir()
    commands = [
        "python -m pip install uv",
        "npm ci --prefix pi-ext/factory-watch",
        "uv sync --locked",
    ]
    _write_fake_executables(fake_bin, {command: 0 for command in commands}, marker)
    env = dict(
        os.environ,
        GATE_MARKER=str(marker),
        PATH=f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
    )

    for step_name in (
        "Install uv",
        "Install extension dependencies",
        "Sync locked Python environment",
    ):
        subprocess.run(
            [
                "bash",
                "-euo",
                "pipefail",
                "-c",
                _workflow_step(repo_root, step_name)["run"],
            ],
            cwd=repo_root,
            env=env,
            check=True,
        )

    assert marker.read_text(encoding="utf-8").splitlines() == commands


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="requires bash on a non-Windows system",
)
def test_workflow_puts_the_synced_venv_on_github_path(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    path_file = tmp_path / "github-path"
    env = dict(os.environ, GITHUB_PATH=str(path_file))

    subprocess.run(
        [
            "bash",
            "-euo",
            "pipefail",
            "-c",
            _workflow_step(repo_root, "Add synced environment to PATH")["run"],
        ],
        cwd=repo_root,
        env=env,
        check=True,
    )

    assert path_file.read_text(encoding="utf-8") == f"{repo_root}/.venv/bin\n"


def _run_workflow_gate_loop(
    tmp_path: Path,
    repo_root: Path,
    label: str,
    commands: list[str],
    exits: dict[str, int],
) -> tuple[subprocess.CompletedProcess[str], Path]:
    case_root = tmp_path / label
    runner_temp = case_root / "runner-temp"
    fake_bin = case_root / "bin"
    marker = case_root / "marker"
    runner_temp.mkdir(parents=True)
    fake_bin.mkdir()
    (runner_temp / "required-gates.txt").write_text(
        "\n".join(commands) + "\n", encoding="utf-8"
    )
    _write_fake_executables(fake_bin, exits, marker)
    env = dict(
        os.environ,
        RUNNER_TEMP=str(runner_temp),
        GATE_MARKER=str(marker),
        PATH=f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
    )

    result = subprocess.run(
        [
            "bash",
            "-euo",
            "pipefail",
            "-c",
            _workflow_step(repo_root, "Run required CI gates")["run"],
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )
    return result, marker


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="requires bash on a non-Windows system",
)
def test_workflow_gate_loop_runs_every_resolved_command_in_order(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    first = "python -m pytest -m unit -q --ignore=tests/gates/test_all_gate.py"
    second = "python -m ruff check ."
    result, marker = _run_workflow_gate_loop(
        tmp_path,
        repo_root,
        "ordered",
        [first, second],
        {first: 0, second: 0},
    )

    assert result.returncode == 0
    assert marker.read_text(encoding="utf-8").splitlines() == [first, second]


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="requires bash on a non-Windows system",
)
def test_workflow_gate_loop_tolerates_exit_5_only_for_pytest(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    pytest_command = "python -m pytest -m unit -q --ignore=tests/gates/test_all_gate.py"
    non_pytest_command = "python -m ruff check pytest-config"
    pytest_result, _ = _run_workflow_gate_loop(
        tmp_path, repo_root, "pytest-exit-5", [pytest_command], {pytest_command: 5}
    )
    other_result, _ = _run_workflow_gate_loop(
        tmp_path,
        repo_root,
        "other-exit-5",
        [non_pytest_command],
        {non_pytest_command: 5},
    )

    assert pytest_result.returncode == 0
    assert other_result.returncode == 5


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="requires bash on a non-Windows system",
)
def test_workflow_gate_loop_stops_before_the_next_command_on_failure(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    failed = "python -m pytest -m unit -q --ignore=tests/gates/test_all_gate.py"
    not_reached = "python -m ruff check ."
    result, marker = _run_workflow_gate_loop(
        tmp_path,
        repo_root,
        "stop-on-failure",
        [failed, not_reached],
        {failed: 1, not_reached: 0},
    )

    assert result.returncode == 1
    assert marker.read_text(encoding="utf-8").splitlines() == [failed]
