"""Tests for factory.system.coverage: which artifacts belong to no bundle.

Membership is many-to-many, so coverage asks only whether an artifact
belongs to *at least one* bundle. Counts are over the artifact set, never
summed across bundles -- summing would double-count anything shared between
two features and report more requirements than exist.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.system import coverage
from factory.system.coverage import build_artifact_lookup, bundle_coverage, member_target

pytestmark = pytest.mark.unit


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "requirements").mkdir()
    (tmp_path / "tasks").mkdir()
    (tmp_path / "docs" / "superpowers" / "specs").mkdir(parents=True)
    (tmp_path / "docs" / "superpowers" / "plans").mkdir(parents=True)
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    (tmp_path / "bundles").mkdir()
    return tmp_path


def _sr(repo: Path, sr_id: str) -> None:
    (repo / "requirements" / f"{sr_id}.md").write_text(
        f"---\nid: {sr_id}\ntitle: {sr_id}\nstatement: x\ndomain: behavioral\n---\n",
        encoding="utf-8",
    )


def _task(repo: Path, task_id: str, slug: str) -> None:
    (repo / "tasks" / f"{task_id}-{slug}.md").write_text(
        f"---\nid: {task_id}\ntitle: {slug}\nstatus: todo\n---\n", encoding="utf-8"
    )


def _spec(repo: Path, name: str) -> str:
    (repo / "docs" / "superpowers" / "specs" / name).write_text("# spec\n", encoding="utf-8")
    return f"docs/superpowers/specs/{name}"


def _plan(repo: Path, name: str) -> str:
    (repo / "docs" / "superpowers" / "plans" / name).write_text("# plan\n", encoding="utf-8")
    return f"docs/superpowers/plans/{name}"


def _adr(repo: Path, adr_id: str, filename: str) -> None:
    (repo / "docs" / "adr" / filename).write_text(
        f"---\nid: {adr_id}\ntitle: {adr_id}\nstatus: accepted\n---\n\n## Decision\nx.\n",
        encoding="utf-8",
    )


def _bundle(repo: Path, bundle_id: str, members: list[str]) -> None:
    (repo / "bundles" / f"{bundle_id}.json").write_text(
        json.dumps({"id": bundle_id, "label": bundle_id, "members": members}),
        encoding="utf-8",
    )


def _by_kind(coverage, kind):
    return next(k for k in coverage.kinds if k.kind == kind)


def test_every_kind_is_counted_including_adr(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _task(repo, "T-001", "thing")
    spec_ref = _spec(repo, "a-spec.md")
    plan_ref = _plan(repo, "a-plan.md")
    _adr(repo, "ADR-0001", "0001-decision.md")
    _bundle(
        repo,
        "everything",
        ["sr:SR-001", "task:T-001", f"spec:{spec_ref}", f"plan:{plan_ref}", "adr:ADR-0001"],
    )

    coverage = bundle_coverage(repo)

    assert coverage.total == 5
    assert coverage.bundled == 5
    assert coverage.unbundled == []
    for kind in ("sr", "task", "spec", "plan", "adr"):
        assert _by_kind(coverage, kind).bundled == 1


def test_an_artifact_in_two_bundles_is_counted_once(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _bundle(repo, "first", ["sr:SR-001"])
    _bundle(repo, "second", ["sr:SR-001"])

    coverage = bundle_coverage(repo)

    # Summing per-bundle counts would report 2 requirements where 1 exists.
    assert coverage.total == 1
    assert coverage.bundled == 1
    assert _by_kind(coverage, "sr").bundled == 1


def test_coverage_loads_trace_nodes_once_for_multiple_sr_and_task_members(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _sr(repo, "SR-002")
    _task(repo, "T-001", "first")
    _task(repo, "T-002", "second")
    _bundle(repo, "feature", ["sr:SR-001", "sr:SR-002", "task:T-001", "task:T-002"])

    real_load_nodes = coverage.trace_model.load_nodes
    calls = 0

    def counted_load_nodes(root):
        nonlocal calls
        calls += 1
        return real_load_nodes(root)

    monkeypatch.setattr(coverage.trace_model, "load_nodes", counted_load_nodes)

    result = bundle_coverage(repo)

    assert result.bundled == 4
    assert calls == 1


def test_coverage_preserves_duplicate_sr_and_task_ids_as_distinct_artifacts(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    (repo / "requirements" / "SR-shadow.md").write_text(
        "---\nid: SR-001\ntitle: shadow\nstatement: x\ndomain: behavioral\n---\n",
        encoding="utf-8",
    )
    _task(repo, "T-001", "first")
    (repo / "tasks" / "T-shadow.md").write_text(
        "---\nid: T-001\ntitle: shadow\nstatus: todo\n---\n",
        encoding="utf-8",
    )
    _bundle(repo, "feature", ["sr:SR-001", "task:T-001"])

    result = bundle_coverage(repo)

    assert result.total == 4
    assert result.bundled == 2
    assert _by_kind(result, "sr").unbundled == ["sr:SR-001"]
    assert _by_kind(result, "task").unbundled == ["task:T-001"]
    assert result.unbundled == ["sr:SR-001", "task:T-001"]


def test_member_target_lookup_matches_legacy_first_path_for_duplicate_ids(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    (repo / "requirements" / "SR-shadow.md").write_text(
        "---\nid: SR-001\ntitle: shadow\nstatement: x\ndomain: behavioral\n---\n",
        encoding="utf-8",
    )
    _task(repo, "T-001", "first")
    (repo / "tasks" / "T-shadow.md").write_text(
        "---\nid: T-001\ntitle: shadow\nstatus: todo\n---\n",
        encoding="utf-8",
    )

    lookup = build_artifact_lookup(repo)
    expected = {
        "sr:SR-001": (repo / "requirements" / "SR-001.md").resolve(),
        "task:T-001": (repo / "tasks" / "T-001-first.md").resolve(),
    }

    for ref, first_path in expected.items():
        legacy_target = member_target(repo, ref)

        assert legacy_target == first_path
        assert member_target(repo, ref, lookup=lookup) == legacy_target


def test_unbundled_artifacts_are_named_not_just_counted(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _sr(repo, "SR-002")
    _bundle(repo, "partial", ["sr:SR-001"])

    coverage = bundle_coverage(repo)

    assert coverage.bundled == 1
    assert _by_kind(coverage, "sr").unbundled == ["sr:SR-002"]
    assert coverage.unbundled == ["sr:SR-002"]


def test_an_empty_bundle_contributes_nothing_and_is_not_an_error(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _bundle(repo, "forward-declared", [])

    coverage = bundle_coverage(repo)

    # Coverage counts artifacts, not bundles, so an empty bundle cannot
    # inflate it. Forward-declaring a feature stays legal.
    assert coverage.total == 1
    assert coverage.bundled == 0


def test_a_repo_with_no_bundles_reports_everything_unbundled(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _task(repo, "T-001", "thing")

    coverage = bundle_coverage(repo)

    assert coverage.bundled == 0
    assert coverage.total == 2
    assert coverage.unbundled == ["sr:SR-001", "task:T-001"]


def test_a_member_naming_a_nonexistent_artifact_does_not_mark_anything_bundled(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _bundle(repo, "typo", ["sr:SR-999"])

    coverage = bundle_coverage(repo)

    assert coverage.bundled == 0
    assert _by_kind(coverage, "sr").unbundled == ["sr:SR-001"]


def test_unbundled_refs_are_in_deterministic_order(tmp_path):
    repo = _repo(tmp_path)
    for sr_id in ("SR-003", "SR-001", "SR-002"):
        _sr(repo, sr_id)

    coverage = bundle_coverage(repo)

    assert _by_kind(coverage, "sr").unbundled == ["sr:SR-001", "sr:SR-002", "sr:SR-003"]
