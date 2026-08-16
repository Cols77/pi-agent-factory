"""Context delta computation (Inc 7 Task 2).

From a seeded git history + goals/history + sim runs, `compute_delta` must
produce the spec §31 / §9.4 delta deterministically: PRs merged, requirement
changes, added ADRs, new scenarios/experiments, goal transitions, metric
deltas and new open items -- never an LLM summary of the past.
"""

from __future__ import annotations

import pytest

from factory.delta.compute import ContextDelta, compute_delta
from _seed_repo import git, seed_repo

pytestmark = pytest.mark.unit


@pytest.fixture
def seeded_repo(tmp_path):
    """A scratch git repo with commits C1..C4b; returns (repo, since_commit)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    return seed_repo(repo)


def test_delta_reports_prs_requirements_adrs(seeded_repo):
    repo, c1 = seeded_repo
    delta = compute_delta(repo, "FEAT-NAV-017", c1)
    assert isinstance(delta, ContextDelta)
    assert delta.feature == "FEAT-NAV-017"
    assert delta.since_commit == c1
    assert len(delta.prs_merged) == 1
    assert "Merge pull request #17" in delta.prs_merged[0]
    assert delta.requirements_changed == ["SR-017"]
    assert delta.adrs_added == ["ADR-0002"]


def test_delta_reports_goals_metrics_open_items(seeded_repo):
    repo, c1 = seeded_repo
    delta = compute_delta(repo, "FEAT-NAV-017", c1)
    assert delta.goals_reached == ["GOAL-NAV-001"]
    assert delta.goals_regressed == []
    assert delta.scenarios_added == ["SIM-048"]
    assert delta.new_open_items == ["false-reacquisition risk under wind"]
    assert delta.metric_changes == [
        {
            "metric": "reacquisition_rate",
            "from": 0.87,
            "to": 0.95,
            "regression": False,
        }
    ]


def test_delta_from_head_is_empty(seeded_repo):
    repo, _ = seeded_repo
    head = git(repo, "rev-parse", "HEAD")
    delta = compute_delta(repo, "FEAT-NAV-017", head)
    assert delta.prs_merged == []
    assert delta.requirements_changed == []
    assert delta.adrs_added == []
    assert delta.goals_reached == []
    assert delta.goals_regressed == []
    assert delta.scenarios_added == []
    assert delta.new_open_items == []
    assert delta.metric_changes == []


def test_delta_unknown_feature_raises(seeded_repo):
    repo, c1 = seeded_repo
    with pytest.raises(ValueError):
        compute_delta(repo, "FEAT-NOPE", c1)


def test_delta_unknown_since_commit_raises(seeded_repo):
    repo, _ = seeded_repo
    with pytest.raises(ValueError):
        compute_delta(repo, "FEAT-NAV-017", "deadbeef" * 5)
