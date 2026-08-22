"""Change-impact freshness findings (Inc 7 Task 5l).

`freshness_health` composes the freshness dependency graph into deterministic
findings: IMPL_STALE (semantic invalidation -> ROUTE_TO_DEV), EVIDENCE_STALE,
EXPLAINER_STALE, DIAGRAM_STALE, MISSING_PROVENANCE, REFRESH_BLOCKED,
REGENERATION_FAILED and CLOSURE_UNRESOLVED. A pure query: it never executes
refresh actions.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.freshness.policy import register_generator
from factory.system import health
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
)
from tests.unit.freshness.test_policy import _code_digest, _sr_digest

pytestmark = pytest.mark.unit


def _reset_generators():
    from factory.freshness import policy

    policy._GENERATORS.clear()
    policy._GENERATOR_VERSIONS.clear()


@pytest.fixture(autouse=True)
def _clean_generators():
    _reset_generators()
    yield
    _reset_generators()


def _seeded_repo(repo: Path):
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    # SR-017 WITH a binding + matching checksum so a semantic change (statement
    # edit) makes the register checksum go stale (the IMPL_STALE trigger).
    from factory.requirements.register import content_checksum, parse_requirement

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
    diag_path = repo / "docs" / "diagrams" / "DIAG-NAV-009.md"
    diag_path.write_text(
        "---\nid: DIAG-NAV-009\ntitle: D\nillustrates: [SR-017]\n"
        "dep_fingerprint: " + json.dumps({"sr:SR-017": _sr_digest(repo)}) + "\n---\n",
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
    return repo


def _codes(findings):
    return [(f.code, f.subject) for f in findings]


def test_impl_stale_when_upstream_requirement_changed(tmp_path):
    repo = _seeded_repo(tmp_path)
    # Semantic change: the statement field changes -> register checksum stale.
    sr_path = repo / "requirements" / "SR-017.md"
    sr_path.write_text(
        sr_path.read_text(encoding="utf-8").replace(
            "statement: pre-empt on reacquisition",
            "statement: pre-empt faster on reacquisition",
        ),
        encoding="utf-8",
    )
    _commit_all(repo, "sr semantics changed")
    findings = health.freshness_health(repo)
    assert ("IMPL_STALE", "code:src/navigation/preemption.py") in _codes(findings)


def test_evidence_stale_when_code_changed(tmp_path):
    repo = _seeded_repo(tmp_path)
    _change_code(repo)
    findings = health.freshness_health(repo)
    assert ("EVIDENCE_STALE", "run:RUN-20260816-0100") in _codes(findings)


def test_explainer_and_diagram_stale_when_sr_changed(tmp_path):
    repo = _seeded_repo(tmp_path)
    _change_sr(repo)
    findings = health.freshness_health(repo)
    assert ("EXPLAINER_STALE", "explainer:NAV-PREEMPTION.md") in _codes(findings)
    assert ("DIAGRAM_STALE", "diag:DIAG-NAV-009") in _codes(findings)


def test_missing_provenance_finding(tmp_path):
    repo = _seeded_repo(tmp_path)
    # An explainer that declares explains: but records no fingerprints.
    _explainer(repo, "NO-FP", explains=["SR-017"])
    _commit_all(repo, "explainer without fingerprints")
    findings = health.freshness_health(repo)
    assert ("MISSING_PROVENANCE", "explainer:NO-FP.md") in _codes(findings)


def test_refresh_blocked_when_no_generator_registered(tmp_path):
    repo = _seeded_repo(tmp_path)
    _change_sr(repo)
    findings = health.freshness_health(repo)
    blocked = [f for f in findings if f.code == "REFRESH_BLOCKED"]
    assert any(f.subject == "explainer:NAV-PREEMPTION.md" for f in blocked)
    assert any(f.subject == "run:RUN-20260816-0100" for f in blocked)


def test_regeneration_failed_when_generator_registered_but_stale(tmp_path):
    repo = _seeded_repo(tmp_path)
    _change_sr(repo)
    # A generator is registered but the artifact is still stale (it did not
    # converge / was not re-run) -> REGENERATION_FAILED, not REFRESH_BLOCKED.
    register_generator("explainer", lambda root, ref: False, version="1")
    findings = health.freshness_health(repo)
    assert ("REGENERATION_FAILED", "explainer:NAV-PREEMPTION.md") in _codes(findings)
    assert not any(f.code == "REFRESH_BLOCKED" and f.subject == "explainer:NAV-PREEMPTION.md" for f in findings)


def test_closure_unresolved_when_slice_stale(tmp_path):
    repo = _seeded_repo(tmp_path)
    _change_code(repo)
    findings = health.freshness_health(repo)
    assert ("CLOSURE_UNRESOLVED", "feat:FEAT-NAV-017") in _codes(findings)


def test_healthy_repo_has_no_freshness_findings(tmp_path):
    repo = _seeded_repo(tmp_path)
    findings = health.freshness_health(repo)
    assert findings == []


def test_query_health_includes_freshness_findings(tmp_path):
    repo = _seeded_repo(tmp_path)
    _change_code(repo)
    payload = health.query_health(repo)
    assert "freshness_findings" in payload
    assert any(f["code"] == "EVIDENCE_STALE" for f in payload["freshness_findings"])


def test_freshness_health_is_deterministic(tmp_path):
    repo = _seeded_repo(tmp_path)
    _change_sr(repo)
    first = _codes(health.freshness_health(repo))
    second = _codes(health.freshness_health(repo))
    assert first == second
