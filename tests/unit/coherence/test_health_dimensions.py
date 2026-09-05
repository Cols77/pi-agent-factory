"""The eleven-dimension health vector (spec §6, narrowed by spec §13
amendment row 2) -- Increment 5 Task 6.

`compile_health_dimensions` composes existing loaders/projections only
(`vcycle_health`, `freshness_health`, `find_gaps`, `compile_obligations`,
`load_goals`, `load_nonconformances`, `load_runs`) into eleven independently
countable dimensions; it never forks a parser or recomputes what those
loaders already derive.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence.navigate import health
from tests.unit.freshness.test_deps import _code, _run_with_deps

pytestmark = pytest.mark.unit


# -- fixture helpers (main 11-dimension repo) --------------------------------


def _write_sr(root: Path, sr_id: str, *, profile: str | None = None) -> None:
    (root / "requirements").mkdir(parents=True, exist_ok=True)
    profile_line = f"profile: {profile}\n" if profile else ""
    (root / "requirements" / f"{sr_id}.md").write_text(
        f"---\nid: {sr_id}\ntitle: t\nstatement: s\ndomain: d\n{profile_line}---\nbody\n",
        encoding="utf-8",
    )


def _write_feature(root: Path, feat_id: str, sr_ids: list[str]) -> None:
    (root / "docs" / "features").mkdir(parents=True, exist_ok=True)
    reqs = ", ".join(sr_ids)
    (root / "docs" / "features" / f"{feat_id}.md").write_text(
        f"---\nid: {feat_id}\ntitle: t\nrequirements: [{reqs}]\n---\nbody\n",
        encoding="utf-8",
    )


def _write_validation_report(root: Path, passing_ids: list[str]) -> None:
    (root / "validation").mkdir(parents=True, exist_ok=True)
    entries = [{"id": sid, "passed": True, "stale": False} for sid in passing_ids]
    (root / "validation" / "validation-report.json").write_text(
        json.dumps({"provenance": {"recorded_by": "harness", "recorded_at": "2026-01-01T00:00:00Z", "command": "coherence-measurement run"}, "requirements": entries}),
        encoding="utf-8",
    )


def _write_sr_with_acceptance(root: Path, sr_id: str, acceptance_yaml: str) -> None:
    (root / "requirements").mkdir(parents=True, exist_ok=True)
    (root / "requirements" / f"{sr_id}.md").write_text(
        f"---\nid: {sr_id}\ntitle: t\nstatement: s\ndomain: d\n{acceptance_yaml}---\nbody\n",
        encoding="utf-8",
    )


def _write_nc(root: Path, nc_id: str, *, status: str = "open") -> None:
    (root / "docs" / "nonconformances").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "nonconformances" / f"{nc_id}.md").write_text(
        f"---\nid: {nc_id}\ntitle: t\nstatus: {status}\n---\nbody\n",
        encoding="utf-8",
    )


def _seed_main_repo(root: Path) -> Path:
    """One passing SR, one SR with missing validation, one blocking
    high-assurance SR, one feature containing an SR, one feature containing
    none, and one open NC-* record (per the Task 6 brief's Step 1)."""
    _write_sr(root, "SR-101")  # prototype, passing validation recorded below
    _write_sr(root, "SR-102")  # prototype, no validation recorded -> open
    _write_sr(root, "SR-103", profile="high_assurance")  # blocking, open
    _write_feature(root, "FEAT-001", ["SR-101"])
    _write_feature(root, "FEAT-002", [])
    _write_validation_report(root, ["SR-101"])
    _write_nc(root, "NC-0001")
    return root


# -- Dimension order / count --------------------------------------------------


def test_compile_health_dimensions_returns_eleven_dimensions_in_fixed_order(tmp_path):
    _seed_main_repo(tmp_path)
    dims = health.compile_health_dimensions(tmp_path)
    assert [d.name for d in dims] == [
        "requirement_quality",
        "decomposition_allocation",
        "implementation_trace",
        "verification_strategy",
        "executed_evidence",
        "validation_scenarios",
        "evidence_freshness",
        "suspect_relationships",
        "nonconformance_closure",
        "deferrals_waivers",
        "human_review",
    ]
    assert len(dims) == 11


# -- Dimension 1: requirement_quality (NC-B first half) ---------------------
# An SR counts only when it carries at least one acceptance criterion with a
# *resolvable* verification binding: test_marker/harness resolve only when
# `ref` exists on disk relative to root; manual resolves as-is (its `reason`
# is guaranteed nonblank at parse time). Whether a `@pytest.mark.sr` decorator
# actually appears at that ref is a stricter, separate gate (task T-5) --
# deliberately not checked here.


def test_requirement_quality_sr_without_acceptance_does_not_count(tmp_path):
    _write_sr(tmp_path, "SR-301")
    dims = {d.name: d for d in health.compile_health_dimensions(tmp_path)}
    rq = dims["requirement_quality"]
    assert (rq.satisfied, rq.expected, rq.exempt) == (0, 1, 0)


def test_requirement_quality_test_marker_with_missing_ref_does_not_count(tmp_path):
    yaml = """acceptance:
  - id: AC-1
    criterion: "c"
    verification:
      kind: test_marker
      ref: "tests/does/not/exist.py"
"""
    _write_sr_with_acceptance(tmp_path, "SR-301", yaml)
    dims = {d.name: d for d in health.compile_health_dimensions(tmp_path)}
    rq = dims["requirement_quality"]
    assert (rq.satisfied, rq.expected) == (0, 1)


def test_requirement_quality_test_marker_with_existing_ref_counts(tmp_path):
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests" / "test_example.py").write_text(
        "def test_x():\n    pass\n", encoding="utf-8",
    )
    yaml = """acceptance:
  - id: AC-1
    criterion: "c"
    verification:
      kind: test_marker
      ref: "tests/test_example.py"
"""
    _write_sr_with_acceptance(tmp_path, "SR-301", yaml)
    dims = {d.name: d for d in health.compile_health_dimensions(tmp_path)}
    rq = dims["requirement_quality"]
    assert (rq.satisfied, rq.expected) == (1, 1)


