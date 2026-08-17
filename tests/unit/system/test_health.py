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
    monkeypatch.setattr(health, "_validation_passing", lambda root, sid, validation=None: True)
    rows = health.bundle_readiness(tmp_path)
    assert rows["b2"].readiness == "strong"


def test_readiness_medium_when_validation_missing(tmp_path, monkeypatch):
    _write_sr(tmp_path, "SR-004", binding=True)
    _write_task_satisfying(tmp_path, "T-003", "SR-004")
    _write_bundle(tmp_path, "b3", ["sr:SR-004"])
    monkeypatch.setattr(health, "_validation_passing", lambda root, sid, validation=None: False)
    rows = health.bundle_readiness(tmp_path)
    assert rows["b3"].readiness == "medium"


def test_query_health_shapes_the_landing_payload(tmp_path):
    _write_sr(tmp_path, "SR-001", binding=True)
    _write_bundle(tmp_path, "b1", ["sr:SR-001"])
    payload = health.query_health(tmp_path)
    assert payload["sr_listed"] is False
    assert {
        "health", "coverage", "bundles", "unbundled",
        "ordering_available", "degraded",
    } <= payload.keys()
    by_id = {b["id"]: b for b in payload["bundles"]}
    assert by_id["b1"]["readiness"] in ("strong", "medium", "weak")
    assert "readiness_counts" in by_id["b1"]


def test_query_health_orders_by_recency(tmp_path):
    from factory.system.ordering import FixedRecency

    _write_sr(tmp_path, "SR-001", binding=True)
    _write_sr(tmp_path, "SR-002", binding=True)
    _write_bundle(tmp_path, "older", ["sr:SR-001"])
    _write_bundle(tmp_path, "newer", ["sr:SR-002"])
    recency = FixedRecency({
        (tmp_path / "requirements" / "SR-001.md"): "2026-01-01T00:00:00Z",
        (tmp_path / "requirements" / "SR-002.md"): "2026-02-01T00:00:00Z",
    })
    payload = health.query_health(tmp_path, recency_source=recency)
    ids = [b["id"] for b in payload["bundles"]]
    assert ids == ["newer", "older"]


def test_query_health_shares_one_lookup_between_coverage_and_ordering(tmp_path, monkeypatch):
    from factory.system.ordering import FixedRecency

    _write_sr(tmp_path, "SR-001", binding=True)
    _write_bundle(tmp_path, "b1", ["sr:SR-001"])
    seen = []
    real_bundle_coverage = health.bundle_coverage
    real_ordered_bundle_ids = health.ordered_bundle_ids

    def capture_bundle_coverage(root, *, lookup):
        seen.append(lookup)
        return real_bundle_coverage(root, lookup=lookup)

    def capture_ordered_bundle_ids(root, git, *, lookup):
        seen.append(lookup)
        return real_ordered_bundle_ids(root, git, lookup=lookup)

    monkeypatch.setattr(health, "bundle_coverage", capture_bundle_coverage)
    monkeypatch.setattr(health, "ordered_bundle_ids", capture_ordered_bundle_ids)

    health.query_health(tmp_path, recency_source=FixedRecency({}))

    assert len(seen) == 2
    assert seen[0] is seen[1]


def test_shape_sentence_states_what_the_project_is_made_of(tmp_path):
    # seed 2 SRs, 1 bundle containing them, 1 task satisfying one
    _write_sr(tmp_path, "SR-001", binding=True)
    _write_sr(tmp_path, "SR-002", binding=True)
    _write_bundle(tmp_path, "b1", ["sr:SR-001", "sr:SR-002"])
    _write_task_satisfying(tmp_path, "T-001", "SR-001")
    payload = health.query_health(tmp_path)
    s = payload["shape"]["sentence"]
    # Asserted with the punctuation that ends each count's word, not a bare
    # "N feature" substring -- "1 feature" is a substring of the buggy
    # "1 features", so a boundary-free assertion would pass against the bug.
    assert "2 requirements," in s
    assert "grouped into 1 feature." in s
    assert "1 task implements" in s
    assert payload["shape"]["parts"] == {
        "requirements": 2, "features": 1, "tasks": 1, "validated": 0,
    }


def test_shape_sentence_is_honest_with_no_bundles(tmp_path):
    payload = health.query_health(tmp_path)
    assert "no features yet" in payload["shape"]["sentence"]


def test_shape_sentence_pluralizes_each_count_in_the_singular():
    s = health._shape_sentence(requirements=1, features=1, tasks=1, validated=1)
    assert "1 requirement," in s
    assert "1 requirements" not in s
    assert "grouped into 1 feature." in s
    assert "1 features" not in s
    assert "1 task implements" in s
    assert "1 tasks" not in s
    assert "1 of that requirement has" in s


def test_shape_sentence_pluralizes_each_count_in_the_plural():
    s = health._shape_sentence(requirements=2, features=2, tasks=2, validated=2)
    assert "2 requirements," in s
    assert "grouped into 2 features." in s
    assert "2 tasks implement" in s
    assert "2 of those requirements have" in s


def test_shape_sentence_names_no_features_yet_when_features_is_zero():
    s = health._shape_sentence(requirements=0, features=0, tasks=0, validated=0)
    assert "grouped into no features yet" in s
    assert "0 requirements," in s


def test_query_health_loads_trace_nodes_once_for_a_multi_member_bundle(tmp_path, monkeypatch):
    from factory.system.ordering import FixedRecency

    _write_sr(tmp_path, "SR-001", binding=True)
    _write_sr(tmp_path, "SR-002", binding=True)
    _write_bundle(tmp_path, "b1", ["sr:SR-001", "sr:SR-002"])
    real_load_nodes = health.trace_model.load_nodes
    calls = 0

    def counted_load_nodes(root):
        nonlocal calls
        calls += 1
        return real_load_nodes(root)

    monkeypatch.setattr(health.trace_model, "load_nodes", counted_load_nodes)

    payload = health.query_health(tmp_path, recency_source=FixedRecency({}))

    assert [bundle["id"] for bundle in payload["bundles"]] == ["b1"]
    assert calls == 1
