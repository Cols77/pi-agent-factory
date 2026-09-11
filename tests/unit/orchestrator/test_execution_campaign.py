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
