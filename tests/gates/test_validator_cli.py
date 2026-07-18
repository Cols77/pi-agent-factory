# tests/gates/test_validator_cli.py
import json
import subprocess
import sys
import pytest

pytestmark = pytest.mark.unit


def _run(script, arg, cwd=None):
    return subprocess.run(
        [sys.executable, f"scripts/gates/{script}", str(arg)],
        cwd=cwd, capture_output=True, text=True,
    ).returncode


def test_valid_session_exits_zero(tmp_path):
    rec = {"session_id": "s1", "started_at": "2026-07-16T14:30:00Z",
           "model_backend": "anthropic:claude-opus-4-8",
           "tasks": [{"task_id": "T-001", "outcome": "escalated",
                      "nodes": [{"node": "dev", "result": "pass"}]}]}
    f = tmp_path / "s.json"
    f.write_text(json.dumps(rec), encoding="utf-8")
    assert _run("validate_session.py", f) == 0


def test_invalid_session_exits_one(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text(json.dumps({"session_id": "s1"}), encoding="utf-8")
    assert _run("validate_session.py", f) == 1


def test_valid_kb_entry_exits_zero():
    assert _run("validate_kb.py", "kb/kb-0001-pybullet-arming.md") == 0
