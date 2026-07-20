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