def test_requirement_quality_test_marker_with_existing_directory_does_not_count(tmp_path):
    (tmp_path / "tests" / "test_example").mkdir(parents=True, exist_ok=True)
    yaml = """acceptance:
  - id: AC-1
    criterion: "c"
    verification:
      kind: test_marker
      ref: "tests/test_example"
"""
    _write_sr_with_acceptance(tmp_path, "SR-301", yaml)
    dims = {d.name: d for d in health.compile_health_dimensions(tmp_path)}
    rq = dims["requirement_quality"]
    assert (rq.satisfied, rq.expected) == (0, 1)


def test_requirement_quality_test_marker_with_non_python_file_does_not_count(tmp_path):
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests" / "test_example.txt").write_text("not a test file\n", encoding="utf-8")
    yaml = """acceptance:
  - id: AC-1
    criterion: "c"
    verification:
      kind: test_marker
      ref: "tests/test_example.txt"
"""
    _write_sr_with_acceptance(tmp_path, "SR-301", yaml)
    dims = {d.name: d for d in health.compile_health_dimensions(tmp_path)}
    rq = dims["requirement_quality"]
    assert (rq.satisfied, rq.expected) == (0, 1)


def test_requirement_quality_absolute_ref_outside_root_does_not_count(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
    outside.write_text("def test_x():\n    pass\n", encoding="utf-8")
    yaml = f"""acceptance:
  - id: AC-1
    criterion: "c"
    verification:
      kind: test_marker
      ref: '{outside.as_posix()}'
"""
    _write_sr_with_acceptance(tmp_path, "SR-301", yaml)
    dims = {d.name: d for d in health.compile_health_dimensions(tmp_path)}
    rq = dims["requirement_quality"]
    assert (rq.satisfied, rq.expected) == (0, 1)


def test_requirement_quality_traversal_ref_outside_root_does_not_count(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
    outside.write_text("def test_x():\n    pass\n", encoding="utf-8")
    yaml = f"""acceptance:
  - id: AC-1
    criterion: "c"
    verification:
      kind: test_marker
      ref: '../{outside.name}'
"""
    _write_sr_with_acceptance(tmp_path, "SR-301", yaml)
    dims = {d.name: d for d in health.compile_health_dimensions(tmp_path)}
    rq = dims["requirement_quality"]
    assert (rq.satisfied, rq.expected) == (0, 1)


def test_requirement_quality_symlink_ref_outside_root_does_not_count(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
    outside.write_text("def test_x():\n    pass\n", encoding="utf-8")
    linked = tmp_path / "linked-test.py"
    try:
        linked.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    yaml = """acceptance:
  - id: AC-1
    criterion: "c"
    verification:
      kind: test_marker
      ref: "linked-test.py"
"""
    _write_sr_with_acceptance(tmp_path, "SR-301", yaml)
    dims = {d.name: d for d in health.compile_health_dimensions(tmp_path)}
    rq = dims["requirement_quality"]
    assert (rq.satisfied, rq.expected) == (0, 1)


def test_requirement_quality_harness_ref_resolution_mirrors_test_marker(tmp_path):
    (tmp_path / "sim-testbench").mkdir(parents=True, exist_ok=True)
    yaml = """acceptance:
  - id: AC-1
    criterion: "c"
    verification:
      kind: harness
      ref: "sim-testbench"
"""
    _write_sr_with_acceptance(tmp_path, "SR-301", yaml)
    dims = {d.name: d for d in health.compile_health_dimensions(tmp_path)}
    rq = dims["requirement_quality"]
    assert (rq.satisfied, rq.expected) == (1, 1)


def test_requirement_quality_manual_criterion_counts(tmp_path):
    yaml = """acceptance:
  - id: AC-1
    criterion: "c"
    verification:
      kind: manual
      reason: "no automated oracle exists for subjective UX quality"
"""
    _write_sr_with_acceptance(tmp_path, "SR-301", yaml)
    dims = {d.name: d for d in health.compile_health_dimensions(tmp_path)}
    rq = dims["requirement_quality"]
    assert (rq.satisfied, rq.expected) == (1, 1)


def test_requirement_quality_counts_when_at_least_one_of_several_criteria_resolves(tmp_path):
    yaml = """acceptance:
  - id: AC-1
    criterion: "c1"
    verification:
      kind: test_marker
      ref: "tests/does/not/exist.py"
  - id: AC-2
    criterion: "c2"
    verification:
      kind: manual
      reason: "reviewed by hand"
"""
    _write_sr_with_acceptance(tmp_path, "SR-301", yaml)
    dims = {d.name: d for d in health.compile_health_dimensions(tmp_path)}
    rq = dims["requirement_quality"]
    assert (rq.satisfied, rq.expected) == (1, 1)


def test_requirement_quality_duplicate_register_ids_do_not_satisfy_affected_sr_nodes(tmp_path):
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests" / "test_example.py").write_text(
        "def test_x():\n    pass\n", encoding="utf-8",
    )
    yaml = """acceptance:
  - id: AC-1
    criterion: "c"
    verification:
      kind: test_marker
      ref: "tests/test_example.py"
"""
    _write_sr_with_acceptance(tmp_path, "SR-301", yaml)
    original = (tmp_path / "requirements" / "SR-301.md").read_text(encoding="utf-8")
    (tmp_path / "requirements" / "SR-301-duplicate.md").write_text(
        original, encoding="utf-8",
    )

    dims = {d.name: d for d in health.compile_health_dimensions(tmp_path)}
    rq = dims["requirement_quality"]
    assert (rq.satisfied, rq.expected) == (0, 2)


# -- Dimensions 4/5: the shared verification_result obligation universe -----


@pytest.mark.sr("SR-009")
def test_verification_strategy_and_executed_evidence_share_the_active_obligation_denominator(
    tmp_path,
):
    _seed_main_repo(tmp_path)
    dims = {d.name: d for d in health.compile_health_dimensions(tmp_path)}
    vs = dims["verification_strategy"]
    ee = dims["executed_evidence"]

    # 3 SRs -> 3 compiled verification_result obligations, all required or
    # blocking (SR-101/SR-102 required, SR-103 blocking), none waived: the
    # compiler never emits advisory/not_applicable for this obligation kind
    # today, and this fixture holds no waiver mechanism, so exempt is 0.
    assert (vs.expected, vs.exempt) == (3, 0)
    assert (ee.expected, ee.exempt) == (3, 0)
    # Every verification_result obligation carries a nonblank resolve_cmd
    # (the compiler always names a re-run command), so all 3 count toward
    # verification_strategy regardless of pass/fail state.
    assert vs.satisfied == 3
    # Only SR-101 has a passing, non-stale recorded validation -> satisfied.
    assert ee.satisfied == 1
    # Both dimensions share one obligation-derived denominator -- never
    # len(sr_nodes) directly (would happen to coincide here at 3, but the
    # implementation computes it from the compiled obligation list, not the
    # SR node count).
    assert vs.expected == ee.expected == len(
        [n for n in health.trace_model.load_nodes(tmp_path) if n.kind == "sr"]
    )


def test_verification_result_obligation_excludes_the_project_scope_ci_gate(tmp_path):
    # A passing project-wide CI gate must never substitute for per-SR
    # verification evidence: dims 4/5 only ever see kind == "verification_result"
    # obligations, never the project-scope ci_verification obligation that
    # compile_obligations also compiles for every sr: scope.
    from coherence.policy.compiler import compile_obligations

    _seed_main_repo(tmp_path)
    nodes = health.trace_model.load_nodes(tmp_path)
    edges = health.trace_model.extract_edges(tmp_path, nodes)
    kinds = {
        o.kind
        for n in nodes
        if n.kind == "sr"
        for o in compile_obligations(tmp_path, f"sr:{n.id}", nodes=nodes, edges=edges)
    }
    # Task 6 addendum lands test_marker on the sr: branch alongside
    # verification_result and human_review. None of these is the project-scope
    # ci_verification obligation -- that one is still compiled (every sr: scope
    # gets it), but is never what dims 4/5 read.
    assert kinds == {"ci_verification", "verification_result", "human_review", "test_marker"}
    dims = {d.name: d for d in health.compile_health_dimensions(tmp_path)}
    # 3, not 6: ci_verification obligations are compiled but never counted here.
    assert dims["verification_strategy"].expected == 3


# -- Dimension 9: nonconformance_closure -------------------------------------


def test_nonconformance_closure_counts_the_one_open_nc_record(tmp_path):
    _seed_main_repo(tmp_path)
    dims = {d.name: d for d in health.compile_health_dimensions(tmp_path)}
    nc = dims["nonconformance_closure"]
    assert (nc.satisfied, nc.expected) == (0, 1)


# -- Dimension 11: human_review ----------------------------------------------


def test_human_review_counts_every_sr_required_or_blocking_alike(tmp_path):
    # SR-059/AC-1: the compiler no longer emits not_applicable for this
    # obligation kind under any profile (a profile-independent floor -- at
    # least "required" outside high_assurance, "blocking" under it), so all
    # three fixture SRs now participate: SR-101/SR-102 (prototype, required)
    # and SR-103 (high_assurance, blocking). Product decision (2026-09-05,
    # policy/compiler.py's _human_review_obligation): outside high_assurance,
    # silence satisfies -- no reviewer needs to have recorded anything for the
    # obligation to read as satisfied. So SR-101/SR-102 (prototype, no
    # decision) are now satisfied; SR-103 (high_assurance, no decision) stays
    # open exactly as before -- satisfied is 2, expected is 3.
    _seed_main_repo(tmp_path)
    dims = {d.name: d for d in health.compile_health_dimensions(tmp_path)}
    hr = dims["human_review"]
    assert (hr.satisfied, hr.expected, hr.exempt) == (2, 3, 0)


# -- query_health wiring -------------------------------------------------


def test_query_health_exposes_dimensions_json_shaped_and_keeps_percent(tmp_path):
    _seed_main_repo(tmp_path)
    payload = health.query_health(tmp_path)

    assert "dimensions" in payload
    by_name = {d["name"]: d for d in payload["dimensions"]}
    assert set(by_name) == {
        "requirement_quality", "decomposition_allocation", "implementation_trace",
        "verification_strategy", "executed_evidence", "validation_scenarios",
        "evidence_freshness", "suspect_relationships", "nonconformance_closure",
        "deferrals_waivers", "human_review",
    }
    for entry in payload["dimensions"]:
        assert set(entry) == {"name", "satisfied", "expected", "exempt"}
    assert by_name["verification_strategy"] == {
        "name": "verification_strategy", "satisfied": 3, "expected": 3, "exempt": 0,
    }
    assert by_name["executed_evidence"] == {
        "name": "executed_evidence", "satisfied": 1, "expected": 3, "exempt": 0,
    }
    assert by_name["nonconformance_closure"] == {
        "name": "nonconformance_closure", "satisfied": 0, "expected": 1, "exempt": 0,
    }
    assert by_name["human_review"] == {
        # SR-059/AC-1: expected is 3, not 1 -- see
        # test_human_review_counts_every_sr_required_or_blocking_alike. satisfied
        # is 2: silence satisfies outside high_assurance (2026-09-05 product
        # decision), so only the fixture's one high_assurance SR stays open.
        "name": "human_review", "satisfied": 2, "expected": 3, "exempt": 0,
    }
    # Only demoted (Task 7 stops leading with it), never removed.
    assert "percent" in payload["health"]


# -- Dimension 7: evidence_freshness (second fixture repo) ------------------


def test_evidence_freshness_universe_is_the_trackable_runs_not_an_sr_intersection(tmp_path):
    # Two simulation runs, no explainers/diagrams: one whose recorded
    # dependency fingerprint still matches its source (fresh, no finding),
    # one whose recorded fingerprint no longer matches (EVIDENCE_STALE). SR
    # ids never appear as a freshness finding's subject, so the universe must
    # be reconstructed from the trackable-artifact collections themselves
    # (runs/explainers/diag nodes), not a bare-SR-id intersection.
    _code(tmp_path, "src/fresh.py", "value = 1\n")
    _code(tmp_path, "src/stale.py", "value = 1\n")
    _run_with_deps(tmp_path, "RUN-FRESH", commit=None, files=["src/fresh.py"])
    _run_with_deps(tmp_path, "RUN-STALE", commit=None, files=["src/stale.py"])
    # Change the stale run's recorded dependency after the manifest captured
    # its digest -- the fresh run's dependency is left untouched.
    _code(tmp_path, "src/stale.py", "value = 2\n")

    dims = {d.name: d for d in health.compile_health_dimensions(tmp_path)}
    freshness = dims["evidence_freshness"]
    assert (freshness.satisfied, freshness.expected) == (1, 2)


# -- Call-count regression: query_health must still load the trace graph -----
# -- exactly once, not once per SR, now that compile_health_dimensions is  --
# -- wired in (Task 6's own must-not-reintroduce regression).              --


def test_query_health_still_loads_trace_nodes_once_with_dimensions_wired_in(
    tmp_path, monkeypatch,
):
    for sr_id in ("SR-201", "SR-202", "SR-203"):
        _write_sr(tmp_path, sr_id)

    real_load_nodes = health.trace_model.load_nodes
    calls = 0

    def counted_load_nodes(root):
        nonlocal calls
        calls += 1
        return real_load_nodes(root)

    monkeypatch.setattr(health.trace_model, "load_nodes", counted_load_nodes)

    payload = health.query_health(tmp_path)

    assert "dimensions" in payload
    assert calls == 1
