import json

import pytest

from factory.system import health

pytestmark = pytest.mark.unit


def _write_sr(root, req_id, *, binding=True, statement="s"):
    """Write a requirements/SR file and return its id."""
    req_dir = root / "requirements"
    req_dir.mkdir(parents=True, exist_ok=True)
    binding_yaml = (
        "binding:\n  experiment: e\n  metric: m\n  assert: a\n  harness: h\n"
        if binding
        else ""
    )
    (req_dir / f"{req_id}.md").write_text(
        f"---\nid: {req_id}\ntitle: T\nstatement: {statement}\ndomain: d\n"
        f"{binding_yaml}---\nbody\n",
        encoding="utf-8",
    )
    return req_id


def _write_task_satisfying(root, task_id, sr_id):
    """Write a task that satisfies `sr_id`, so the SR reads as covered."""
    tasks_dir = root / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / f"{task_id}.md").write_text(
        f"---\nid: {task_id}\ntitle: T\nstatus: done\nsatisfies: ['{sr_id}']\n"
        f"---\nbody\n",
        encoding="utf-8",
    )
    return task_id


def _write_bundle(root, bundle_id, member_refs):
    bundles_dir = root / "bundles"
    bundles_dir.mkdir(parents=True, exist_ok=True)
    (bundles_dir / f"{bundle_id}.json").write_text(
        json.dumps({"id": bundle_id, "label": bundle_id, "members": member_refs}),
        encoding="utf-8",
    )


def test_readiness_weak_when_sr_unbound(tmp_path):
    sr = _write_sr(tmp_path, "SR-001", binding=False)
    _write_bundle(tmp_path, "b1", ["sr:" + sr])

    rows = health.bundle_readiness(tmp_path)
    assert rows["b1"].readiness == "weak"
    assert rows["b1"].bound == 0
    assert rows["b1"].sr_total == 1


def test_readiness_strong_when_all_current_covered_validated(tmp_path, monkeypatch):
    _write_sr(tmp_path, "SR-002", binding=True)
    _write_sr(tmp_path, "SR-003", binding=True)
    _write_bundle(tmp_path, "b2", ["sr:SR-002", "sr:SR-003"])
    _write_task_satisfying(tmp_path, "T-001", "SR-002")
    _write_task_satisfying(tmp_path, "T-002", "SR-003")
    monkeypatch.setattr(health, "_validation_passing", lambda root, sid: True)
    rows = health.bundle_readiness(tmp_path)
    assert rows["b2"].readiness == "strong"


def test_readiness_medium_when_validation_missing(tmp_path, monkeypatch):
    _write_sr(tmp_path, "SR-004", binding=True)
    _write_task_satisfying(tmp_path, "T-003", "SR-004")
    _write_bundle(tmp_path, "b3", ["sr:SR-004"])
    monkeypatch.setattr(health, "_validation_passing", lambda root, sid: False)
    rows = health.bundle_readiness(tmp_path)
    assert rows["b3"].readiness == "medium"
