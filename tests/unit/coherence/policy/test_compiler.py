import json
import subprocess
import sys
from pathlib import Path

import pytest

from coherence.policy.compiler import (
    UnsupportedScopeError,
    compile_obligations,
    resolve_profile,
)
from substrate.policy.vocabulary import UncompiledPresetError

pytestmark = pytest.mark.unit


def _seed_gates(root: Path) -> None:
    # {python} deliberately included: every real gate command in
    # .factory/factory.yaml uses it (verified against tests/integration/
    # orchestrator/test_resume_run.py's own fixture), and this is exactly
    # what proves _ci_verification_obligation reuses backends.py's real
    # substitution instead of joining raw step.cmd strings.
    (root / ".factory").mkdir(exist_ok=True)
    (root / ".factory" / "factory.yaml").write_text(
        "gates:\n"
        "  unit:\n"
        "  - { cmd: '{python} -m pytest -m unit -q' }\n"
        "  sim:\n"
        "  - { cmd: '{python} -m pytest -m sim -q' }\n"
        "  full:\n"
        "  - { cmd: '{python} -m pytest -m unit -q' }\n",
        encoding="utf-8",
    )


@pytest.mark.sr("SR-008")
def test_resolve_profile_project_default(tmp_path):
    assert resolve_profile(tmp_path, "project") == "prototype"


