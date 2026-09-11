"""SR-034/SR-049 baseline, campaign and classification tests (RED first).

Coherent semantics used here: a regression is a declared test that passed in the
baseline and fails after DEV; a pre-existing failure failed in both; a failure
with no baseline history gets exactly one bounded classification re-run (never a
DEV fix attempt, never a fixer-budget increment).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from factory.orchestrator.execution_campaign import (
    CampaignError,
    CampaignResult,
    TestCampaign,
    TestSnapshot,
)
from factory.orchestrator.execution_contract import ExecutionContract

pytestmark = pytest.mark.unit


def contract_fixture(tmp_path: Path) -> ExecutionContract:
    return ExecutionContract.build(
        run_id="run-013",
        task_id="T-013",
        workflow_version="governed-execution/v1",
        workspace=tmp_path / "worktree",
        required_gates=("unit",),
        satisfies=("SR-034", "SR-049"),
        plan_ref=None,
        spec_ref=None,
        max_fixer_iterations=2,
    )


def snapshot(*passed_ids: str, failed: tuple[str, ...] = (), declared: tuple[str, ...] = ()):
    passed = frozenset(passed_ids)
    failed_ids = frozenset(failed)
    declared_ids = frozenset(declared) if declared else (passed | failed_ids)
    total = len(declared_ids)
    pass_rate = (len(passed) / total) if total else 0.0
    return TestSnapshot(
        passed_ids=passed,
        failed_ids=failed_ids,
        pass_rate=pass_rate,
        declared_ids=declared_ids,
    )


class ScriptedCampaignRunner:
    def __init__(self, snapshots: list[TestSnapshot]) -> None:
        self._snapshots = list(snapshots)
        self.calls = 0

    def run(self, contract: ExecutionContract) -> TestSnapshot:
        self.calls += 1
        if not self._snapshots:
            raise AssertionError("campaign runner script exhausted")
        return self._snapshots.pop(0)


class EmptyFlakyRegistry:
    def is_registered(self, test_id: str) -> bool:
        return False


class HumanFlakyRegistry:
    def __init__(self, ids: set[str]) -> None:
        self._ids = set(ids)

    def is_registered(self, test_id: str) -> bool:
        return test_id in self._ids


def test_production_campaign_class_is_not_collected_by_pytest() -> None:
    assert TestCampaign.__test__ is False


def test_passing_baseline_and_new_failure_are_classified_as_regression(tmp_path: Path) -> None:
    runner = ScriptedCampaignRunner(
        [snapshot("a", "b"), snapshot("a", failed=("b",), declared=("a", "b"))]
    )
    campaign = TestCampaign(runner, flaky_registry=EmptyFlakyRegistry())

    baseline = campaign.capture_baseline(contract_fixture(tmp_path))
    assert runner.calls == 1
    outcome = campaign.evaluate_after_dev(contract_fixture(tmp_path), baseline)

    assert outcome.failed_ids == frozenset({"b"})
    assert outcome.regressions == ("b",)
    assert outcome.pre_existing_failures == ()
    assert outcome.pass_rate_gate_passed is False
    assert outcome.fixer_iterations_consumed == 0


def test_pre_existing_failure_is_not_injected_as_a_regression(tmp_path: Path) -> None:
    runner = ScriptedCampaignRunner(
        [
            snapshot("a", failed=("pre-existing",)),
            snapshot("a", failed=("pre-existing",)),
        ]
    )
    campaign = TestCampaign(runner, flaky_registry=EmptyFlakyRegistry())

    baseline = campaign.capture_baseline(contract_fixture(tmp_path))
    outcome = campaign.evaluate_after_dev(contract_fixture(tmp_path), baseline)

    assert outcome.regressions == ()
    assert outcome.pre_existing_failures == ("pre-existing",)
    assert outcome.classification_reruns == {}


def test_unlisted_failure_gets_one_classification_rerun_and_never_a_fix_retry(
    tmp_path: Path,
) -> None:
    runner = ScriptedCampaignRunner(
        [
            snapshot("a"),
            snapshot("a", failed=("flaky",), declared=("a", "flaky")),
            snapshot("a", "flaky"),
        ]
    )
    campaign = TestCampaign(runner, flaky_registry=EmptyFlakyRegistry())

    baseline = campaign.capture_baseline(contract_fixture(tmp_path))
    outcome = campaign.evaluate_after_dev(contract_fixture(tmp_path), baseline)

    assert runner.calls == 3
    assert outcome.classification_reruns == {"flaky": 1}
    assert outcome.registry_candidates == ("flaky",)
    assert outcome.regressions == ()
    assert outcome.fixer_iterations_consumed == 0


def test_repeated_unlisted_failure_becomes_a_regression(tmp_path: Path) -> None:
    runner = ScriptedCampaignRunner(
        [
            snapshot("a"),
            snapshot("a", failed=("flaky",), declared=("a", "flaky")),
            snapshot("a", failed=("flaky",), declared=("a", "flaky")),
        ]
    )
    campaign = TestCampaign(runner, flaky_registry=EmptyFlakyRegistry())

    baseline = campaign.capture_baseline(contract_fixture(tmp_path))
    outcome = campaign.evaluate_after_dev(contract_fixture(tmp_path), baseline)

    assert outcome.classification_reruns == {"flaky": 1}
    assert outcome.registry_candidates == ()
    assert outcome.regressions == ("flaky",)


def test_registered_flaky_failure_is_quarantined_not_a_regression(tmp_path: Path) -> None:
    runner = ScriptedCampaignRunner(
        [snapshot("a"), snapshot("a", failed=("known",), declared=("a", "known"))]
    )
    campaign = TestCampaign(runner, flaky_registry=HumanFlakyRegistry({"known"}))

    baseline = campaign.capture_baseline(contract_fixture(tmp_path))
    outcome = campaign.evaluate_after_dev(contract_fixture(tmp_path), baseline)

    assert outcome.flaky_ids == ("known",)
    assert outcome.regressions == ()
    assert outcome.classification_reruns == {}
    assert runner.calls == 2


def test_campaign_types_fail_closed_on_incomplete_or_out_of_range_results() -> None:
    with pytest.raises(CampaignError):
        TestSnapshot(
            passed_ids=frozenset({"a"}),
            failed_ids=frozenset(),
            pass_rate=1.0,
            declared_ids=frozenset({"a", "b"}),  # "b" omitted
        )
    with pytest.raises(CampaignError):
        TestSnapshot(
            passed_ids=frozenset({"a"}),
            failed_ids=frozenset({"b"}),
            pass_rate=1.5,  # outside [0, 1]
            declared_ids=frozenset({"a", "b"}),
        )
    good = snapshot("a", failed=("b",))
    with pytest.raises(CampaignError):
        CampaignResult(
            snapshot=good,
            regressions=(),
            pre_existing_failures=(),
            flaky_ids=(),
            registry_candidates=(),
            classification_reruns={},
            pass_rate_gate_passed=False,
            failed_ids=frozenset(),  # omits the declared failure
            declared_ids=frozenset({"a"}),  # omits "b"
        )


def test_campaign_result_rejects_inconsistent_classification_sets() -> None:
    good = snapshot("a", failed=("b",))

    def result(**overrides: object) -> CampaignResult:
        kwargs: dict[str, object] = {
            "regressions": (),
            "pre_existing_failures": (),
            "flaky_ids": (),
            "registry_candidates": (),
            "classification_reruns": {},
            "pass_rate_gate_passed": False,
            "failed_ids": frozenset({"b"}),
            "declared_ids": frozenset({"a", "b"}),
        }
        kwargs.update(overrides)
        return CampaignResult(snapshot=good, **kwargs)  # type: ignore[arg-type]

    # Control: a coherent result is accepted.
    assert result(regressions=("b",)).regressions == ("b",)

    for call in (
        lambda: result(regressions=("ghost",)),  # M1a: not in failed_ids
        lambda: result(pass_rate_gate_passed=True),  # M1b: gate with a live failure
        lambda: result(pre_existing_failures=("ghost",)),  # M1c: not in failed_ids
        lambda: result(registry_candidates=("ghost",)),  # M1d: not in failed_ids
        lambda: result(regressions=("b",), flaky_ids=("b",)),  # overlapping disposition
    ):
        with pytest.raises(CampaignError):
            call()


def test_confirmation_run_must_cover_the_declared_set(tmp_path: Path) -> None:
    runner = ScriptedCampaignRunner(
        [
            snapshot("a"),
            snapshot("a", failed=("ghost",), declared=("a", "ghost")),
            snapshot("a"),  # confirmation drops the undeclared id entirely
        ]
    )
    campaign = TestCampaign(runner, flaky_registry=EmptyFlakyRegistry())
    baseline = campaign.capture_baseline(contract_fixture(tmp_path))

    with pytest.raises(CampaignError):
        campaign.evaluate_after_dev(contract_fixture(tmp_path), baseline)


def test_registered_flaky_failure_is_never_also_a_regression(tmp_path: Path) -> None:
    runner = ScriptedCampaignRunner(
        [snapshot("known"), snapshot(failed=("known",), declared=("known",))]
    )
    campaign = TestCampaign(runner, flaky_registry=HumanFlakyRegistry({"known"}))

    baseline = campaign.capture_baseline(contract_fixture(tmp_path))
    outcome = campaign.evaluate_after_dev(contract_fixture(tmp_path), baseline)

    assert outcome.regressions == ()
    assert outcome.flaky_ids == ("known",)


def test_repeat_confirmation_run_is_refused(tmp_path: Path) -> None:
    same_pass = snapshot("a", failed=("ghost",), declared=("a", "ghost"))
    runner = ScriptedCampaignRunner(
        [
            snapshot("a"),
            same_pass,
            snapshot("a", failed=("ghost",), declared=("a", "ghost")),
            same_pass,  # a second evaluation of the SAME pass
        ]
    )
    campaign = TestCampaign(runner, flaky_registry=EmptyFlakyRegistry())
    baseline = campaign.capture_baseline(contract_fixture(tmp_path))
    campaign.evaluate_after_dev(contract_fixture(tmp_path), baseline)
    assert runner.calls == 3

    with pytest.raises(CampaignError):
        campaign.evaluate_after_dev(contract_fixture(tmp_path), baseline)
    # Only the pass's own suite run; the confirmation is never repeated.
    assert runner.calls == 4


def test_successive_passes_evaluate_but_repeating_a_pass_is_refused(tmp_path: Path) -> None:
    """D1: the kernel injects ONE campaign, captures the baseline ONCE outside
    the loop, and evaluates inside ``while True:`` -- every DEV pass (each fixer
    revision and human retry) needs its own evaluation."""
    regressing_pass = snapshot("a", failed=("b",), declared=("a", "b"))
    runner = ScriptedCampaignRunner(
        [
            snapshot("a", "b"),  # baseline, captured once before the loop
            regressing_pass,  # pass 1
            snapshot("a", "b"),  # pass 2: the fixer cleared the failure
            regressing_pass,  # a repeat evaluation of pass 1
        ]
    )
    campaign = TestCampaign(runner, flaky_registry=EmptyFlakyRegistry())
    baseline = campaign.capture_baseline(contract_fixture(tmp_path))

    first = campaign.evaluate_after_dev(contract_fixture(tmp_path), baseline)
    assert first.regressions == ("b",)
    assert first.pass_rate_gate_passed is False

    second = campaign.evaluate_after_dev(contract_fixture(tmp_path), baseline)
    assert second.regressions == ()
    assert second.pass_rate_gate_passed is True

    with pytest.raises(CampaignError):
        campaign.evaluate_after_dev(contract_fixture(tmp_path), baseline)


def test_evaluation_guard_latches_on_the_error_path(tmp_path: Path) -> None:
    """D2: a pass whose first evaluation RAISES is still consumed, so a retry of
    the same pass cannot re-run the bounded confirmation."""
    pass_snapshot = snapshot("a", failed=("ghost",), declared=("a", "ghost"))
    runner = ScriptedCampaignRunner(
        [
            snapshot("a"),  # baseline
            pass_snapshot,  # evaluation #1: "ghost" has no baseline history
            snapshot("a"),  # confirmation drops the declared id -> raises
            pass_snapshot,  # retry of the SAME pass
        ]
    )
    campaign = TestCampaign(runner, flaky_registry=EmptyFlakyRegistry())
    baseline = campaign.capture_baseline(contract_fixture(tmp_path))

    with pytest.raises(CampaignError, match="omits declared test ids"):
        campaign.evaluate_after_dev(contract_fixture(tmp_path), baseline)
    assert runner.calls == 3

    with pytest.raises(CampaignError, match="once-only"):
        campaign.evaluate_after_dev(contract_fixture(tmp_path), baseline)
    assert runner.calls == 4  # the pass run only -- never a second confirmation


def test_pass_rate_gate_compares_only_blocking_failures(tmp_path: Path) -> None:
    """D3: quarantined known-flaky failures are non-blocking, so a run whose only
    failures are quarantined may pass the gate; a real failure still cannot."""
    quarantined = CampaignResult(
        snapshot=snapshot("a", failed=("known",), declared=("a", "known")),
        regressions=(),
        pre_existing_failures=(),
        flaky_ids=("known",),
        registry_candidates=(),
        classification_reruns={},
        pass_rate_gate_passed=True,
        failed_ids=frozenset({"known"}),
        declared_ids=frozenset({"a", "known"}),
    )
    assert quarantined.pass_rate_gate_passed is True

    runner = ScriptedCampaignRunner(
        [snapshot("a"), snapshot("a", failed=("known",), declared=("a", "known"))]
    )
    campaign = TestCampaign(runner, flaky_registry=HumanFlakyRegistry({"known"}))
    baseline = campaign.capture_baseline(contract_fixture(tmp_path))
    outcome = campaign.evaluate_after_dev(contract_fixture(tmp_path), baseline)

    assert outcome.flaky_ids == ("known",)
    assert outcome.pass_rate_gate_passed is True

    with pytest.raises(CampaignError, match="blocking"):
        CampaignResult(
            snapshot=snapshot("a", failed=("b",), declared=("a", "b")),
            regressions=("b",),
            pre_existing_failures=(),
            flaky_ids=(),
            registry_candidates=(),
            classification_reruns={},
            pass_rate_gate_passed=True,
            failed_ids=frozenset({"b"}),
            declared_ids=frozenset({"a", "b"}),
        )


def test_every_failed_id_must_carry_exactly_one_disposition() -> None:
    """D5: a failed id may not be left without a disposition set."""
    good = snapshot("a", failed=("b",))

    def result(**overrides: object) -> CampaignResult:
        kwargs: dict[str, object] = {
            "regressions": (),
            "pre_existing_failures": (),
            "flaky_ids": (),
            "registry_candidates": (),
            "classification_reruns": {},
            "pass_rate_gate_passed": False,
            "failed_ids": frozenset({"b"}),
            "declared_ids": frozenset({"a", "b"}),
        }
        kwargs.update(overrides)
        return CampaignResult(snapshot=good, **kwargs)  # type: ignore[arg-type]

    with pytest.raises(CampaignError, match="disposition"):
        result()  # "b" failed but no disposition set names it
