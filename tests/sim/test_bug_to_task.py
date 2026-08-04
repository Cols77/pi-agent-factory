"""Tests for converting bug snapshots to factory task files."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sim.bug_capture import BugSnapshot
from sim.bug_to_task import build_task_description, bug_to_task

pytestmark = pytest.mark.unit


class TestBuildTaskDescription:
    """build_task_description(snapshot_data) returns a markdown string."""

    def test_includes_name_and_timestamp(self):
        content = {
            "name": "bug-drone-not-landing",
            "captured_at": 45.2,
            "user_description": "Drone did not land on low battery",
            "requirements": [],
            "scenario": {"sea_polygon": {"vertices": [[0, 0], [10, 0]]}},
            "drone_pose": {"x": 5.0, "y": 10.0, "z": 3.0},
            "mission_state": {
                "mission_clock": 45.2,
                "waypoints_completed": 12,
                "waypoints_total": 20,
                "battery": 0.15,
            },
        }
        desc = build_task_description(content)

        # Name appears in heading
        assert "bug-drone-not-landing" in desc
        # Captured-at timestamp
        assert "45.2s" in desc or "45.2 s" in desc
        # User description present
        assert "Drone did not land" in desc
        # Mission clock appears
        assert "45.2" in desc
        # Waypoints present
        assert "12" in desc
        assert "20" in desc
        # Battery present
        assert "0.15" in desc or "15%" in desc or "0.15" in desc

    def test_handles_minimal_data(self):
        """Works with minimal dict (missing optional fields gracefully)."""
        content = {
            "name": "minimal-bug",
            "captured_at": 10.0,
            "user_description": "Something broke",
            "requirements": [],
            "scenario": {},
            "drone_pose": {},
            "mission_state": {},
        }
        desc = build_task_description(content)
        assert "minimal-bug" in desc
        assert "Something broke" in desc
        assert "10.0" in desc


class TestBugToTask:
    """bug_to_task(bug_path) writes a factory task file and returns its path."""

    def test_converts_snapshot_to_task_file(self, monkeypatch, tmp_path):
        """Writes tasks/T-*.md in cwd/tasks and returns path to it."""
        # Write a bug snapshot YAML into tmp_path
        snapshot = BugSnapshot(
            name="bug-test",
            captured_at=30.0,
            user_description="Test bug description",
            requirements=[],
            scenario={"sea_polygon": {"vertices": [[0, 0], [10, 0]]}},
            drone_pose={"x": 5.0, "y": 5.0, "z": 5.0},
            mission_state={
                "mission_clock": 30.0,
                "waypoints_completed": 5,
                "waypoints_total": 10,
                "battery": 0.6,
            },
        )
        bug_path = tmp_path / "bug-snapshot.yaml"
        snapshot.save(bug_path)

        # Chdir to tmp so tasks/ is created there
        monkeypatch.chdir(tmp_path)

        result = bug_to_task(bug_path)

        # Returns the absolute path to the task file
        result_path = Path(result)
        assert result_path.exists()
        assert result_path.parent.name == "tasks"
        assert result_path.name.startswith("T-")

        content = result_path.read_text()
        assert "Test bug description" in content
        assert "30.0" in content

    def test_raises_on_missing_bug_file(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            bug_to_task("/nonexistent/bug.yaml")

    def test_task_file_contains_acceptance_criteria(self, monkeypatch, tmp_path):
        """The task file includes checklist-style acceptance criteria."""
        snapshot = BugSnapshot(
            name="bug-no-reaction",
            captured_at=12.0,
            user_description="Drone did not react to shark",
            requirements=[],
            scenario={"sea_polygon": {"vertices": [[0, 0], [5, 0]]}},
            drone_pose={"x": 2.0, "y": 2.0, "z": 2.0},
            mission_state={"mission_clock": 12.0},
        )
        bug_path = tmp_path / "snap.yaml"
        snapshot.save(bug_path)

        monkeypatch.chdir(tmp_path)
        result = bug_to_task(bug_path)

        content = Path(result).read_text()
        assert "- [ ] Fix the issue" in content
        assert "## How to Reproduce" in content


class TestMainCLI:
    """python -m sim.bug_to_task CLI interface."""

    def test_no_args_returns_error(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["bug_to_task"])
        from sim.bug_to_task import main
        assert main() == 1

    def test_converts_and_prints_success(self, monkeypatch, tmp_path, capsys):
        """With a valid bug path, main() writes the task and returns 0."""
        from sim.bug_capture import BugSnapshot

        snapshot = BugSnapshot(
            name="bug-cli",
            captured_at=5.0,
            user_description="CLI bug",
            requirements=[],
            scenario={},
            drone_pose={},
            mission_state={},
        )
        bug_path = tmp_path / "cli-bug.yaml"
        snapshot.save(bug_path)

        monkeypatch.setattr(sys, "argv", ["bug_to_task", str(bug_path)])
        monkeypatch.chdir(tmp_path)

        from sim.bug_to_task import main
        assert main() == 0
        assert (tmp_path / "tasks" / "T-bug-cli.md").exists()
        out = capsys.readouterr().out
        assert "Task created" in out