@pytest.mark.sr("SR-008")
def test_resolve_profile_project_scope_uses_project_default_explicitly(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text(
        "profile: high_assurance\n", encoding="utf-8"
    )
    assert resolve_profile(tmp_path, "project") == "high_assurance"


def test_resolve_profile_unknown_artifact_scope_fails_closed(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text(
        "profile: high_assurance\n", encoding="utf-8"
    )
    with pytest.raises(UnsupportedScopeError):
        resolve_profile(tmp_path, "sr:SR-404")


def test_resolve_profile_unsupported_artifact_scope_fails_closed(tmp_path):
    with pytest.raises(UnsupportedScopeError):
        resolve_profile(tmp_path, "file:src/not-a-trace-artifact.py")


@pytest.mark.sr("SR-008")
def test_resolve_profile_rejects_uncompiled_preset(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text("profile: exploration\n", encoding="utf-8")
    with pytest.raises(UncompiledPresetError):
        resolve_profile(tmp_path, "project")


@pytest.mark.sr("SR-008")
def test_resolve_profile_rejects_uncompiled_preset_product(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text("profile: product\n", encoding="utf-8")
    with pytest.raises(UncompiledPresetError):
        resolve_profile(tmp_path, "project")


def test_compile_obligations_ci_verification_substitutes_python_like_backends_does(tmp_path):
    _seed_gates(tmp_path)
    obligations = compile_obligations(tmp_path, "project")
    ci = next(o for o in obligations if o.kind == "ci_verification")
    assert ci.requiredness == "blocking"
    assert ci.source_policy == "prototype"
    # No literal "{python}" survives -- backends._target_python/_quote_for_shell
    # already ran, producing a real interpreter path/token in its place.
    assert all("{python}" not in command for command in (ci.resolve_cmd or ()))
    assert any("-m pytest -m unit -q" in command for command in (ci.resolve_cmd or ()))


def test_compile_obligations_preserves_configured_order_and_duplicates(tmp_path):
    _seed_gates(tmp_path)
    obligations = compile_obligations(tmp_path, "project")
    ci = next(o for o in obligations if o.kind == "ci_verification")

    assert ci.resolve_cmd is not None
    assert len(ci.resolve_cmd) == 3
    assert ci.resolve_cmd[0].endswith("-m pytest -m unit -q")
    assert ci.resolve_cmd[1].endswith("-m pytest -m sim -q")
    assert ci.resolve_cmd[2] == ci.resolve_cmd[0]


def test_compile_obligations_task_justification_for_task_scope(tmp_path):
    # task_justification lands here (not deferred to Increment 6B) because it
    # is a direct sibling of this same increment's typed-justification work
    # (Task 2) -- Increment 4's verification_result and Increment 6's
    # human_review obligation kinds are added by those increments' own plans,
    # since each is grounded in that increment's own deliverable.
    _seed_gates(tmp_path)
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-900.md").write_text(
        "---\nid: T-900\ntitle: t\nstatus: todo\ndod:\n- 'd'\n---\nbody\n", encoding="utf-8",
    )
    obligations = compile_obligations(tmp_path, "task:T-900")
    tj = next(o for o in obligations if o.kind == "task_justification")
    assert tj.requiredness == "advisory"  # prototype is the project default here
    assert tj.state == "open"  # T-900 has no justification at all


@pytest.mark.sr("SR-008")
def test_resolve_profile_honors_preloaded_nodes_and_edges(tmp_path, monkeypatch):
    # Increment 5's per-SR health loop calls compile_obligations(root,
    # f"sr:{n.id}", nodes=nodes, edges=edges) inside a loop over every SR --
    # it must never trigger a fresh trace_model.load_nodes per call.
    from coherence.trace import model as trace_model

    (tmp_path / "docs" / "features").mkdir(parents=True)
    (tmp_path / "docs" / "features" / "FEAT-001.md").write_text(
        "---\nid: FEAT-001\ntitle: f\nprofile: high_assurance\nrequirements: [SR-001]\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: t\nstatement: s\ndomain: d\n"
        "binding:\n  harness: h\n  experiment: e\n  metric: m\n  assert: '>= 0.9'\n---\n",
        encoding="utf-8",
    )
    nodes = trace_model.load_nodes(tmp_path)
    edges = trace_model.extract_edges(tmp_path, nodes)

    def _boom(*_a, **_k):
        raise AssertionError("must not reload nodes when already supplied")

    monkeypatch.setattr(trace_model, "load_nodes", _boom)
    assert resolve_profile(tmp_path, "sr:SR-001", nodes=nodes, edges=edges) == "high_assurance"


@pytest.mark.sr("SR-008")
def test_resolve_profile_artifact_own_override_wins_over_feature_inheritance(tmp_path):
    # SR-500 declares its own `profile:` override (high_assurance) while its
    # owning feature declares a DIFFERENT one (prototype) -- artifact/
    # requirement scope must win over feature/bundle scope (the guide's
    # precedence order), never the other way around.
    (tmp_path / "docs" / "features").mkdir(parents=True)
    (tmp_path / "docs" / "features" / "FEAT-500.md").write_text(
        "---\nid: FEAT-500\ntitle: f\nprofile: prototype\nrequirements: [SR-500]\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-500.md").write_text(
        "---\nid: SR-500\ntitle: t\nstatement: s\ndomain: d\nprofile: high_assurance\n---\n",
        encoding="utf-8",
    )
    assert resolve_profile(tmp_path, "sr:SR-500") == "high_assurance"


def test_compile_obligations_verification_result_high_assurance_no_validation_is_blocking_open(
    tmp_path,
):
    # An SR with a declared harness but no recorded validation at all: under
    # high_assurance this must block, and stay open (never satisfied by
    # absence of evidence -- spec's "missing evidence is unknown, never
    # passing" invariant).
    (tmp_path / "docs" / "features").mkdir(parents=True)
    (tmp_path / "docs" / "features" / "FEAT-001.md").write_text(
        "---\nid: FEAT-001\ntitle: f\nprofile: high_assurance\nrequirements: [SR-001]\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: t\nstatement: s\ndomain: d\n"
        "binding:\n  harness: h\n  experiment: e\n  metric: m\n  assert: '>= 0.9'\n---\n",
        encoding="utf-8",
    )
    obligations = compile_obligations(tmp_path, "sr:SR-001")
    vr = next(o for o in obligations if o.kind == "verification_result")
    assert vr.requiredness == "blocking"
    assert vr.state == "open"


def test_compile_obligations_verification_result_prototype_pass_nonstale_is_satisfied(
    tmp_path,
):
    # prototype's contract is pass/fail only -- no harness-declared check --
    # so a passing, non-stale validation entry alone satisfies it, and its
    # requiredness must be "required", never "blocking" (D16: only
    # high_assurance blocks on this kind).
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-002.md").write_text(
        "---\nid: SR-002\ntitle: t\nstatement: s\ndomain: d\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "validation").mkdir()
    (tmp_path / "validation" / "validation-report.json").write_text(
        json.dumps(
            {
                "provenance": {"recorded_by": "harness", "recorded_at": "2026-01-01T00:00:00Z", "command": "coherence-measurement run"},
                "requirements": [{"id": "SR-002", "passed": True, "stale": False}],
            }
        ),
        encoding="utf-8",
    )
    obligations = compile_obligations(tmp_path, "sr:SR-002")
    vr = next(o for o in obligations if o.kind == "verification_result")
    assert vr.state == "satisfied"
    assert vr.requiredness == "required"


def test_compile_obligations_verification_result_high_assurance_missing_harness_stays_open(
    tmp_path,
):
    # Same passing, non-stale validation entry as above, but under
    # high_assurance with no declared harness: the extra high_assurance check
    # must still hold this open, naming the missing harness in the reason.
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-003.md").write_text(
        "---\nid: SR-003\ntitle: t\nstatement: s\ndomain: d\nprofile: high_assurance\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "validation").mkdir()
    (tmp_path / "validation" / "validation-report.json").write_text(
        json.dumps(
            {
                "provenance": {"recorded_by": "harness", "recorded_at": "2026-01-01T00:00:00Z", "command": "coherence-measurement run"},
                "requirements": [{"id": "SR-003", "passed": True, "stale": False}],
            }
        ),
        encoding="utf-8",
    )
    obligations = compile_obligations(tmp_path, "sr:SR-003")
    vr = next(o for o in obligations if o.kind == "verification_result")
    assert vr.requiredness == "blocking"
    assert vr.state == "open"
    assert "harness" in vr.reason


def test_compile_obligations_human_review_high_assurance_no_review_identity_is_blocking_open(
    tmp_path,
):
    # An SR under high_assurance with no human-review identity evidence at
    # all: D16 human_review is blocking here and stays open -- absence of a
    # recorded human reviewer is "unknown", never treated as satisfied.
    (tmp_path / "docs" / "features").mkdir(parents=True)
    (tmp_path / "docs" / "features" / "FEAT-001.md").write_text(
        "---\nid: FEAT-001\ntitle: f\nprofile: high_assurance\nrequirements: [SR-001]\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: t\nstatement: s\ndomain: d\n"
        "binding:\n  harness: h\n  experiment: e\n  metric: m\n  assert: '>= 0.9'\n---\n",
        encoding="utf-8",
    )
    obligations = compile_obligations(tmp_path, "sr:SR-001")
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.requiredness == "blocking"
    assert hr.state == "open"


def test_compile_obligations_human_review_under_prototype_is_not_applicable(tmp_path):
    # D16: human_review does not apply under prototype -- the obligation is
    # still compiled so CI/dimension-11 sees a real node, but non-blocking.
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-002.md").write_text(
        "---\nid: SR-002\ntitle: t\nstatement: s\ndomain: d\n---\n",
        encoding="utf-8",
    )
    obligations = compile_obligations(tmp_path, "sr:SR-002")  # project default: prototype
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.requiredness == "not_applicable"


# --------------------------------------------------------------------------
# Task 8a: human_review wired to a durable `review:<sr_id>` DecisionFile
# (R-7, agent half). I-01: the producer of work is never the sole authority
# that it is done -- these tests pin that a valid HUMAN `accept` decision
# (never authored here, always via tmp_path fixtures) is the only path to
# `satisfied`, and that every other case (missing, malformed, reject, defer,
# wrong item, wrong gate, wrong SR, or an `sr:` authoring-consent decision)
# stays open.
#
# Six of these tests (valid accept, missing decision, cross-SR mis-scoping,
# reject, defer, and a blank decided_by below) are also bound to
# SR-050/AC-3 via @pytest.mark.sr("SR-050"): they exhaustively exercise the
# narrowed criterion's "attributed, correctly-scoped human accept, fail-
# closed on everything else" contract.
# --------------------------------------------------------------------------


def _seed_high_assurance_sr(tmp_path: Path, sr_id: str, *, extra_ids: tuple[str, ...] = ()) -> None:
    (tmp_path / "docs" / "features").mkdir(parents=True, exist_ok=True)
    all_ids = ", ".join((sr_id, *extra_ids))
    (tmp_path / "docs" / "features" / "FEAT-001.md").write_text(
        "---\nid: FEAT-001\ntitle: f\nprofile: high_assurance\n"
        f"requirements: [{all_ids}]\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements").mkdir(exist_ok=True)
    (tmp_path / "requirements" / f"{sr_id}.md").write_text(
        f"---\nid: {sr_id}\ntitle: t\nstatement: s\ndomain: d\n"
        "binding:\n  harness: h\n  experiment: e\n  metric: m\n  assert: '>= 0.9'\n---\n",
        encoding="utf-8",
    )


def _write_review_decision(
    tmp_path: Path,
    sr_id: str,
    *,
    gate_id: str | None = None,
    item_id: str | None = None,
    artifact_ref: str | None = None,
    action: str = "accept",
    reason: str = "",
    review_after: str | None = None,
) -> Path:
    from coherence.gate.model import Decision, DecisionFile
    from coherence.gate.store import write_decision

    # NOTE: every call site here is a tmp_path fixture -- this simulates a
    # human decision for the test; it must never run against the repo's own
    # gate store.
    return write_decision(
        tmp_path,
        DecisionFile(
            gate_id=gate_id or f"review:{sr_id}",
            artifact_ref=artifact_ref or f"artifact:requirements/{sr_id}.md",
            decisions=(
                Decision(
                    item_id or f"review:{sr_id}",
                    action,
                    reason=reason,
                    review_after=review_after,
                    decided_by="reviewer@example.invalid",
                ),
            ),
            decided_at="2026-09-01T00:00:00Z",
            decided_by="reviewer@example.invalid",
        ),
    )


@pytest.mark.sr("SR-050")
def test_human_review_missing_decision_stays_open_under_high_assurance(tmp_path):
    _seed_high_assurance_sr(tmp_path, "SR-100")
    obligations = compile_obligations(tmp_path, "sr:SR-100")
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.state == "open"
    assert hr.requiredness == "blocking"


@pytest.mark.sr("SR-050")
def test_human_review_valid_accept_satisfies_only_that_sr(tmp_path):
    _seed_high_assurance_sr(tmp_path, "SR-101")
    _write_review_decision(tmp_path, "SR-101")

    obligations = compile_obligations(tmp_path, "sr:SR-101")
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.state == "satisfied"
    assert hr.requiredness == "blocking"


@pytest.mark.sr("SR-050")
def test_human_review_accept_for_one_sr_does_not_satisfy_another(tmp_path):
    _seed_high_assurance_sr(tmp_path, "SR-002", extra_ids=("SR-003",))
    (tmp_path / "requirements" / "SR-003.md").write_text(
        "---\nid: SR-003\ntitle: t\nstatement: s\ndomain: d\n---\n",
        encoding="utf-8",
    )
    _write_review_decision(tmp_path, "SR-002")

    obligations = compile_obligations(tmp_path, "sr:SR-003")
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.state == "open"


@pytest.mark.sr("SR-050")
def test_human_review_reject_leaves_obligation_open(tmp_path):
    _seed_high_assurance_sr(tmp_path, "SR-104")
    _write_review_decision(tmp_path, "SR-104", action="reject", reason="insufficient evidence")

    obligations = compile_obligations(tmp_path, "sr:SR-104")
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.state == "open"


@pytest.mark.sr("SR-050")
def test_human_review_defer_leaves_obligation_open(tmp_path):
    _seed_high_assurance_sr(tmp_path, "SR-105")
    _write_review_decision(
        tmp_path, "SR-105", action="defer", reason="needs more evidence",
        review_after="2026-12-01T00:00:00Z",
    )

    obligations = compile_obligations(tmp_path, "sr:SR-105")
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.state == "open"


def test_human_review_malformed_decision_file_stays_open(tmp_path):
    from coherence.gate.store import decision_path

    _seed_high_assurance_sr(tmp_path, "SR-106")
    path = decision_path(tmp_path, "review:SR-106")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")

    obligations = compile_obligations(tmp_path, "sr:SR-106")
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.state == "open"


def test_human_review_wrong_item_id_inside_file_stays_open(tmp_path):
    _seed_high_assurance_sr(tmp_path, "SR-107")
    _write_review_decision(tmp_path, "SR-107", item_id="review:SR-999")

    obligations = compile_obligations(tmp_path, "sr:SR-107")
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.state == "open"


def test_human_review_wrong_gate_id_inside_file_stays_open(tmp_path):
    import json as _json

    from coherence.gate.store import decision_path

    _seed_high_assurance_sr(tmp_path, "SR-108")
    path = decision_path(tmp_path, "review:SR-108")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _json.dumps(
            {
                "schema": 1,
                "gate_id": "review:SR-999",
                "artifact_ref": "artifact:requirements/SR-108.md",
                "decisions": [{"item_id": "review:SR-108", "action": "accept"}],
                "decided_at": "2026-09-01T00:00:00Z",
                "decided_by": "reviewer@example.invalid",
            }
        ),
        encoding="utf-8",
    )

    obligations = compile_obligations(tmp_path, "sr:SR-108")
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.state == "open"


def test_human_review_authoring_consent_decision_does_not_satisfy(tmp_path):
    from coherence.gate.model import Decision, DecisionFile
    from coherence.gate.store import write_decision

    _seed_high_assurance_sr(tmp_path, "SR-109")
    write_decision(
        tmp_path,
        DecisionFile(
            gate_id="sr:SR-109",
            artifact_ref="artifact:requirements/SR-109.md",
            decisions=(Decision("sr:SR-109", "accept"),),
            decided_at="2026-09-01T00:00:00Z",
            decided_by="human@example.invalid",
        ),
    )

    obligations = compile_obligations(tmp_path, "sr:SR-109")
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.state == "open"


def test_human_review_prototype_accept_is_satisfied_but_not_applicable(tmp_path):
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-110.md").write_text(
        "---\nid: SR-110\ntitle: t\nstatement: s\ndomain: d\n---\n",
        encoding="utf-8",
    )
    _write_review_decision(tmp_path, "SR-110")

    obligations = compile_obligations(tmp_path, "sr:SR-110")  # project default: prototype
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.requiredness == "not_applicable"
    assert hr.state == "satisfied"


