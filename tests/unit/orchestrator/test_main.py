import json
import sys
from pathlib import Path

import pytest

from factory.orchestrator.__main__ import main

pytestmark = pytest.mark.unit


def _write_gate_config(repo_root: Path) -> None:
    # main() now builds its gate runner from config (require_gates), so any
    # repo it runs against needs a declared gate or construction itself raises
    # before run_next is even reached.
    factory_dir = repo_root / ".factory"
    factory_dir.mkdir(parents=True, exist_ok=True)
    (factory_dir / "factory.yaml").write_text(
        'gates:\n  unit:\n    - { cmd: "{python} -c \\"pass\\"" }\n',
        encoding="utf-8",
    )


def test_main_error_status_on_run_next_exception(tmp_path, monkeypatch):
    """Test that when run_next() raises an exception, the error status is written before re-raising."""
    # Set up the repo structure with sessions directory
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (tmp_path / "tasks").mkdir()
    _write_gate_config(tmp_path)

    # Monkeypatch sys.argv to simulate CLI invocation
    monkeypatch.setattr(sys, "argv", ["factory.orchestrator", "run", "--repo", str(tmp_path)])

    # Monkeypatch run_next to raise RuntimeError immediately
    def mock_run_next(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("factory.orchestrator.__main__.run_next", mock_run_next)

    # Call main() and expect the exception to propagate
    with pytest.raises(RuntimeError, match="boom"):
        main()

    # Assert the status file was written with error state
    status_path = sessions_dir / ".factory-status.json"
    assert status_path.exists(), f"Status file should exist at {status_path}"

    status_data = json.loads(status_path.read_text(encoding="utf-8"))
    # New format uses current_node/current_state with pipeline
    state = status_data.get("current_state", status_data.get("node_state"))
    assert state == "error", f"Expected node_state='error', got {state}"
    # Error snippet is in the pipeline entry
    pipeline = status_data.get("pipeline", [])
    error_entry = next((p for p in pipeline if p["node"] == "orchestrator"), None)
    assert error_entry is not None, f"Expected orchestrator in pipeline, got {pipeline}"
    assert "boom" in error_entry["snippet"], f"Expected 'boom' in snippet, got {error_entry['snippet']}"

    # Assert the lock file was cleaned up (finally block ran)
    lock_path = sessions_dir / ".factory-run.lock"
    assert not lock_path.exists(), f"Lock file should be removed after exception, but exists at {lock_path}"


def test_main_list_prints_task_board_and_touches_no_run_state(tmp_path, monkeypatch, capsys):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "T-001-a.md").write_text(
        "---\nid: T-001\ntitle: Example task\nstatus: todo\ndod:\n  - x\n---\nbody\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["factory.orchestrator", "list", "--repo", str(tmp_path)])
    main()

    out = capsys.readouterr().out
    assert "TODO (1)" in out
    assert "T-001  Example task" in out
    assert not (tmp_path / "sessions" / ".factory-run.lock").exists()
    assert not (tmp_path / "sessions" / ".factory-status.json").exists()


def test_main_run_passes_task_id_through(tmp_path, monkeypatch):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (tmp_path / "tasks").mkdir()
    _write_gate_config(tmp_path)

    monkeypatch.setattr(
        sys, "argv",
        ["factory.orchestrator", "run", "--repo", str(tmp_path), "--task", "T-042"],
    )

    captured = {}

    def fake_run_next(*args, **kwargs):
        captured["task_id"] = kwargs.get("task_id")
        return None

    monkeypatch.setattr("factory.orchestrator.__main__.run_next", fake_run_next)
    main()
    assert captured["task_id"] == "T-042"


def test_main_list_json_outputs_structured_tasks(tmp_path, monkeypatch, capsys):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "T-001-a.md").write_text(
        "---\nid: T-001\ntitle: Example task\nstatus: todo\ndod:\n  - x\n---\nbody\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["factory.orchestrator", "list", "--repo", str(tmp_path), "--json"])
    main()

    out = json.loads(capsys.readouterr().out)
    assert out == [{
        "id": "T-001", "title": "Example task", "status": "todo",
        "already_done": False, "last_run": None,
    }]


def test_main_list_json_includes_last_run(tmp_path, monkeypatch, capsys):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "T-1-a.md").write_text(
        "---\nid: T-1\ntitle: t\nstatus: todo\ndod:\n  - c\n---\nbody\n",
        encoding="utf-8",
    )
    runs_dir = tmp_path / "sessions" / ".factory-runs"
    runs_dir.mkdir(parents=True)
    (runs_dir / "T-1.json").write_text(json.dumps({
        "task_id": "T-1", "current_node": "dev", "current_state": "fail", "updated_at": "t",
        "pipeline": [{"node": "dev", "node_state": "fail", "handoff": "red", "outcome": "escalated"}],
    }), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["factory.orchestrator", "list", "--repo", str(tmp_path), "--json"])
    main()

    out = json.loads(capsys.readouterr().out)
    t1 = next(t for t in out if t["id"] == "T-1")
    assert t1["last_run"]["state"] == "fail"
    assert t1["last_run"]["handoff"] == "red"
