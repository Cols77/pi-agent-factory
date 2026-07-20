import json
import sys

import pytest

from factory.orchestrator.__main__ import main

pytestmark = pytest.mark.unit


def test_main_error_status_on_run_next_exception(tmp_path, monkeypatch):
    """Test that when run_next() raises an exception, the error status is written before re-raising."""
    # Set up the repo structure with sessions directory
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (tmp_path / "tasks").mkdir()

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
    assert status_data["node_state"] == "error", f"Expected node_state='error', got {status_data['node_state']}"
    assert "boom" in status_data["snippet"], f"Expected 'boom' in snippet, got {status_data['snippet']}"

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
    assert out == [{"id": "T-001", "title": "Example task", "status": "todo"}]
