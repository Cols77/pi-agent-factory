"""/catchup command shim + query_catchup (Inc 7 Task 3).

`/catchup <feature>` loads the recorded checkpoint, computes the
deterministic delta, upgrades the checkpoint to HEAD, and routes the REVIEW
presentation to the SCC browser. A feature with no recorded review is
reported honestly, never synthesized.
"""

from __future__ import annotations

import pytest

from _seed_repo import git, seed_repo
from factory.commands.catchup import run_catchup
from factory.delta.checkpoint import Checkpoint, load_checkpoint, save_checkpoint
from factory.system.queries import ScopeNotFoundError, query_catchup

pytestmark = pytest.mark.unit


@pytest.fixture
def seeded_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    return seed_repo(repo)


def _save_checkpoint_at(pi_dir, feature, commit):
    save_checkpoint(pi_dir, Checkpoint(feature=feature, commit=commit, reviewed_at="2026-08-16T10:00:00Z"))


def test_run_catchup_with_checkpoint_computes_and_upgrades(seeded_repo, tmp_path):
    repo, c1 = seeded_repo
    head = git(repo, "rev-parse", "HEAD")
    pi_dir = tmp_path / "pi"
    _save_checkpoint_at(pi_dir, "FEAT-NAV-017", c1)

    outcome = run_catchup(repo, "FEAT-NAV-017", checkpoint_dir=pi_dir)

    assert outcome["reviewed"] is True
    assert outcome["since_commit"] == c1
    delta = outcome["delta"]
    assert delta["requirements_changed"] == ["SR-017"]
    assert delta["goals_reached"] == ["GOAL-NAV-001"]
    # The checkpoint is upgraded to HEAD (the delta has now been shown).
    upgraded = load_checkpoint(pi_dir, "FEAT-NAV-017")
    assert upgraded is not None
    assert upgraded.commit == head
    assert upgraded.reviewed_at != "2026-08-16T10:00:00Z"
    # REVIEW presentation routed to the SCC browser catch-up scope.
    presentation = outcome["presentation"]
    assert presentation["level"] == "REVIEW"
    assert presentation["adapter"] == "browser"
    assert presentation["target"] == "system?scope=catchup:FEAT-NAV-017"


def test_run_catchup_without_checkpoint_reports_unreviewed(seeded_repo, tmp_path):
    repo, _ = seeded_repo
    outcome = run_catchup(repo, "FEAT-NAV-017", checkpoint_dir=tmp_path / "pi")
    assert outcome["reviewed"] is False
    assert outcome["delta"] is None
    assert outcome["presentation"]["level"] == "REVIEW"


def test_run_catchup_unknown_feature_with_checkpoint_raises(seeded_repo, tmp_path):
    repo, c1 = seeded_repo
    pi_dir = tmp_path / "pi"
    _save_checkpoint_at(pi_dir, "FEAT-NOPE", c1)
    with pytest.raises(ValueError):
        run_catchup(repo, "FEAT-NOPE", checkpoint_dir=pi_dir)


def test_query_catchup_with_checkpoint(seeded_repo, tmp_path):
    repo, c1 = seeded_repo
    pi_dir = repo / ".pi"
    _save_checkpoint_at(pi_dir, "FEAT-NAV-017", c1)
    result = query_catchup(repo, "FEAT-NAV-017")
    assert result["reviewed"] is True
    assert result["since_commit"] == c1
    assert result["delta"]["metric_changes"][0]["to"] == 0.95
    # The query is read-only: the checkpoint stays at c1.
    assert load_checkpoint(pi_dir, "FEAT-NAV-017").commit == c1


def test_query_catchup_without_checkpoint(seeded_repo):
    repo, _ = seeded_repo
    result = query_catchup(repo, "FEAT-NAV-017")
    assert result["reviewed"] is False
    assert result["delta"] is None


def test_query_catchup_unknown_feature_raises_scope_error(seeded_repo, tmp_path):
    repo, c1 = seeded_repo
    _save_checkpoint_at(repo / ".pi", "FEAT-NOPE", c1)
    with pytest.raises(ScopeNotFoundError):
        query_catchup(repo, "FEAT-NOPE")


def test_delta_cli_catchup_json(seeded_repo, tmp_path):
    """`python -m factory.delta catchup --json` emits the command outcome."""
    import json
    import subprocess
    import sys

    repo, c1 = seeded_repo
    _save_checkpoint_at(repo / ".pi", "FEAT-NAV-017", c1)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "factory.delta",
            "catchup",
            "--feature",
            "FEAT-NAV-017",
            "--repo",
            str(repo),
            "--json",
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["reviewed"] is True
    assert payload["delta"]["goals_reached"] == ["GOAL-NAV-001"]
    assert payload["presentation"]["target"] == "system?scope=catchup:FEAT-NAV-017"
