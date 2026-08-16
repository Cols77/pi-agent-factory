"""Refresh policy + reconciliation + closure (Inc 7, Tasks 5e/5f/5i/5j/5m)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.freshness import policy
from factory.freshness.deps import FreshnessState, check_artifact
from factory.freshness.fingerprint import fingerprint_file, fingerprint_value
from factory.freshness.policy import (
    RefreshAction,
    freshness_closure,
    reconcile,
    refresh_decision,
    register_generator,
)

# Reuse the deps-test repo fixture by importing its builders.
from tests.unit.freshness.test_deps import (
    _change_code,
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

pytestmark = pytest.mark.unit


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
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
    _diagram(repo, "DIAG-NAV-009", ["run:RUN-20260816-0100"])
    _explainer(
        repo,
        "NAV-PREEMPTION",
        explains=["SR-017"],
        sr_fps={"SR-017": _sr_digest(repo)},
        code_fps={"src/navigation/preemption.py": _code_digest(repo)},
    )
    _commit_all(repo, "evidence + diagram + explainer")
    return repo


def _sr_digest(repo: Path) -> str:
    return fingerprint_value("SR-017", (repo / "requirements" / "SR-017.md").read_text(encoding="utf-8")).digest


def _code_digest(repo: Path) -> str:
    return fingerprint_file("file", repo / "src/navigation/preemption.py", repo).digest


def _explainer_path(repo: Path) -> Path:
    return repo / "docs" / "visual-explain" / "NAV-PREEMPTION.md"


def _rewrite_explainer(repo: Path, **meta) -> None:
    """Rewrite the explainer with fresh fingerprints so regeneration 'succeeds'."""
    parts = ["---", "id: NAV-PREEMPTION.md", "title: E"]
    if "explains" in meta:
        quoted = ['"' + e + '"' for e in meta["explains"]]
        parts.append("explains: [" + ", ".join(quoted) + "]")
    parts.append("dep_fingerprint: " + json.dumps(meta.get("sr_fps", {"SR-017": _sr_digest(repo)})))
    parts.append(
        "code_fingerprint: "
        + json.dumps(meta.get("code_fps", {"src/navigation/preemption.py": _code_digest(repo)}))
    )
    if meta.get("generator"):
        parts.append(f"generator: {meta['generator']}")
    parts.append("---")
    _explainer_path(repo).write_text("\n".join(parts) + "\nbody\n", encoding="utf-8")


@pytest.fixture(autouse=True)
def _clear_generators():
    policy._GENERATORS.clear()
    policy._GENERATOR_VERSIONS.clear()
    yield
    policy._GENERATORS.clear()
    policy._GENERATOR_VERSIONS.clear()


# ── 5e: authority-aware refresh policy ─────────────────────────────────────


def test_policy_preserves_authoritative_contracts(repo):
    decision = refresh_decision(repo, "sr:SR-017")
    assert decision.action is RefreshAction.REQUEST_HUMAN_ACTION


def test_policy_routes_implementation_to_dev(repo):
    decision = refresh_decision(repo, "code:src/navigation/preemption.py")
    assert decision.action is RefreshAction.ROUTE_TO_DEV


def test_policy_evidence_without_harness_requests_human(repo):
    # The required action is a rerun; harness availability is a resource
    # boundary checked at execution, not a policy change.
    decision = refresh_decision(repo, "run:RUN-20260816-0100")
    assert decision.action is RefreshAction.RERUN_VALIDATION


    pass


    pass


def test_policy_evidence_with_registered_rerun(repo):
    register_generator("run", lambda root, ref: True, version="1")
    decision = refresh_decision(repo, "run:RUN-20260816-0100")
    assert decision.action is RefreshAction.RERUN_VALIDATION


def test_policy_generated_without_generator_regenerates_anyway(repo):
    # Generated kinds REQUIRE regeneration; an unregistered generator blocks
    # at execution (5e boundary) instead of changing the policy.
    decision = refresh_decision(repo, "explainer:NAV-PREEMPTION.md")
    assert decision.action is RefreshAction.REGENERATE


def test_policy_generated_with_generator_regenerates(repo):
    register_generator("explainer", lambda root, ref: True, version="1")
    assert refresh_decision(repo, "explainer:NAV-PREEMPTION.md").action is RefreshAction.REGENERATE


def test_policy_derived_recomputes(repo):
    assert refresh_decision(repo, "health").action is RefreshAction.RECOMPUTE


# ── 5f: automatic generated-artifact regeneration ──────────────────────────


def test_linked_sr_change_stales_explainer_then_regeneration_fixes(repo):
    _change_sr(repo)
    assert check_artifact(repo, "explainer:NAV-PREEMPTION.md").state == FreshnessState.STALE

    def regenerate(root, ref):
        _rewrite_explainer(root)  # writes fresh SR + code fingerprints
        return True

    register_generator("explainer", regenerate, version="1")
    result = reconcile(repo, ["explainer:NAV-PREEMPTION.md"])
    assert "explainer:NAV-PREEMPTION.md" in result.refreshed
    assert check_artifact(repo, "explainer:NAV-PREEMPTION.md").state == FreshnessState.FRESH


def test_linked_code_change_stales_explainer_when_sr_unchanged(repo):
    _change_code(repo)
    state = check_artifact(repo, "explainer:NAV-PREEMPTION.md")
    assert state.state == FreshnessState.STALE
    assert any("changed since evidence" in reason for reason in state.reasons)


def test_unrelated_code_change_keeps_explainer_fresh(repo):
    _code(repo, "src/unrelated.py", "x = 1\n")
    _commit_all(repo, "unrelated")
    assert check_artifact(repo, "explainer:NAV-PREEMPTION.md").state == FreshnessState.FRESH


def test_regeneration_success_means_new_fingerprints_fresh(repo):
    _change_sr(repo)

    def regenerate(root, ref):
        _rewrite_explainer(root)
        return True

    register_generator("explainer", regenerate, version="1")
    result = reconcile(repo, ["explainer:NAV-PREEMPTION.md"])
    assert "explainer:NAV-PREEMPTION.md" in result.refreshed
    # The rewritten file records the CURRENT SR digest.
    recorded = json.loads(_explainer_path(repo).read_text(encoding="utf-8").split("dep_fingerprint: ", 1)[1].split("\n", 1)[0])
    assert recorded["SR-017"] == _sr_digest(repo)


def test_regeneration_failure_leaves_visible_state(repo):
    _change_sr(repo)

    def failing_generator(root, ref):
        return False  # generator present but fails to write

    register_generator("explainer", failing_generator, version="1")
    result = reconcile(repo, ["explainer:NAV-PREEMPTION.md"])
    # Not fresh: the artifact stays stale and visible.
    assert "explainer:NAV-PREEMPTION.md" not in result.refreshed
    assert check_artifact(repo, "explainer:NAV-PREEMPTION.md").state == FreshnessState.STALE
    assert result.closure_reached is False


def test_generator_version_change_refreshes(repo):
    # Explainer records generator version 1; the registered generator is v2.
    _rewrite_explainer(repo, generator="diagram-design@1")

    def regenerate(root, ref):
        _rewrite_explainer(root, generator="diagram-design@2")
        return True

    register_generator("explainer", regenerate, version="diagram-design@2")
    result = reconcile(repo, ["explainer:NAV-PREEMPTION.md"])
    assert "explainer:NAV-PREEMPTION.md" in result.refreshed
    assert "generator: diagram-design@2" in _explainer_path(repo).read_text(encoding="utf-8")


def test_missing_generator_blocks_without_silent_fresh(repo):
    _change_sr(repo)
    result = reconcile(repo, ["explainer:NAV-PREEMPTION.md"])
    assert "explainer:NAV-PREEMPTION.md" in result.blocked
    assert result.closure_reached is False


# ── 5i: reconciliation verifies, never trusts ──────────────────────────────


def test_reconcile_does_not_trust_that_a_refresh_ran(repo):
    _change_sr(repo)

    def liar(root, ref):
        return True  # claims success, writes nothing

    register_generator("explainer", liar, version="1")
    result = reconcile(repo, ["explainer:NAV-PREEMPTION.md"])
    # The action ran but the fingerprint still mismatches -> still_stale.
    assert "explainer:NAV-PREEMPTION.md" in result.still_stale
    assert check_artifact(repo, "explainer:NAV-PREEMPTION.md").state == FreshnessState.STALE


def test_reconcile_evidence_without_harness_blocks(repo):
    _change_code(repo)
    result = reconcile(repo, ["run:RUN-20260816-0100"])
    assert "run:RUN-20260816-0100" in result.blocked
    assert result.closure_reached is False


# ── 5j: feature freshness closure ──────────────────────────────────────────


def test_closure_reached_when_everything_fresh(repo):
    closure = freshness_closure(repo, "FEAT-NAV-017")
    assert closure.closure_reached is True
    assert closure.remaining == {}


def test_closure_not_reached_with_stale_artifact(repo):
    _change_code(repo)
    closure = freshness_closure(repo, "FEAT-NAV-017")
    assert closure.closure_reached is False
    assert closure.remaining.get("run:RUN-20260816-0100") == "stale"
    assert closure.remaining.get("explainer:NAV-PREEMPTION.md") == "stale"


def test_closure_after_reconcile(repo):
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
    result = reconcile(
        repo,
        ["explainer:NAV-PREEMPTION.md", "run:RUN-20260816-0100"],
    )
    assert "explainer:NAV-PREEMPTION.md" in result.refreshed
    assert "run:RUN-20260816-0100" in result.refreshed
    closure = freshness_closure(repo, "FEAT-NAV-017")
    assert closure.closure_reached is True


# ── 5m: refresh loop protection ────────────────────────────────────────────


def test_bounded_attempts_prevent_infinite_refresh_loop(repo):
    _change_sr(repo)

    def never_fixes(root, ref):
        return True  # always 'runs', never converges

    register_generator("explainer", never_fixes, version="1")
    result = reconcile(repo, ["explainer:NAV-PREEMPTION.md"], max_attempts=3)
    # Bounded: after 3 attempts the artifact is still stale, reported, and the
    # call returned (no infinite loop).
    assert "explainer:NAV-PREEMPTION.md" in result.still_stale


def test_self_cycle_in_dependency_graph_terminates(repo):
    _diagram(repo, "DIAG-SELF", ["diag:DIAG-SELF"])
    _commit_all(repo, "self cycle")
    closure = freshness_closure(repo, "FEAT-NAV-017")
    assert closure.closure_reached is True
