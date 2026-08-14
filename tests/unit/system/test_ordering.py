"""Tests for factory.system.ordering: which bundle is most recently touched.

Touched means a commit changed a *member artifact*. Editing the bundle file
is curation, not development, and must not float a dormant feature to the
top of the navigator's sidebar.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.system.ordering import FixedRecency, bundle_recency, ordered_bundle_ids

pytestmark = pytest.mark.unit


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "requirements").mkdir()
    (tmp_path / "bundles").mkdir()
    return tmp_path


def _sr(repo: Path, sr_id: str) -> None:
    (repo / "requirements" / f"{sr_id}.md").write_text(
        f"---\nid: {sr_id}\ntitle: {sr_id}\nstatement: x\ndomain: behavioral\n---\n",
        encoding="utf-8",
    )


def _bundle(repo: Path, bundle_id: str, members: list[str]) -> None:
    (repo / "bundles" / f"{bundle_id}.json").write_text(
        json.dumps({"id": bundle_id, "label": bundle_id, "members": members}),
        encoding="utf-8",
    )


def test_recency_is_the_most_recent_commit_touching_any_member(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _sr(repo, "SR-002")
    _bundle(repo, "alpha", ["sr:SR-001", "sr:SR-002"])
    git = FixedRecency(
        {
            (repo / "requirements" / "SR-001.md").resolve(): "2026-08-01T00:00:00Z",
            (repo / "requirements" / "SR-002.md").resolve(): "2026-08-09T00:00:00Z",
        }
    )

    assert bundle_recency(repo, git) == {"alpha": "2026-08-09T00:00:00Z"}


def test_bundles_are_ordered_most_recent_first(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _sr(repo, "SR-002")
    _bundle(repo, "older", ["sr:SR-001"])
    _bundle(repo, "newer", ["sr:SR-002"])
    git = FixedRecency(
        {
            (repo / "requirements" / "SR-001.md").resolve(): "2026-08-01T00:00:00Z",
            (repo / "requirements" / "SR-002.md").resolve(): "2026-08-09T00:00:00Z",
        }
    )

    order, available = ordered_bundle_ids(repo, git)

    assert order == ["newer", "older"]
    assert available is True


def test_equal_recency_breaks_ties_by_id_ascending(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _sr(repo, "SR-002")
    _bundle(repo, "zulu", ["sr:SR-001"])
    _bundle(repo, "alpha", ["sr:SR-002"])
    same = "2026-08-05T00:00:00Z"
    git = FixedRecency(
        {
            (repo / "requirements" / "SR-001.md").resolve(): same,
            (repo / "requirements" / "SR-002.md").resolve(): same,
        }
    )

    order, _ = ordered_bundle_ids(repo, git)

    assert order == ["alpha", "zulu"]


def test_a_bundle_with_no_recency_sorts_after_every_dated_bundle(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _bundle(repo, "dated", ["sr:SR-001"])
    _bundle(repo, "empty", [])
    git = FixedRecency({(repo / "requirements" / "SR-001.md").resolve(): "2026-08-01T00:00:00Z"})

    order, _ = ordered_bundle_ids(repo, git)

    assert order == ["dated", "empty"]


def test_when_no_recency_is_available_order_falls_back_to_id_and_says_so(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _bundle(repo, "zulu", ["sr:SR-001"])
    _bundle(repo, "alpha", ["sr:SR-001"])
    git = FixedRecency({})

    order, available = ordered_bundle_ids(repo, git)

    assert order == ["alpha", "zulu"]
    # A silent fallback would make an arbitrary order look meaningful.
    assert available is False


def test_editing_the_bundle_file_does_not_affect_recency(tmp_path):
    repo = _repo(tmp_path)
    _sr(repo, "SR-001")
    _bundle(repo, "alpha", ["sr:SR-001"])
    git = FixedRecency(
        {
            (repo / "requirements" / "SR-001.md").resolve(): "2026-08-01T00:00:00Z",
            (repo / "bundles" / "alpha.json").resolve(): "2026-08-11T00:00:00Z",
        }
    )

    assert bundle_recency(repo, git) == {"alpha": "2026-08-01T00:00:00Z"}
