import json

import pytest
from factory.system.models import SystemScopeRef
from factory.system.reverse import query_reverse
from factory.system.queries import ScopeNotFoundError

from ._fixtures import _write_task_fixture, _write_manifest_fixture, _write_exported_guide_fixture  # noqa: F401

pytestmark = pytest.mark.unit


def test_walks_file_to_run_to_task_to_requirement(tmp_path, write_task, write_manifest):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    write_task(tmp_path, "T-059", status="done", satisfies=["SR-146"])
    write_manifest(tmp_path, run_id="r1", task_id="T-059", outcome="completed",
                   changed_files=["src/a.py"])

    result = query_reverse(tmp_path, SystemScopeRef(kind="file", ref="file:src/a.py"))

    assert len(result["paths"]) == 1
    path = result["paths"][0]
    assert path["run"]["run_id"] == "r1"
    assert path["task"]["id"] == "T-059"
    assert path["requirements"] == ["sr:SR-146"]
    assert path["stops_at"] is None


def test_a_file_no_run_touched_is_missing_not_empty(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "orphan.py").write_text("x = 1\n", encoding="utf-8")

    result = query_reverse(tmp_path, SystemScopeRef(kind="file", ref="file:src/orphan.py"))

    assert result["paths"] == []
    assert result["degraded"] is True
    assert any("no recorded run" in r for r in result["degraded_reasons"])


def test_the_chain_stops_where_a_hop_does_not_resolve(tmp_path, write_task, write_manifest):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    write_task(tmp_path, "T-059", status="done", satisfies=[])
    write_manifest(tmp_path, run_id="r1", task_id="T-059", outcome="completed",
                   changed_files=["src/a.py"])

    path = query_reverse(tmp_path, SystemScopeRef(kind="file", ref="file:src/a.py"))["paths"][0]

    assert path["requirements"] == []
    assert path["stops_at"] == "satisfies"


def test_one_file_touched_by_several_runs_yields_several_paths(tmp_path, write_task, write_manifest):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    write_task(tmp_path, "T-059", status="done", satisfies=[])
    write_manifest(tmp_path, run_id="r1", task_id="T-059", outcome="escalated",
                   changed_files=["src/a.py"])
    write_manifest(tmp_path, run_id="r2", task_id="T-059", outcome="completed",
                   changed_files=["src/a.py"])

    paths = query_reverse(tmp_path, SystemScopeRef(kind="file", ref="file:src/a.py"))["paths"]

    assert [p["run"]["run_id"] for p in paths] == ["r1", "r2"], "rework must not be collapsed"


def test_a_spec20_bundle_without_implementation_never_crashes_the_walk(tmp_path, write_task):
    # load_run_manifest returns §20 simulation bundles (a `run` key, no
    # `task_id`) *unvalidated* -- so one without an `implementation` block is
    # legal input. It records no changed files, so it must simply never match
    # the walked file: `paths` empty, the designed degraded reason, no
    # KeyError. Before this guard the whole reverse query exited 1 and the
    # browser review page surfaced the raw traceback behind `why this file:`.
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    write_task(tmp_path, "T-059", status="done", satisfies=["SR-146"])
    bundle_dir = tmp_path / "evidence" / "runs" / "RUN-SIM-7"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "manifest.json").write_text(
        json.dumps({"run": "RUN-SIM-7", "goals": [], "result": None}), encoding="utf-8"
    )

    result = query_reverse(tmp_path, SystemScopeRef(kind="file", ref="file:src/a.py"))

    assert result["paths"] == []
    assert result["degraded"] is True
    assert any("no recorded run" in r for r in result["degraded_reasons"])


def test_a_path_outside_the_repository_is_refused(tmp_path):
    with pytest.raises(ScopeNotFoundError):
        query_reverse(tmp_path, SystemScopeRef(kind="file", ref="file:../../etc/passwd"))


def test_an_exported_guide_is_not_a_navigable_file(tmp_path, write_exported_guide):
    exported = write_exported_guide(tmp_path / "guide.json")
    with pytest.raises(ScopeNotFoundError):
        query_reverse(tmp_path, SystemScopeRef(kind="file", ref=f"file:{exported.name}"))
