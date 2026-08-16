"""Context delta computation (Inc 7 Task 2).

From a seeded git history + goals/history + sim runs, `compute_delta` must
produce the spec §31 / §9.4 delta deterministically: PRs merged, requirement
changes, added ADRs, new scenarios/experiments, goal transitions, metric
deltas and new open items -- never an LLM summary of the past.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from factory.delta.compute import ContextDelta, compute_delta

pytestmark = pytest.mark.unit

GOAL_FM = """---
id: GOAL-NAV-001
title: "Pre-emption under reacquisition"
feature: [FEAT-NAV-017]
requirements: [SR-017]
metric: {"name": "reacquisition_rate", "source_experiment": "SIM-047"}
target: {"operator": ">=", "value": 0.9}
state: NOT_REACHED
---
"""


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def _commit_all(repo: Path, message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    return _git(repo, "commit", "-q", "-m", message, "--no-verify")
    # ^--no-verify avoided: use default hooks (none in a scratch repo)


def _seed_baseline(repo: Path) -> str:
    """Commit C1: feature, SR, ADR-0001, goal, and the SIM-047 baseline run."""
    for directory in (
        repo / "requirements",
        repo / "docs" / "features",
        repo / "docs" / "adr",
        repo / "goals",
        repo / "evidence" / "runs",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    (repo / "requirements" / "SR-017.md").write_text(
        "---\nid: SR-017\ntitle: Pre-emption\ndomain: behavioral\nstatement: pre-empt on reacquisition\n---\n",
        encoding="utf-8",
    )
    (repo / "docs" / "features" / "FEAT-NAV-017.md").write_text(
        "---\nid: FEAT-NAV-017\ntitle: Navigation pre-emption\nrequirements: [SR-017]\n---\n"
        "# Feature\n\n## Open Questions\n\n- pre-existing concern\n",
        encoding="utf-8",
    )
    (repo / "docs" / "adr" / "ADR-0001.md").write_text(
        "---\nid: ADR-0001\ntitle: Baseline decision\nstatus: accepted\n---\n",
        encoding="utf-8",
    )
    (repo / "goals" / "GOAL-NAV-001.md").write_text(GOAL_FM, encoding="utf-8")
    run_dir = repo / "evidence" / "runs" / "RUN-20260815-0100"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run": "RUN-20260815-0100",
                "experiment": "SIM-047",
                "feature": "FEAT-NAV-017",
                "requirements": ["SR-017"],
                "goals": ["GOAL-NAV-001"],
                "commit": "PLACEHOLDER",
                "result": "passed",
                "recorded_ts": "2026-08-15T10:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "metrics.json").write_text(
        json.dumps({"reacquisition_rate": 0.87}), encoding="utf-8"
    )
    _commit_all(repo, "C1 baseline")
    c1 = _git(repo, "rev-parse", "HEAD")
    # The run manifest's commit field is filled after we know the commit.
    _write_run_commit(repo, "RUN-20260815-0100", c1)
    return c1


def _write_run_commit(repo: Path, run_id: str, commit: str) -> None:
    manifest = repo / "evidence" / "runs" / run_id / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["commit"] = commit
    manifest.write_text(json.dumps(data), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    _git(repo, "commit", "-q", "-m", f"record run commit {run_id}", "--allow-empty")


def _merge_pr(repo: Path) -> None:
    """C2: branch work (SR-017 change + ADR-0002) merged back as a PR."""
    default_branch = _git(repo, "symbolic-ref", "--short", "HEAD")
    _git(repo, "checkout", "-q", "-b", "pr-nav-017")
    sr = repo / "requirements" / "SR-017.md"
    sr.write_text(sr.read_text(encoding="utf-8") + "\n# changed in PR\n", encoding="utf-8")
    (repo / "docs" / "adr" / "ADR-0002.md").write_text(
        "---\nid: ADR-0002\ntitle: Pre-emption policy\nstatus: accepted\n---\n",
        encoding="utf-8",
    )
    _commit_all(repo, "pr: SR-017 semantics + ADR-0002")
    _git(repo, "checkout", "-q", default_branch)
    _git(repo, "merge", "-q", "--no-ff", "pr-nav-017", "-m", "Merge pull request #17 from pr-nav-017")


def _seed_rest(repo: Path, c1: str) -> None:
    """C3: open question added; C4: new experiment run + REACHED transition."""
    feat = repo / "docs" / "features" / "FEAT-NAV-017.md"
    feat.write_text(
        feat.read_text(encoding="utf-8") + "- false-reacquisition risk under wind\n",
        encoding="utf-8",
    )
    _commit_all(repo, "C3 open question added")

    run_dir = repo / "evidence" / "runs" / "RUN-20260816-0100"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run": "RUN-20260816-0100",
                "experiment": "SIM-048",
                "feature": "FEAT-NAV-017",
                "requirements": ["SR-017"],
                "goals": ["GOAL-NAV-001"],
                "commit": "PLACEHOLDER",
                "result": "passed",
                "recorded_ts": "2026-08-16T10:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "metrics.json").write_text(
        json.dumps({"reacquisition_rate": 0.95}), encoding="utf-8"
    )
    transitions = repo / "goals" / "GOAL-NAV-001-transitions.jsonl"
    _commit_all(repo, "C4 sim run SIM-048")
    c4 = _git(repo, "rev-parse", "HEAD")
    _write_run_commit(repo, "RUN-20260816-0100", c4)
    c4 = _git(repo, "rev-parse", "HEAD")
    transitions.write_text(
        json.dumps(
            {
                "goal_id": "GOAL-NAV-001",
                "from_state": "NOT_REACHED",
                "to_state": "REACHED",
                "value": 0.95,
                "target": 0.9,
                "operator": ">=",
                "run": "RUN-20260816-0100",
                "commit": c4,
                "recorded_at": "2026-08-16T11:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _commit_all(repo, "C4b record REACHED transition")


@pytest.fixture
def seeded_repo(tmp_path):
    """A scratch git repo with four commits; returns (repo, since_commit)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    c1 = _seed_baseline(repo)
    _merge_pr(repo)
    _seed_rest(repo, c1)
    return repo, c1


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
    head = _git(repo, "rev-parse", "HEAD")
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
