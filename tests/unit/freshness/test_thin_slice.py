"""Thin-slice freshness acceptance (Inc 7 Task 5o).

The navigation/pre-emption feature (FEAT-NAV-017 -> SR-017 -> code ->
evidence -> diagram -> explainer) as the required dependency-driven
acceptance slice. Test A = requirement semantic change; Test B =
implementation-only change. Both prove invalidation is dependency-driven,
never special-cased around SR changes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.freshness.deps import FreshnessState, check_artifact, compute_impact
from factory.freshness.policy import (
    RefreshAction,
    freshness_closure,
    reconcile,
    refresh_decision,
    register_generator,
)
from factory.requirements.register import content_checksum, parse_requirement
from tests.unit.freshness.test_deps import (
    _change_code,
    _code,
    _commit_all,
    _diagram,
    _explainer,
    _git,
    _goal,
    _run_with_deps,
)
from tests.unit.freshness.test_policy import _code_digest, _rewrite_explainer, _sr_digest

pytestmark = pytest.mark.unit


def _rewrite_diagram(root: Path) -> None:
    diag = root / "docs" / "diagrams" / "DIAG-NAV-009.md"
    diag.write_text(
        "---\nid: DIAG-NAV-009\ntitle: D\nillustrates: [SR-017]\n"
        "dep_fingerprint: " + json.dumps({"sr:SR-017": _sr_digest(root)}) + "\n---\nbody\n",
        encoding="utf-8",
    )


def _rerun(root: Path, ref: str) -> bool:
    """Simulate an evidence rerun: re-record the code dependency digests and
    the run's commit at the current HEAD (a real rerun re-fingerprints)."""
    from factory.freshness.fingerprint import fingerprint_file

    run_id = ref.partition(":")[2]
    manifest_path = root / "evidence" / "runs" / run_id / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    deps = []
    for dep in data.get("dependencies", []):
        if isinstance(dep, dict) and dep.get("kind") == "file" and isinstance(dep.get("source"), str):
            dep["digest"] = fingerprint_file(dep["name"], root / dep["source"], root).digest
        deps.append(dep)
    data["dependencies"] = deps
    data["commit"] = _git(root, "rev-parse", "HEAD")
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    return True


def _register_all_refresh():
    register_generator("explainer", lambda root, ref: _rewrite_explainer(root), version="1")
    register_generator("run", _rerun, version="1")
    register_generator("diag", lambda root, ref: (_rewrite_diagram(root) or True), version="1")


@pytest.fixture()
def drone_repo(tmp_path):
    """The navigation/pre-emption slice: all artifacts fresh at baseline."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")

    sr_path = repo / "requirements" / "SR-017.md"
    sr_path.parent.mkdir(parents=True, exist_ok=True)
    sr_path.write_text(
        "---\nid: SR-017\ntitle: Pre-emption\ndomain: behavioral\n"
        "statement: pre-empt on reacquisition\n"
        "upstream: []\n"
        "binding:\n  experiment: sim-047\n  metric: reacquisition_rate\n  assert: '>= 0.9'\n  trials: 1\n---\n",
        encoding="utf-8",
    )
    checksum = content_checksum(parse_requirement(sr_path))
    sr_path.write_text(
        "---\nid: SR-017\ntitle: Pre-emption\ndomain: behavioral\n"
        "statement: pre-empt on reacquisition\n"
        "upstream: []\n"
        "binding:\n  experiment: sim-047\n  metric: reacquisition_rate\n  assert: '>= 0.9'\n  trials: 1\n"
        f"checksum: {checksum}\n---\n",
        encoding="utf-8",
    )

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
    _rewrite_diagram(repo)
    _explainer(
        repo,
        "NAV-PREEMPTION",
        explains=["SR-017"],
        sr_fps={"SR-017": _sr_digest(repo)},
        code_fps={"src/navigation/preemption.py": _code_digest(repo)},
    )
    _commit_all(repo, "evidence + diagram + explainer")
    return repo


@pytest.fixture(autouse=True)
def _clean_generators():
    from factory.freshness import policy

    policy._GENERATORS.clear()
    policy._GENERATOR_VERSIONS.clear()
    yield
    policy._GENERATORS.clear()
    policy._GENERATOR_VERSIONS.clear()


def _assert_baseline_fresh(repo):
    assert check_artifact(repo, "sr:SR-017").state == FreshnessState.FRESH
    assert check_artifact(repo, "code:src/navigation/preemption.py").state == FreshnessState.FRESH
    assert check_artifact(repo, "run:RUN-20260816-0100").state == FreshnessState.FRESH
    assert check_artifact(repo, "explainer:NAV-PREEMPTION.md").state == FreshnessState.FRESH
    assert check_artifact(repo, "diag:DIAG-NAV-009").state == FreshnessState.FRESH
    assert freshness_closure(repo, "FEAT-NAV-017").closure_reached is True


def _change_sr_statement(repo, text="pre-empt faster on reacquisition"):
    sr_path = repo / "requirements" / "SR-017.md"
    sr_path.write_text(
        sr_path.read_text(encoding="utf-8").replace(
            "statement: pre-empt on reacquisition", f"statement: {text}"
        ),
        encoding="utf-8",
    )
    _commit_all(repo, "sr semantics changed")


def _checksum_of(repo):
    """The checksum currently recorded in SR-017's frontmatter."""
    import re

    text = (repo / "requirements" / "SR-017.md").read_text(encoding="utf-8")
    match = re.search(r"^checksum: (\S+)$", text, re.MULTILINE)
    return match.group(1) if match else ""


