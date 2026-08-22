"""/catchup freshness integration (Inc 7, Task 5k): the ContextDelta's
invalidated / auto_refreshed / refresh_required / blocked_refreshes /
freshness_closure_reached fields are derived deterministically from the
freshness dependency graph, never narrated.
"""

from __future__ import annotations

import json

import pytest

from factory.delta.compute import compute_delta
from factory.delta.freshness import apply_freshness
from factory.freshness.policy import register_generator
from tests.unit.freshness.test_deps import (_change_code, _change_sr, _code, _commit_all, _diagram, _explainer, _git, _goal, _run_with_deps, _sr)
from tests.unit.freshness.test_policy import _code_digest, _rewrite_explainer, _sr_digest

pytestmark = pytest.mark.unit


@pytest.fixture
def delta_repo(tmp_path):
    """A git repo with a checkpoint at baseline and changes after it."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _sr(repo)
    _code(repo, "src/navigation/preemption.py")
    _goal(repo)
    feat_dir = repo / "docs" / "features"
    feat_dir.mkdir(parents=True, exist_ok=True)
    (feat_dir / "FEAT-NAV-017.md").write_text(
        "---\nid: FEAT-NAV-017\ntitle: Nav pre-emption\nrequirements: [SR-017]\n---\n# intent\n",
        encoding="utf-8",
    )
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
    import json as _json

    diag_path = repo / "docs" / "diagrams" / "DIAG-NAV-009.md"
    diag_path.write_text(
        "---\nid: DIAG-NAV-009\ntitle: D\nillustrates: [SR-017]\n"
        "dep_fingerprint: " + _json.dumps({"sr:SR-017": _sr_digest(repo)}) + "\n---\n",
        encoding="utf-8",
    )
    _explainer(
        repo,
        "NAV-PREEMPTION",
        explains=["SR-017"],
        sr_fps={"SR-017": _sr_digest(repo)},
        code_fps={"src/navigation/preemption.py": _code_digest(repo)},
    )
    _commit_all(repo, "evidence + diagram + explainer")
    # Record a checkpoint at the commit BEFORE the changes below.
    from factory.delta.checkpoint import Checkpoint, save_checkpoint

    save_checkpoint(repo / ".pi", Checkpoint("FEAT-NAV-017", c1, "2026-08-16T10:00:00Z"))
    return repo, c1


def _reset_generators():
    from factory.freshness import policy

    policy._GENERATORS.clear()
    policy._GENERATOR_VERSIONS.clear()


def test_delta_freshness_invalidates_affected_closure(delta_repo):
    repo, c1 = delta_repo
    _reset_generators()
    _change_sr(repo)
    _change_code(repo)
    delta = apply_freshness(repo, compute_delta(repo, "FEAT-NAV-017", c1))
    # SR + code changed -> the run (evidence) and the explainer are invalidated.
    assert "run:RUN-20260816-0100" in delta.invalidated
    assert "explainer:NAV-PREEMPTION.md" in delta.invalidated
    assert "SR-017" in delta.requirements_changed
    assert "src/navigation/preemption.py" in delta.code_files_changed
    # No generators registered: refresh blocked / required, closure NOT reached.
    assert delta.freshness_closure_reached is False
    assert "run:RUN-20260816-0100" in delta.blocked_refreshes
    assert "explainer:NAV-PREEMPTION.md" in delta.blocked_refreshes


def test_delta_freshness_auto_refreshes_when_generators_registered(delta_repo):
    repo, c1 = delta_repo
    _change_sr(repo)

    def regenerate(root, ref):
        _rewrite_explainer(root)
        return True

    def rerun(root, ref):
        import json

        run_id = ref.partition(":")[2]
        manifest = root / "evidence" / "runs" / run_id / "manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["commit"] = _git(root, "rev-parse", "HEAD")
        manifest.write_text(json.dumps(data), encoding="utf-8")
        return True

    register_generator("explainer", regenerate, version="1")
    register_generator("run", rerun, version="1")

    def regenerate_diagram(root, ref):
        diag_path = root / "docs" / "diagrams" / "DIAG-NAV-009.md"
        diag_path.write_text(
            "---\nid: DIAG-NAV-009\ntitle: D\nillustrates: [SR-017]\n"
            "dep_fingerprint: "
            + json.dumps({"sr:SR-017": _sr_digest(root)})
            + "\n---\n",
            encoding="utf-8",
        )
        return True

    register_generator("diag", regenerate_diagram, version="1")
    delta = apply_freshness(repo, compute_delta(repo, "FEAT-NAV-017", c1))
    assert "explainer:NAV-PREEMPTION.md" in delta.auto_refreshed
    assert "run:RUN-20260816-0100" in delta.auto_refreshed
    assert "diag:DIAG-NAV-009" in delta.auto_refreshed
    assert delta.freshness_closure_reached is True


def test_delta_freshness_no_changes_closure_reached(delta_repo):
    repo, c1 = delta_repo
    _reset_generators()
    delta = apply_freshness(repo, compute_delta(repo, "FEAT-NAV-017", c1))
    # Nothing changed since the checkpoint: nothing invalidated.
    assert delta.invalidated == []
    assert delta.freshness_closure_reached is True
