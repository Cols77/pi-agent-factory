"""Integration test: `story` and `reverse` agree about the same run, driven
through the real `python -m factory.system` CLI end to end (increment B
"V-cycle": Task 3 built the forward story -- task -> runs -> requirements;
Task 4 built the reverse walk -- file -> run -> task -> requirements. This is
the proof they describe the same recorded evidence when the same repo is
walked forward and backward.)

Builds its own repo scaffold directly, matching
`test_navigator_projection.py`'s convention (`tests/unit`/`tests/integration`
are separate top-level test packages with no shared `__init__.py` chain, so a
cross-directory relative import to `tests/unit/system/_fixtures.py` would be
fragile) -- and writes the run evidence manifest through the real
`factory.evidence.manifests.write_run_manifest` writer, the same real loader
both `query_story` and `query_reverse` read through, so this test cannot
silently drift to a manifest shape no producer actually writes.

Drives the same CLI entry point `test_navigator_projection.py`'s own tests
already exercise (`python -m factory.system` via `sys.executable`, already
the `uv`-managed venv interpreter under `uv run pytest` -- no need to shell
out to `uv run` a second time), rather than calling `query_story`/
`query_reverse` directly: the point of this test is that the two subcommands
report the same `run_id` for the same evidence when driven end to end through
the real CLI, not merely that the underlying Python functions agree
in-process.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from factory.evidence.manifests import write_run_manifest

pytestmark = pytest.mark.integration

_TASK_T059 = """---
id: T-059
title: "Implement the demo feature"
status: done
dod:
  - done
satisfies: []
---
body
"""


def _write_manifest(root: Path, *, run_id: str, task_id: str, changed_files: list[str]) -> Path:
    """Write a schema-valid run evidence manifest through the real writer --
    the same shape `test_navigator_projection.py`'s own `_write_manifest`
    helper uses, and the one `factory.evidence.finalize` actually produces."""
    manifest = {
        "schema_version": 2,
        "run_id": run_id,
        "task_id": task_id,
        "started_at": "2026-08-08T08:00:00Z",
        "ended_at": "2026-08-08T09:00:00Z",
        "start_commit": "a" * 40,
        "result_commit": "b" * 40,
        "outcome": "completed",
        "inputs": {
            "task": {"path": f"tasks/{task_id}-slug.md", "sha256": "c" * 64},
            "requirements": [],
            "factory_config_sha256": "d" * 64,
        },
        "dependencies": [],
        "implementation": {
            "changed_files": changed_files,
            "patch": {"sha256": "e" * 64, "size": 0, "media_type": "text/x-diff"},
        },
        "validation": [],
        "reviews": [],
        "decisions": [],
        "publication": {"state": "local", "errors": []},
    }
    return write_run_manifest(root / "evidence", manifest)


def run_module_cli(repo_root: Path, args: list[str]) -> dict:
    """Invoke `python -m factory.system` as a real subprocess -- mirroring
    `test_navigator_projection.py`'s own inline CLI invocations in this same
    directory (`sys.executable`, already the correct `uv`-managed venv
    interpreter when this test itself runs under `uv run pytest`, so
    shelling out to `uv run` a second time is unnecessary). `--repo-root` is
    appended here so callers only need to name the subcommand and its own
    flags, exactly as the brief's example calls it."""
    result = subprocess.run(
        [sys.executable, "-m", "factory.system", *args, "--repo-root", str(repo_root)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_story_and_reverse_agree_about_the_same_run(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "T-059-slug.md").write_text(_TASK_T059, encoding="utf-8")

    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "a.py").write_text("# a\n", encoding="utf-8")

    _write_manifest(tmp_path, run_id="run-059", task_id="T-059", changed_files=["src/a.py"])

    story = run_module_cli(tmp_path, ["story", "--scope", "task:T-059", "--json"])
    reverse = run_module_cli(tmp_path, ["reverse", "--scope", "file:src/a.py", "--json"])

    assert story["runs"][0]["run_id"] == reverse["paths"][0]["run"]["run_id"]
    assert story["runs"][0]["run_id"] == "run-059"
