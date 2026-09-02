import pytest
from factory.freshness.model import FreshnessSeverity
from factory.requirements.closure import RequirementState, classify
from factory.requirements.register import Binding, Requirement

pytestmark = pytest.mark.unit


def _req(tmp_path, *, binding=None, checksum=None, statement="When X, the system shall Y."):
    return Requirement(
        id="SR-001", title="t", statement=statement, domain="behavioral", upstream=[],
        binding=binding, body="", path=tmp_path / "SR-001.md", checksum=checksum,
    )


def _bound(harness="demo-harness"):
    return Binding(
        experiment="e", metric="m", assert_expr=">= 0.90", harness=harness, trials=1, window=None
    )


def _current(tmp_path, binding):
    from factory.requirements.register import content_checksum
    req = _req(tmp_path, binding=binding)
    return _req(tmp_path, binding=binding, checksum=content_checksum(req))


def test_a_passing_validation_result_is_measured_passing(tmp_path):
    finding = classify(
        _current(tmp_path, _bound()), validation="passing",
        linked_task_status=None, deferred_reason=None,
    )
    assert finding.state is RequirementState.MEASURED_PASSING
    assert finding.severity is None, "a healthy state carries no severity"
    assert finding.req_id == "SR-001"


def test_a_failing_validation_result_is_legal_but_distinct(tmp_path):
    finding = classify(
        _current(tmp_path, _bound()), validation="failing",
        linked_task_status=None, deferred_reason=None,
    )
    assert finding.state is RequirementState.MEASURED_FAILING, "a failing result is honest evidence"
    assert finding.severity is None, (
        "measured-failing is a healthy CLOSURE state -- bound, current and genuinely "
        "measured; the failure belongs to the validation report, not the register"
    )


def test_no_result_with_a_live_task_is_planned(tmp_path):
    finding = classify(
        _current(tmp_path, _bound()), validation=None,
        linked_task_status="todo", deferred_reason=None,
    )
    assert finding.state is RequirementState.PLANNED


def test_no_result_with_a_done_task_is_pending_not_planned(tmp_path):
    finding = classify(
        _current(tmp_path, _bound()), validation=None,
        linked_task_status="done", deferred_reason=None,
    )
    assert finding.state is RequirementState.PENDING, "a done task that produced nothing is not a plan"
    assert finding.severity is FreshnessSeverity.BLOCKING


def test_no_result_and_no_task_is_pending(tmp_path):
    finding = classify(
        _current(tmp_path, _bound()), validation=None,
        linked_task_status=None, deferred_reason=None,
    )
    assert finding.state is RequirementState.PENDING


def test_an_unnamed_harness_is_unmeasurable_and_only_a_warning(tmp_path):
    finding = classify(
        _current(tmp_path, _bound(harness=None)), validation=None,
        linked_task_status="todo", deferred_reason=None,
    )
    assert finding.state is RequirementState.UNMEASURABLE
    assert finding.severity is FreshnessSeverity.WARNING, "an unnamed instrument never blocks"


def test_a_deferred_requirement_is_declined(tmp_path):
    finding = classify(
        _req(tmp_path), validation=None, linked_task_status=None,
        deferred_reason="no task delivers this yet",
    )
    assert finding.state is RequirementState.DECLINED
    assert "no task delivers this yet" in finding.detail


@pytest.mark.sr("SR-002")
def test_an_unbound_requirement_with_no_disposition_is_pending(tmp_path):
    finding = classify(
        _req(tmp_path), validation=None, linked_task_status=None, deferred_reason=None,
    )
    assert finding.state is RequirementState.PENDING
    assert finding.severity is FreshnessSeverity.BLOCKING


def test_a_stale_checksum_is_pending_whatever_else_is_true(tmp_path):
    stale = _req(tmp_path, binding=_bound(), checksum="sha256:0000")
    finding = classify(
        stale, validation="passing", linked_task_status="todo", deferred_reason=None,
    )
    assert finding.state is RequirementState.PENDING, "a stale binding may no longer measure the statement"
    assert finding.severity is FreshnessSeverity.BLOCKING
    assert "stale" in finding.detail.lower()


def test_a_deferral_wins_over_pending_but_not_over_a_real_result(tmp_path):
    declined = classify(
        _req(tmp_path), validation=None, linked_task_status=None, deferred_reason="later",
    )
    measured = classify(
        _current(tmp_path, _bound()), validation="passing",
        linked_task_status=None, deferred_reason="later",
    )
    assert declined.state is RequirementState.DECLINED
    assert measured.state is RequirementState.MEASURED_PASSING, "evidence outranks a deferral"


def test_healthy_states_carry_no_severity(tmp_path):
    planned = classify(
        _current(tmp_path, _bound()), validation=None,
        linked_task_status="todo", deferred_reason=None,
    )
    declined = classify(
        _req(tmp_path), validation=None, linked_task_status=None, deferred_reason="later",
    )
    assert planned.severity is None
    assert declined.severity is None