# --------------------------------------------------------------------------
# Task 6 addendum: compiled test_marker obligation (profile-aware closure)
# --------------------------------------------------------------------------


def _seed_test_marker_trace(tmp_path, sr_id, *, experiment, profile=None) -> None:
    (tmp_path / "requirements").mkdir(exist_ok=True)
    profile_line = f"profile: {profile}\n" if profile else ""
    (tmp_path / "requirements" / f"{sr_id}.md").write_text(
        "---\n"
        f"id: {sr_id}\ntitle: t\nstatement: s\ndomain: d\n"
        f"{profile_line}"
        "binding:\n"
        f"  experiment: {experiment}\n"
        "  metric: m\n"
        "  assert: '>= 0.9'\n"
        "  harness: h\n"
        "---\n",
        encoding="utf-8",
    )


def test_compile_obligations_test_marker_required_under_default_prototype(tmp_path):
    # The project default (prototype) compiles the test_marker obligation with
    # requiredness "required", and a bound experiment test file missing the
    # marker stays open -- this is exactly the value the closure CHECK reads.
    experiment = "tests/test_sr_req.py"
    exp = tmp_path / experiment
    exp.parent.mkdir(parents=True, exist_ok=True)
    exp.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    _seed_test_marker_trace(tmp_path, "SR-011", experiment=experiment)
    obligations = compile_obligations(tmp_path, "sr:SR-011")  # project default: prototype
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.requiredness == "required"
    assert tm.state == "open"


