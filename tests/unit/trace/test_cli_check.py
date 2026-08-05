from __future__ import annotations

from pathlib import Path

import pytest
from factory.trace.cli import cmd_check, main
from factory.trace.write import set_deferred, set_exempt

pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _task(tmp_path: Path, task_id: str) -> None:
    _write(
        tmp_path / "tasks" / f"{task_id}.md",
        f"---\nid: {task_id}\ntitle: t\nstatus: todo\ndod: []\n"
        "source_plan: docs/superpowers/plans/p1.md\n---\n",
    )


def _plan(tmp_path: Path) -> None:
    _write(
        tmp_path / "docs" / "superpowers" / "plans" / "p1.md",
        "# P\n\ndocs/superpowers/specs/s1.md\n",
    )
    _write(tmp_path / "docs" / "superpowers" / "specs" / "s1.md", "# S\n")


def test_pending_gap_fails_the_gate(tmp_path):
    _task(tmp_path, "T-001")
    _plan(tmp_path)

    text, code = cmd_check(tmp_path)

    assert code == 1
    assert "T-001" in text
    assert "pending" in text


def test_exempting_every_gap_passes_the_gate(tmp_path):
    _task(tmp_path, "T-001")
    _plan(tmp_path)
    set_exempt(tmp_path, "T-001", "tooling")

    text, code = cmd_check(tmp_path)

    assert code == 0
    assert "0 pending" in text


def test_deferring_passes_the_gate_but_is_reported_as_a_warning(tmp_path):
    _task(tmp_path, "T-001")
    _plan(tmp_path)
    set_deferred(tmp_path, "T-001", "needs an SR split")

    text, code = cmd_check(tmp_path)

    assert code == 0
    assert "deferred" in text
    assert "needs an SR split" in text


def test_empty_repo_passes(tmp_path):
    assert cmd_check(tmp_path)[1] == 0


def test_main_check_propagates_the_exit_code(tmp_path, capsys):
    _task(tmp_path, "T-001")
    _plan(tmp_path)

    assert main(["check", "--project-root", str(tmp_path)]) == 1
    assert "pending" in capsys.readouterr().out
