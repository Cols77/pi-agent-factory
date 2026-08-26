"""Increment 8: long-run gating on compiled ``test_marker`` obligations.

``_blocking_for`` must treat a blocking, not-satisfied ``test_marker`` obligation
(the missing ``@pytest.mark.sr(...)`` marker on a high-assurance SR's bound
experiment test file) as a run-gating winner, while a satisfied marker does not
gate and a prototype (``required``, non-blocking) marker never gates. A
``test_marker`` winner must behave like ``human_review`` for rerun purposes:
it is never auto-rerunnable.
"""
import pytest

from substrate.policy.obligation import Obligation, Requiredness

pytestmark = pytest.mark.unit


def _tm(
    *,
    state: str,
    requiredness: Requiredness = "blocking",
    scope_ref: str = "sr:SR-HA-001",
    resolve_cmd: tuple[str, ...] | None = ("add @pytest.mark.sr(\"SR-HA-001\") to test_ha.py",),
) -> Obligation:
    return Obligation(
        id=f"ob:test_marker:{scope_ref}",
        scope_ref=scope_ref,
        kind="test_marker",
        requiredness=requiredness,
        reason="high_assurance requires @pytest.mark.sr on the bound test file",
        source_policy="high_assurance",
        state=state,
        resolve_cmd=resolve_cmd,
    )


def _stub(obligations: list[Obligation]):
    from coherence.policy import compiler as policy_compiler

    def _fake_compile(root_in, scope_ref_in) -> list[Obligation]:
        return obligations

    return policy_compiler, _fake_compile


def _blocking_for(root, req_ids, *, verdict_files=None, repeatable_policy=None):
    from coherence.runs import service as runs_service

    return runs_service._blocking_for(
        root,
        tuple(sorted(req_ids)),
        policy_bound=True,
        verdict_files=verdict_files or {},
        repeatable_policy=repeatable_policy or {},
        max_reruns=2,
        reruns_used=0,
    )


def _run(monkeypatch, root, req_ids, obligations, *, verdict_files=None, repeatable_policy=None):
    policy_compiler, fake = _stub(obligations)
    monkeypatch.setattr(policy_compiler, "compile_obligations", fake)
    return _blocking_for(
        root,
        req_ids,
        verdict_files=verdict_files,
        repeatable_policy=repeatable_policy,
    )


def test_blocking_open_test_marker_gates_the_run(tmp_path, monkeypatch):
    blocking_id, resolve_cmd, rerun = _run(monkeypatch, tmp_path, ["SR-HA-001"], [_tm(state="open")])
    assert blocking_id == "ob:test_marker:sr:SR-HA-001"
    assert resolve_cmd == _tm(state="open").resolve_cmd
    assert rerun is False  # test_marker is never auto-rerun, like human_review


def test_satisfied_test_marker_does_not_gate(tmp_path, monkeypatch):
    blocking_id, resolve_cmd, rerun = _run(
        monkeypatch, tmp_path, ["SR-HA-001"], [_tm(state="satisfied")]
    )
    assert (blocking_id, resolve_cmd, rerun) == (None, None, False)


def test_prototype_required_nonblocking_test_marker_does_not_gate(tmp_path, monkeypatch):
    # "required" is not "blocking", so a missing marker on a prototype profile
    # must not gate the run (only high_assurance compiles to blocking).
    tm = _tm(state="open", requiredness="required", scope_ref="sr:SR-PROTO-001")
    blocking_id, resolve_cmd, rerun = _run(monkeypatch, tmp_path, ["SR-PROTO-001"], [tm])
    assert (blocking_id, resolve_cmd, rerun) == (None, None, False)


def test_blocking_and_satisfied_markers_pick_the_open_one(tmp_path, monkeypatch):
    # A satisfied marker must not win even though it may sort earlier by id;
    # gating is driven by blocking+open candidates only.
    blocking_id, _, _ = _run(
        monkeypatch,
        tmp_path,
        ["SR-HA-001"],
        [_tm(state="satisfied"), _tm(state="open")],
    )
    assert blocking_id == "ob:test_marker:sr:SR-HA-001"


def test_verification_result_wins_over_test_marker(tmp_path, monkeypatch):
    vr = Obligation(
        id="ob:verification_result:sr:SR-HA-001",
        scope_ref="sr:SR-HA-001",
        kind="verification_result",
        requiredness="blocking",
        reason="verification needed",
        source_policy="high_assurance",
        state="open",
        resolve_cmd=("run coverage",),
    )
    verdict = tmp_path / "verdicts" / "SR-HA-001.json"
    verdict.parent.mkdir(parents=True)
    verdict.write_text("{}", encoding="utf-8")
    # Precedence: verification_result > human_review > test_marker, so an open
    # verification_result still outscores a blocking+open test_marker.
    blocking_id, resolve_cmd, rerun = _run(
        monkeypatch,
        tmp_path,
        ["SR-HA-001"],
        [_tm(state="open"), vr],
        verdict_files={"SR-HA-001": verdict},
        repeatable_policy={"SR-HA-001": True},
    )
    assert blocking_id == vr.id
    assert resolve_cmd == vr.resolve_cmd
    assert rerun is True  # verification_result remains auto-rerunnable


def test_human_review_wins_over_test_marker_but_never_reruns(tmp_path, monkeypatch):
    hr = Obligation(
        id="ob:human_review:sr:SR-HA-001",
        scope_ref="sr:SR-HA-001",
        kind="human_review",
        requiredness="blocking",
        reason="audit review required",
        source_policy="high_assurance",
        state="open",
        resolve_cmd=("python -m audit run FEAT-HA",),
    )
    blocking_id, resolve_cmd, rerun = _run(
        monkeypatch, tmp_path, ["SR-HA-001"], [_tm(state="open"), hr]
    )
    assert blocking_id == hr.id
    assert resolve_cmd == hr.resolve_cmd
    assert rerun is False  # human_review never auto-reruns


def test_test_marker_never_reruns_even_with_all_prereqs(tmp_path, monkeypatch):
    verdict = tmp_path / "verdicts" / "SR-HA-001.json"
    verdict.parent.mkdir(parents=True)
    verdict.write_text("{}", encoding="utf-8")
    # A test_marker winner must not auto-rerun even when every verification_result
    # rerun prerequisite is satisfied (verdict file present, repeatable, budget).
    _, _, rerun = _run(
        monkeypatch,
        tmp_path,
        ["SR-HA-001"],
        [_tm(state="open")],
        verdict_files={"SR-HA-001": verdict},
        repeatable_policy={"SR-HA-001": True},
    )
    assert rerun is False