def test_compile_obligations_test_marker_blocking_under_high_assurance_override(tmp_path):
    experiment = "tests/test_sr_high_ob.py"
    exp = tmp_path / experiment
    exp.parent.mkdir(parents=True, exist_ok=True)
    exp.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    _seed_test_marker_trace(tmp_path, "SR-012", experiment=experiment, profile="high_assurance")
    obligations = compile_obligations(tmp_path, "sr:SR-012")
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.requiredness == "blocking"
    assert tm.state == "open"


def test_compile_obligations_test_marker_satisfied_when_marker_present(tmp_path):
    experiment = "tests/test_sr_sat.py"
    exp = tmp_path / experiment
    exp.parent.mkdir(parents=True, exist_ok=True)
    exp.write_text(
        '@pytest.mark.sr("SR-013")\n'
        "def test_x():\n"
        "    assert True\n",
        encoding="utf-8",
    )
    _seed_test_marker_trace(tmp_path, "SR-013", experiment=experiment)
    obligations = compile_obligations(tmp_path, "sr:SR-013")  # project default: prototype
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.requiredness == "required"
    assert tm.state == "satisfied"


def test_compile_obligations_test_marker_not_applicable_for_command_experiment(tmp_path):
    # A command / non-file experiment is a separate configuration finding (Task
    # 3), NOT this obligation's concern: test_marker is not_applicable for it.
    _seed_test_marker_trace(tmp_path, "SR-014", experiment="patrol")
    obligations = compile_obligations(tmp_path, "sr:SR-014")
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.requiredness == "not_applicable"
    assert tm.state == "satisfied"


