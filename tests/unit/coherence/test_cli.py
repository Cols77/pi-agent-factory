from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit

_PROJECT_ROOT = Path(__file__).parents[3]


def _run_coherence(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "coherence", *args],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_trace_check_dispatches_through_top_level_module(tmp_path: Path):
    result = _run_coherence("trace", "check", "--project-root", str(tmp_path))

    assert result.returncode == 0
    assert "traceability health:" in result.stdout


def test_register_status_dispatches_and_preserves_requirements_dir(tmp_path: Path):
    requirements_dir = tmp_path / "requirements"
    requirements_dir.mkdir()
    (requirements_dir / "SR-001.md").write_text(
        "---\n"
        "id: SR-001\n"
        "title: Dispatch works\n"
        "statement: The dispatcher shall forward arguments.\n"
        "domain: behavioral\n"
        "---\n",
        encoding="utf-8",
    )

    result = _run_coherence("register", "status", "--requirements-dir", str(requirements_dir))

    assert result.returncode == 0
    assert result.stdout == "SR-001  [proposed]  Dispatch works\n"


def test_doctor_context_dispatches_through_top_level_module(tmp_path: Path):
    result = _run_coherence(
        "doctor", "context", "--project-root", str(tmp_path), "--json"
    )

    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "specs": [],
        "requirements": [],
        "config": {"present": False, "harnesses": {}},
    }


@pytest.mark.parametrize("argv", [[], ["unknown", "--keep", "value"]])
def test_missing_or_unknown_group_module_entry_returns_two_and_lists_valid_groups(argv):
    result = _run_coherence(*argv)

    assert result.returncode == 2
    output = result.stdout + result.stderr
    assert "valid groups:" in output
    assert all(group in output for group in ("trace", "register", "doctor"))


@pytest.mark.parametrize("group", ["navigate", "presentation", "goals", "simulation"])
def test_coherence_exposes_increment_three_groups(group):
    from coherence import cli

    assert group in cli.GROUPS


@pytest.mark.parametrize("group", ["trace", "register", "doctor", "navigate", "presentation", "goals", "simulation"])
def test_dispatch_passes_child_argv_unchanged(group, monkeypatch):
    from coherence import cli

    received: list[str] = []

    def child_main(argv: list[str]) -> int:
        received.extend(argv)
        return 17

    monkeypatch.setitem(cli.GROUPS, group, child_main)
    child_argv = ["status", "--requirements-dir", "fixture", "--", "value"]

    assert cli.main([group, *child_argv]) == 17
    assert received == child_argv
