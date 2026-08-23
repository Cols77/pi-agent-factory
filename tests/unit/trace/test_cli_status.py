from __future__ import annotations

import json
from pathlib import Path

import pytest
from factory.trace.cli import cmd_graph, cmd_status, main

pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _repo(tmp_path: Path) -> Path:
    _write(
        tmp_path / "tasks" / "T-001.md",
        "---\nid: T-001\ntitle: Thing\nstatus: done\ndod: []\n"
        "source_plan: docs/superpowers/plans/p1.md\n---\n",
    )
    _write(tmp_path / "docs" / "superpowers" / "plans" / "p1.md", "# Plan One\n")
    return tmp_path


def test_status_reports_percent_and_gap_count(tmp_path):
    text = cmd_status(_repo(tmp_path))

    assert "task->plan" in text
    assert "%" in text
    assert "task declares no justification" in text


def test_graph_dict_is_json_serialisable_and_has_the_expected_keys(tmp_path):
    data = cmd_graph(_repo(tmp_path))

    json.dumps(data)  # must not raise
    assert set(data) == {"nodes", "edges", "gaps", "validation", "health"}
    assert {"id": "T-001", "kind": "task"}.items() <= data["nodes"][0].items()


def test_main_graph_json_prints_parsable_json(tmp_path, capsys):
    exit_code = main(["graph", "--project-root", str(_repo(tmp_path)), "--json"])

    assert exit_code == 0
    assert "nodes" in json.loads(capsys.readouterr().out)


def test_main_status_on_empty_repo_exits_zero(tmp_path, capsys):
    assert main(["status", "--project-root", str(tmp_path)]) == 0
    assert "100%" in capsys.readouterr().out