# --------------------------------------------------------------------------
# Task 5 addendum: test_marker obligation resolves through acceptance criteria
# for an SR that carries no `binding` (the proposed/unbound state).
# --------------------------------------------------------------------------


def _seed_unbound_sr_with_acceptance(tmp_path, sr_id, *, acceptance_yaml, profile=None):
    (tmp_path / "requirements").mkdir(exist_ok=True)
    profile_line = f"profile: {profile}\n" if profile else ""
    (tmp_path / "requirements" / f"{sr_id}.md").write_text(
        "---\n"
        f"id: {sr_id}\ntitle: t\nstatement: s\ndomain: d\n"
        f"{profile_line}"
        f"{acceptance_yaml}"
        "---\n",
        encoding="utf-8",
    )


def test_compile_obligations_test_marker_via_acceptance_satisfied(tmp_path):
    # An unbound SR (no `binding:`) with one `test_marker` acceptance
    # criterion whose ref file carries a matching @pytest.mark.sr marker
    # must compile a satisfied test_marker obligation.
    experiment = "tests/test_ac_sat.py"
    exp = tmp_path / experiment
    exp.parent.mkdir(parents=True, exist_ok=True)
    exp.write_text(
        '@pytest.mark.sr("SR-020")\ndef test_x():\n    assert True\n', encoding="utf-8",
    )
    _seed_unbound_sr_with_acceptance(
        tmp_path,
        "SR-020",
        acceptance_yaml=(
            "acceptance:\n"
            "  - id: AC-1\n"
            '    criterion: "c"\n'
            "    verification:\n"
            "      kind: test_marker\n"
            f"      ref: \"{experiment}\"\n"
        ),
    )
    obligations = compile_obligations(tmp_path, "sr:SR-020")
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.requiredness == "required"  # project default: prototype
    assert tm.state == "satisfied"


def test_compile_obligations_test_marker_rejects_duplicate_registered_ids(tmp_path):
    # Conflicting duplicate SR declarations must not let the valid acceptance
    # source hide the invalid one: duplicate registration is ambiguous.
    good = "tests/test_ac_duplicate_good.py"
    bad = "tests/test_ac_duplicate_bad.py"
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / good).write_text(
        '@pytest.mark.sr("SR-DUP")\ndef test_good():\n    assert True\n', encoding="utf-8"
    )
    (tmp_path / bad).write_text("def test_bad():\n    assert True\n", encoding="utf-8")
    duplicate_yaml = (
        "---\n"
        "id: SR-DUP\ntitle: t\nstatement: s\ndomain: d\n"
        "acceptance:\n"
        "  - id: AC-1\n"
        '    criterion: "c"\n'
        "    verification:\n"
        "      kind: test_marker\n"
    )
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-DUP-a.md").write_text(
        f"{duplicate_yaml}      ref: \"{bad}\"\n---\n", encoding="utf-8"
    )
    (tmp_path / "requirements" / "SR-DUP-b.md").write_text(
        f"{duplicate_yaml}      ref: \"{good}\"\n---\n", encoding="utf-8"
    )

    obligations = compile_obligations(tmp_path, "sr:SR-DUP")
    tm = next(o for o in obligations if o.kind == "test_marker")

    assert tm.state == "open"
    assert "duplicate" in tm.reason


@pytest.mark.parametrize(
    ("high_name", "prototype_name"),
    [
        ("SR-MIX-a.md", "SR-MIX-b.md"),
        ("SR-MIX-b.md", "SR-MIX-a.md"),
    ],
)
def test_compile_obligations_duplicate_profiles_are_ambiguous_and_blocking(
    tmp_path, high_name, prototype_name
):
    duplicate_yaml = (
        "---\n"
        "id: SR-MIX\ntitle: t\nstatement: s\ndomain: d\n"
        "acceptance:\n"
        "  - id: AC-1\n"
        '    criterion: "c"\n'
        "    verification:\n"
        "      kind: test_marker\n"
        "      ref: \"tests/test_mixed_profile.py\"\n"
        "---\n"
    )
    requirements = tmp_path / "requirements"
    requirements.mkdir()
    (requirements / high_name).write_text(
        duplicate_yaml.replace("domain: d\n", "domain: d\nprofile: high_assurance\n"),
        encoding="utf-8",
    )
    (requirements / prototype_name).write_text(duplicate_yaml, encoding="utf-8")

    obligations = compile_obligations(tmp_path, "sr:SR-MIX")
    assert {o.kind for o in obligations} == {
        "ci_verification",
        "verification_result",
        "human_review",
        "test_marker",
    }
    for obligation in obligations:
        assert obligation.requiredness == "blocking"
        assert obligation.state == "open"
        assert obligation.source_policy == "ambiguous"
        assert "duplicate" in obligation.reason


