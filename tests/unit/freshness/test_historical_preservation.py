"""Historical preservation (Inc 7 Task 5n).

Refreshing current engineering knowledge must not erase evidence of prior
states: old validation retains its provenance, superseded generated
artifacts remain attributable, and failure/rejection records stay
immutable. The freshness engine never deletes -- these tests prove it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.freshness.policy import reconcile, register_generator
from tests.unit.freshness.test_deps import (
    _change_sr,
    _code,
    _commit_all,
    _diagram,
    _explainer,
    _git,
    _goal,
    _run_with_deps,
    _sr,
)
from tests.unit.freshness.test_policy import _code_digest, _rewrite_explainer, _sr_digest



def _seeded_repo(repo: Path):
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _sr(repo)
    _code(repo, "src/navigation/preemption.py")
    _goal(repo)
    c1 = _commit_all(repo, "baseline")
    _run_with_deps(
        repo,
        "RUN-20260816-0100",
        commit=c1,
        sr_ids=["SR-017"],
        goals=["GOAL-NAV-001"],
        files=["src/navigation/preemption.py"],
    )
    _diagram(repo, "DIAG-NAV-009", ["SR-017"])
    _explainer(
        repo,
        "NAV-PREEMPTION",
        explains=["SR-017"],
        sr_fps={"SR-017": _sr_digest(repo)},
        code_fps={"src/navigation/preemption.py": _code_digest(repo)},
    )
    # A failure/rejection record that must stay immutable.
    goals_dir = repo / "goals"
    goals_dir.mkdir(parents=True, exist_ok=True)
    (goals_dir / "GOAL-NAV-001-transitions.jsonl").write_text(
        json.dumps(
            {
                "goal_id": "GOAL-NAV-001",
                "from_state": "ACTIVE",
                "to_state": "NOT_REACHED",
                "recorded_at": "2026-08-10T09:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _commit_all(repo, "evidence + diagram + explainer + transition log")
    return repo


@pytest.fixture(autouse=True)
def _clean_generators():
    from factory.freshness import policy

    policy._GENERATORS.clear()
    policy._GENERATOR_VERSIONS.clear()
    yield
    policy._GENERATORS.clear()
    policy._GENERATOR_VERSIONS.clear()


@pytest.mark.integration
def test_old_explainer_content_remains_in_git_history(tmp_path):
    repo = _seeded_repo(tmp_path)
    old_text = (repo / "docs" / "visual-explain" / "NAV-PREEMPTION.md").read_text(
        encoding="utf-8"
    )
    _change_sr(repo)

    def regenerate(root, ref):
        _rewrite_explainer(root)
        return True

    register_generator("explainer", regenerate, version="1")
    reconcile(repo, ["explainer:NAV-PREEMPTION.md"])

    # The current file has new fingerprints; the previous version is still in
    # git history (superseded, attributable).
    current = (repo / "docs" / "visual-explain" / "NAV-PREEMPTION.md").read_text(
        encoding="utf-8"
    )
    assert current != old_text
    historical = _git(
        repo, "show", "HEAD~1:docs/visual-explain/NAV-PREEMPTION.md"
    )
    # Only the trailing-newline convention may differ between writers.
    assert historical.rstrip("\n") == old_text.rstrip("\n")


@pytest.mark.integration
def test_reconcile_never_deletes_old_evidence_bundles(tmp_path):
    repo = _seeded_repo(tmp_path)
    _change_sr(repo)

    def rerun(root, ref):
        run_id = ref.partition(":")[2]
        manifest = root / "evidence" / "runs" / run_id / "manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["commit"] = _git(root, "rev-parse", "HEAD")
        manifest.write_text(json.dumps(data), encoding="utf-8")
        return True

    register_generator("run", rerun, version="1")
    reconcile(repo, ["run:RUN-20260816-0100"])
    # The run bundle still exists (refresh updated provenance, never deleted).
    assert (repo / "evidence" / "runs" / "RUN-20260816-0100" / "manifest.json").exists()


@pytest.mark.integration
def test_invalidated_evidence_kept_but_distinguished_from_current(tmp_path):
    repo = _seeded_repo(tmp_path)
    manifest = repo / "evidence" / "runs" / "RUN-20260816-0100" / "manifest.json"
    original_commit = json.loads(manifest.read_text(encoding="utf-8"))["commit"]

    _change_sr(repo)
    from factory.freshness.deps import check_artifact

    # The old evidence is STALE (its recorded commit predates the SR change)
    # but still present with its original provenance.
    state = check_artifact(repo, "run:RUN-20260816-0100")
    assert state.state.value == "stale"
    assert (repo / "evidence" / "runs" / "RUN-20260816-0100" / "manifest.json").exists()
    assert json.loads(manifest.read_text(encoding="utf-8"))["commit"] == original_commit


@pytest.mark.integration
def test_failure_records_and_rejected_hypotheses_stay_immutable(tmp_path):
    repo = _seeded_repo(tmp_path)
    transition_log = repo / "goals" / "GOAL-NAV-001-transitions.jsonl"
    before = transition_log.read_text(encoding="utf-8")

    # A full refresh pass over every artifact kind must not touch the log.
    _change_sr(repo)

    def regenerate(root, ref):
        _rewrite_explainer(root)
        return True

    def rerun(root, ref):
        run_id = ref.partition(":")[2]
        manifest = root / "evidence" / "runs" / run_id / "manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["commit"] = _git(root, "rev-parse", "HEAD")
        manifest.write_text(json.dumps(data), encoding="utf-8")
        return True

    register_generator("explainer", regenerate, version="1")
    register_generator("run", rerun, version="1")
    reconcile(
        repo,
        ["explainer:NAV-PREEMPTION.md", "run:RUN-20260816-0100"],
    )

    assert transition_log.read_text(encoding="utf-8") == before
    # The recorded NOT_REACHED failure is still in git history too.
    assert "NOT_REACHED" in _git(repo, "show", "HEAD:goals/GOAL-NAV-001-transitions.jsonl")
