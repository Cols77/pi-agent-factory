"""Shared scratch-git-repo seeding for delta/checkpoint tests (Inc 7).

Builds a real git history (baseline C1 -> PR merge C2 -> open-question C3 ->
new experiment + REACHED transition C4/C4b) so delta computation and the
catchup command can be tested deterministically. Not a test module itself
(no `pytestmark`); it is imported by test_compute.py and test_catchup.py.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

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


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def commit_all(repo: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    git(repo, "commit", "-q", "-m", message)


def seed_baseline(repo: Path) -> str:
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
    commit_all(repo, "C1 baseline")
    c1 = git(repo, "rev-parse", "HEAD")
    _write_run_commit(repo, "RUN-20260815-0100", c1)
    return c1


def _write_run_commit(repo: Path, run_id: str, commit: str) -> None:
    manifest = repo / "evidence" / "runs" / run_id / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["commit"] = commit
    manifest.write_text(json.dumps(data), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    git(repo, "commit", "-q", "-m", f"record run commit {run_id}", "--allow-empty")


def merge_pr(repo: Path) -> None:
    """C2: branch work (SR-017 change + ADR-0002) merged back as a PR."""
    default_branch = git(repo, "symbolic-ref", "--short", "HEAD")
    git(repo, "checkout", "-q", "-b", "pr-nav-017")
    sr = repo / "requirements" / "SR-017.md"
    sr.write_text(sr.read_text(encoding="utf-8") + "\n# changed in PR\n", encoding="utf-8")
    (repo / "docs" / "adr" / "ADR-0002.md").write_text(
        "---\nid: ADR-0002\ntitle: Pre-emption policy\nstatus: accepted\n---\n",
        encoding="utf-8",
    )
    commit_all(repo, "pr: SR-017 semantics + ADR-0002")
    git(repo, "checkout", "-q", default_branch)
    git(repo, "merge", "-q", "--no-ff", "pr-nav-017", "-m", "Merge pull request #17 from pr-nav-017")


def seed_rest(repo: Path) -> None:
    """C3: open question added; C4: new experiment run + REACHED transition."""
    feat = repo / "docs" / "features" / "FEAT-NAV-017.md"
    feat.write_text(
        feat.read_text(encoding="utf-8") + "- false-reacquisition risk under wind\n",
        encoding="utf-8",
    )
    commit_all(repo, "C3 open question added")

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
    commit_all(repo, "C4 sim run SIM-048")
    c4 = git(repo, "rev-parse", "HEAD")
    _write_run_commit(repo, "RUN-20260816-0100", c4)
    c4 = git(repo, "rev-parse", "HEAD")
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
    commit_all(repo, "C4b record REACHED transition")


def seed_repo(repo: Path) -> tuple[Path, str]:
    """Init a scratch git repo and commit C1..C4b; returns (repo, since=c1)."""
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    c1 = seed_baseline(repo)
    merge_pr(repo)
    seed_rest(repo)
    return repo, c1