def test_compile_obligations_test_marker_via_acceptance_unresolved_ref_stays_open(tmp_path):
    # The ref file exists but carries no matching marker: unsatisfied.
    experiment = "tests/test_ac_unsat.py"
    exp = tmp_path / experiment
    exp.parent.mkdir(parents=True, exist_ok=True)
    exp.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    _seed_unbound_sr_with_acceptance(
        tmp_path,
        "SR-021",
        acceptance_yaml=(
            "acceptance:\n"
            "  - id: AC-1\n"
            '    criterion: "c"\n'
            "    verification:\n"
            "      kind: test_marker\n"
            f"      ref: \"{experiment}\"\n"
        ),
        profile="high_assurance",
    )
    obligations = compile_obligations(tmp_path, "sr:SR-021")
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.requiredness == "blocking"
    assert tm.state == "open"
    assert "SR-021" in " ".join(tm.resolve_cmd or ())
    assert experiment in " ".join(tm.resolve_cmd or ())


def test_compile_obligations_test_marker_rejects_traversal_ref(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}_outside_traversal.py"
    outside.write_text(
        '@pytest.mark.sr("SR-025")\ndef test_x():\n    assert True\n',
        encoding="utf-8",
    )
    ref = f"../{outside.name}"
    _seed_unbound_sr_with_acceptance(
        tmp_path,
        "SR-025",
        acceptance_yaml=(
            "acceptance:\n"
            "  - id: AC-1\n"
            '    criterion: "c"\n'
            "    verification:\n"
            "      kind: test_marker\n"
            f"      ref: \"{ref}\"\n"
        ),
    )
    obligations = compile_obligations(tmp_path, "sr:SR-025")
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.state == "open"
    assert ref in " ".join(tm.resolve_cmd or ())


def test_compile_obligations_test_marker_rejects_absolute_outside_ref(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}_outside_absolute.py"
    outside.write_text(
        '@pytest.mark.sr("SR-026")\ndef test_x():\n    assert True\n',
        encoding="utf-8",
    )
    ref = outside.resolve().as_posix()
    _seed_unbound_sr_with_acceptance(
        tmp_path,
        "SR-026",
        acceptance_yaml=(
            "acceptance:\n"
            "  - id: AC-1\n"
            '    criterion: "c"\n'
            "    verification:\n"
            "      kind: test_marker\n"
            f"      ref: \"{ref}\"\n"
        ),
    )
    obligations = compile_obligations(tmp_path, "sr:SR-026")
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.state == "open"
    assert ref in " ".join(tm.resolve_cmd or ())


def test_compile_obligations_test_marker_rejects_parent_component_inside_root_ref(tmp_path):
    ref_target = "tests/test_ac_parent_inside_root.py"
    target = tmp_path / ref_target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        '@pytest.mark.sr("SR-029")\ndef test_x():\n    assert True\n',
        encoding="utf-8",
    )
    ref = "tests/../tests/test_ac_parent_inside_root.py"
    _seed_unbound_sr_with_acceptance(
        tmp_path,
        "SR-029",
        acceptance_yaml=(
            "acceptance:\n"
            "  - id: AC-1\n"
            '    criterion: "c"\n'
            "    verification:\n"
            "      kind: test_marker\n"
            f"      ref: \"{ref}\"\n"
        ),
    )
    obligations = compile_obligations(tmp_path, "sr:SR-029")
    tm = next(o for o in obligations if o.kind == "test_marker")

    assert tm.state == "open"
    assert ref in " ".join(tm.resolve_cmd or ())


@pytest.mark.skipif(sys.platform != "win32", reason="Windows rooted paths are platform-specific")
def test_compile_obligations_test_marker_rejects_current_drive_rooted_ref_inside_root(tmp_path):
    target = tmp_path / "tests" / "test_ac_rooted_inside_root.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        '@pytest.mark.sr("SR-030")\ndef test_x():\n    assert True\n',
        encoding="utf-8",
    )
    # On Windows this is rooted on the current drive but still resolves under
    # tmp_path. Path.is_absolute() is false for this form.
    ref = str(target)[2:]
    assert ref.startswith("\\")
    _seed_unbound_sr_with_acceptance(
        tmp_path,
        "SR-030",
        acceptance_yaml=(
            "acceptance:\n"
            "  - id: AC-1\n"
            '    criterion: "c"\n'
            "    verification:\n"
            "      kind: test_marker\n"
            f"      ref: '{ref}'\n"
        ),
    )
    obligations = compile_obligations(tmp_path, "sr:SR-030")
    tm = next(o for o in obligations if o.kind == "test_marker")

    assert tm.state == "open"
    assert ref in " ".join(tm.resolve_cmd or ())