def test_acceptance_a_requirement_semantic_change(drone_repo):
    repo = drone_repo
    _assert_baseline_fresh(repo)

    # Change requirement semantics: authoritative SR stays fresh; implementation
    # -> ROUTE_TO_DEV; evidence/diagram/explainer stale; closure NOT reached.
    _change_sr_statement(repo)
    assert check_artifact(repo, "sr:SR-017").state == FreshnessState.FRESH
    impact = compute_impact(repo, ["sr:SR-017"])
    assert "code:src/navigation/preemption.py" in set(impact.directly_affected) | set(impact.transitively_affected)
    assert refresh_decision(repo, "code:src/navigation/preemption.py").action is RefreshAction.ROUTE_TO_DEV
    assert check_artifact(repo, "run:RUN-20260816-0100").state == FreshnessState.STALE
    assert check_artifact(repo, "diag:DIAG-NAV-009").state == FreshnessState.STALE
    assert check_artifact(repo, "explainer:NAV-PREEMPTION.md").state == FreshnessState.STALE
    assert freshness_closure(repo, "FEAT-NAV-017").closure_reached is False

    # Auto-refresh the safe generated/evidenced artifacts.
    _register_all_refresh()
    affected = list(set(impact.directly_affected) | set(impact.transitively_affected))
    code_before = (repo / "src/navigation/preemption.py").read_text(encoding="utf-8")
    result = reconcile(repo, affected)
    assert "run:RUN-20260816-0100" in result.refreshed
    assert "diag:DIAG-NAV-009" in result.refreshed
    assert "explainer:NAV-PREEMPTION.md" in result.refreshed
    # The implementation is never auto-rewritten: still ROUTE_TO_DEV, closure
    # stays open until a human DEV repair lands.
    assert (repo / "src/navigation/preemption.py").read_text(encoding="utf-8") == code_before
    assert refresh_decision(repo, "code:src/navigation/preemption.py").action is RefreshAction.ROUTE_TO_DEV
    assert freshness_closure(repo, "FEAT-NAV-017").closure_reached is False

    # DEV repair: rewrite the implementation, accept the new SR semantics
    # (re-record its checksum), then re-validate (the rerun records the post-
    # repair HEAD + fresh dependency digests).
    _change_code(repo)
    sr_path = repo / "requirements" / "SR-017.md"
    text = sr_path.read_text(encoding="utf-8")
    new_checksum = content_checksum(parse_requirement(sr_path))
    sr_path.write_text(text.replace("checksum: " + _checksum_of(repo), f"checksum: {new_checksum}"), encoding="utf-8")
    _commit_all(repo, "accept new semantics")
    _rerun(repo, "run:RUN-20260816-0100")
    assert check_artifact(repo, "code:src/navigation/preemption.py").state == FreshnessState.FRESH
    assert check_artifact(repo, "run:RUN-20260816-0100").state == FreshnessState.FRESH
    assert freshness_closure(repo, "FEAT-NAV-017").closure_reached is True

    # Historical pre-change evidence still exists but cannot validate current state.
    assert (repo / "evidence" / "runs" / "RUN-20260816-0100" / "manifest.json").exists()


def test_acceptance_b_implementation_only_change(drone_repo):
    repo = drone_repo
    _assert_baseline_fresh(repo)

    # Change implementation only: SR stays fresh; evidence + explainer stale;
    # invalidation is dependency-driven (the SR is NOT in the impact closure).
    _change_code(repo)
    assert check_artifact(repo, "sr:SR-017").state == FreshnessState.FRESH
    assert check_artifact(repo, "code:src/navigation/preemption.py").state == FreshnessState.FRESH
    assert check_artifact(repo, "run:RUN-20260816-0100").state == FreshnessState.STALE
    assert check_artifact(repo, "explainer:NAV-PREEMPTION.md").state == FreshnessState.STALE
    impact = compute_impact(repo, ["code:src/navigation/preemption.py"])
    assert "sr:SR-017" not in set(impact.directly_affected) | set(impact.transitively_affected)
    assert freshness_closure(repo, "FEAT-NAV-017").closure_reached is False

    # Rerun validation + regenerate knowledge -> closure reached, SR unchanged.
    _register_all_refresh()
    affected = list(set(impact.directly_affected) | set(impact.transitively_affected))
    result = reconcile(repo, affected)
    assert "run:RUN-20260816-0100" in result.refreshed
    assert "explainer:NAV-PREEMPTION.md" in result.refreshed
    assert check_artifact(repo, "sr:SR-017").state == FreshnessState.FRESH
    assert freshness_closure(repo, "FEAT-NAV-017").closure_reached is True