def test_compile_obligations_test_marker_rejects_symlink_outside_ref(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}_outside_symlink.py"
    outside.write_text(
        '@pytest.mark.sr("SR-027")\ndef test_x():\n    assert True\n',
        encoding="utf-8",
    )
    ref = "tests/test_ac_symlink_outside.py"
    link = tmp_path / ref
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks are not supported: {exc}")
    _seed_unbound_sr_with_acceptance(
        tmp_path,
        "SR-027",
        acceptance_yaml=(
            "acceptance:\n"
            "  - id: AC-1\n"
            '    criterion: "c"\n'
            "    verification:\n"
            "      kind: test_marker\n"
            f"      ref: \"{ref}\"\n"
        ),
    )
    obligations = compile_obligations(tmp_path, "sr:SR-027")
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.state == "open"
    assert ref in " ".join(tm.resolve_cmd or ())


def test_compile_obligations_test_marker_rejects_directory_junction_ref(tmp_path):
    target_dir = tmp_path / "tests" / "ordinary"
    target_dir.mkdir(parents=True)
    target = target_dir / "target.py"
    target.write_text(
        '@pytest.mark.sr("SR-028")\ndef test_target():\n    assert True\n',
        encoding="utf-8",
    )
    alias = tmp_path / "tests" / "alias"
    if sys.platform == "win32":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(alias), str(target_dir)],
            capture_output=True,
            text=False,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).decode(errors="replace")
            pytest.skip(f"could not create a directory junction: {detail}")
    else:
        try:
            alias.symlink_to(target_dir, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"directory symlinks are not supported: {exc}")

    ref = "tests/alias/target.py"
    _seed_unbound_sr_with_acceptance(
        tmp_path,
        "SR-028",
        acceptance_yaml=(
            "acceptance:\n"
            "  - id: AC-1\n"
            '    criterion: "c"\n'
            "    verification:\n"
            "      kind: test_marker\n"
            f"      ref: \"{ref}\"\n"
        ),
    )

    obligations = compile_obligations(tmp_path, "sr:SR-028")
    tm = next(o for o in obligations if o.kind == "test_marker")

    assert tm.state == "open"
    assert ref in " ".join(tm.resolve_cmd or ())


def test_compile_obligations_test_marker_via_acceptance_partial_is_not_satisfied(tmp_path):
    # Two test_marker criteria; only one resolves. Partial satisfaction must
    # NOT be reported as satisfied -- this is the false-green this obligation
    # exists to prevent.
    good = "tests/test_ac_partial_good.py"
    bad = "tests/test_ac_partial_bad.py"
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / good).write_text(
        '@pytest.mark.sr("SR-022")\ndef test_x():\n    assert True\n', encoding="utf-8",
    )
    (tmp_path / bad).write_text("def test_y():\n    assert True\n", encoding="utf-8")
    _seed_unbound_sr_with_acceptance(
        tmp_path,
        "SR-022",
        acceptance_yaml=(
            "acceptance:\n"
            "  - id: AC-1\n"
            '    criterion: "a"\n'
            "    verification:\n"
            "      kind: test_marker\n"
            f"      ref: \"{good}\"\n"
            "  - id: AC-2\n"
            '    criterion: "b"\n'
            "    verification:\n"
            "      kind: test_marker\n"
            f"      ref: \"{bad}\"\n"
        ),
    )
    obligations = compile_obligations(tmp_path, "sr:SR-022")
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.state == "open"
    assert bad in " ".join(tm.resolve_cmd or ())
    assert good not in " ".join(tm.resolve_cmd or ())


def test_compile_obligations_test_marker_manual_only_criteria_is_not_applicable(tmp_path):
    # An SR whose acceptance criteria are all `kind: manual` (no test_marker
    # criteria at all) and carries no binding: not this obligation's concern.
    _seed_unbound_sr_with_acceptance(
        tmp_path,
        "SR-023",
        acceptance_yaml=(
            "acceptance:\n"
            "  - id: AC-1\n"
            '    criterion: "c"\n'
            "    verification:\n"
            "      kind: manual\n"
            '      reason: "no automated check"\n'
        ),
    )
    obligations = compile_obligations(tmp_path, "sr:SR-023")
    tm = next(o for o in obligations if o.kind == "test_marker")
    assert tm.requiredness == "not_applicable"
    assert tm.state == "satisfied"


def test_compile_obligations_test_marker_legacy_binding_ignores_acceptance(tmp_path):
    # An SR with a `binding.experiment` must behave exactly as the legacy
    # path always has, even when it ALSO carries a test_marker acceptance
    # criterion pointing elsewhere -- the legacy path is not merged with the
    # acceptance-based one.
    legacy_experiment = "tests/test_legacy_sr.py"
    exp = tmp_path / legacy_experiment
    exp.parent.mkdir(parents=True, exist_ok=True)
    exp.write_text(
        '@pytest.mark.sr("SR-024")\ndef test_x():\n    assert True\n', encoding="utf-8",
    )
    other_ref = "tests/test_ac_unrelated.py"
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / other_ref).write_text("def test_z():\n    assert True\n", encoding="utf-8")
    (tmp_path / "requirements").mkdir(exist_ok=True)
    (tmp_path / "requirements" / "SR-024.md").write_text(
        "---\n"
        "id: SR-024\ntitle: t\nstatement: s\ndomain: d\n"
        "binding:\n"
        f"  experiment: {legacy_experiment}\n"
        "  metric: m\n"
        "  assert: '>= 0.9'\n"
        "  harness: h\n"
        "acceptance:\n"
        "  - id: AC-1\n"
        '    criterion: "c"\n'
        "    verification:\n"
        "      kind: test_marker\n"
        f"      ref: \"{other_ref}\"\n"
        "---\n",
        encoding="utf-8",
    )
    obligations = compile_obligations(tmp_path, "sr:SR-024")
    tm = next(o for o in obligations if o.kind == "test_marker")
    # The bound experiment carries the marker -> satisfied, exactly like the
    # legacy path, regardless of the unrelated unresolved acceptance ref.
    assert tm.state == "satisfied"
    assert tm.requiredness == "required"


# --------------------------------------------------------------------------
# Review round 3, Critical 3: an accept that names nobody must not count as
# a human review. The substrate cannot tell an agent-written decision from a
# human one; what it CAN enforce is that the decision is attributed and
# timestamped, so an unattributed accept is exactly the self-certification
# I-01 forbids -- it is nobody's decision on record.
# --------------------------------------------------------------------------


def _write_unattributed_review_decision(
    tmp_path: Path,
    sr_id: str,
    *,
    decided_at: str = "2026-09-01T00:00:00Z",
    decided_by: str = "reviewer@example.invalid",
) -> Path:
    import json as _json

    from coherence.gate.store import decision_path

    # tmp_path fixture only -- never the repo's own gate store.
    path = decision_path(tmp_path, f"review:{sr_id}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _json.dumps(
            {
                "schema": 1,
                "gate_id": f"review:{sr_id}",
                "artifact_ref": f"artifact:requirements/{sr_id}.md",
                "decisions": [{"item_id": f"review:{sr_id}", "action": "accept"}],
                "decided_at": decided_at,
                "decided_by": decided_by,
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.mark.sr("SR-050")
def test_human_review_accept_with_a_blank_decided_by_stays_open(tmp_path):
    _seed_high_assurance_sr(tmp_path, "SR-120")
    _write_unattributed_review_decision(tmp_path, "SR-120", decided_by="")

    obligations = compile_obligations(tmp_path, "sr:SR-120")
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.state == "open"
    assert hr.requiredness == "blocking"


def test_human_review_accept_with_a_whitespace_decided_by_stays_open(tmp_path):
    _seed_high_assurance_sr(tmp_path, "SR-121")
    _write_unattributed_review_decision(tmp_path, "SR-121", decided_by="   ")

    obligations = compile_obligations(tmp_path, "sr:SR-121")
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.state == "open"


def test_human_review_accept_with_a_blank_decided_at_stays_open(tmp_path):
    _seed_high_assurance_sr(tmp_path, "SR-122")
    _write_unattributed_review_decision(tmp_path, "SR-122", decided_at="")

    obligations = compile_obligations(tmp_path, "sr:SR-122")
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.state == "open"


def test_human_review_accept_with_a_non_iso_decided_at_stays_open(tmp_path):
    _seed_high_assurance_sr(tmp_path, "SR-123")
    _write_unattributed_review_decision(tmp_path, "SR-123", decided_at="whenever")

    obligations = compile_obligations(tmp_path, "sr:SR-123")
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.state == "open"


def test_human_review_accept_naming_nobody_at_no_time_stays_open(tmp_path):
    """The exact proven shape: decided_at="" and decided_by="" with a single
    accept flipped the obligation from blocking/open to blocking/satisfied."""
    _seed_high_assurance_sr(tmp_path, "SR-124")
    _write_unattributed_review_decision(tmp_path, "SR-124", decided_at="", decided_by="")

    obligations = compile_obligations(tmp_path, "sr:SR-124")
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.state == "open"


def test_human_review_attributed_and_timestamped_accept_still_satisfies(tmp_path):
    """The positive control: attribution is what is newly required, not a
    new obstacle to a genuine review decision."""
    _seed_high_assurance_sr(tmp_path, "SR-125")
    _write_unattributed_review_decision(
        tmp_path, "SR-125", decided_at="2026-09-01T09:30:00Z", decided_by="a.human@example.invalid"
    )

    obligations = compile_obligations(tmp_path, "sr:SR-125")
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.state == "satisfied"


def test_human_review_date_only_decided_at_is_accepted(tmp_path):
    """`_is_iso` in gate/model.py is the one ISO validator; a bare
    YYYY-MM-DD is a supported form there and must stay supported here."""
    _seed_high_assurance_sr(tmp_path, "SR-126")
    _write_unattributed_review_decision(
        tmp_path, "SR-126", decided_at="2026-09-01", decided_by="a.human@example.invalid"
    )

    obligations = compile_obligations(tmp_path, "sr:SR-126")
    hr = next(o for o in obligations if o.kind == "human_review")
    assert hr.state == "satisfied"
