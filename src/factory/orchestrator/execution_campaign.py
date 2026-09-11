"""SR-034/SR-049 baseline, campaign and flaky/regression classification.

A campaign captures one pre-DEV baseline, runs the required test suite after
DEV, and compares the two. A declared test that passed in the baseline and
fails after DEV is a deterministic regression introduced by the change -- it is
a regression regardless of any registry entry. A failure with no baseline
history gets exactly one bounded classification re-run: a confirmation pass
becomes a human-visible registry candidate, a repeated failure becomes a
regression. That re-run is never a DEV fix attempt and never consumes the fixer
budget. Registered known-flaky failures keep running non-blocking and are
recorded as ``flaky_ids`` rather than regressions.

The result is fail-closed: it must carry the full declared test id set and a
pass rate in ``[0.0, 1.0]``, or construction raises :class:`CampaignError`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from factory.orchestrator.execution_contract import ExecutionContract


class CampaignError(RuntimeError):
    """A campaign snapshot or result is incomplete, contradictory or out of range."""


class FlakyRegistry(Protocol):
    """The read-only known-flaky lookup the campaign consults (never a writer)."""

    def is_registered(self, test_id: str) -> bool: ...


class TestCampaignRunner(Protocol):
    """Runs the required test suite once and reports a :class:`TestSnapshot`."""

    def run(self, contract: ExecutionContract) -> TestSnapshot: ...


@dataclass(frozen=True)
class TestSnapshot:
    """One full run of the declared test ids: stable node ids, no display names."""

    passed_ids: frozenset[str]
    failed_ids: frozenset[str]
    pass_rate: float
    declared_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        rate = self.pass_rate
        if not isinstance(rate, (int, float)) or isinstance(rate, bool) or not (
            0.0 <= float(rate) <= 1.0
        ):
            raise CampaignError(f"pass_rate must be in [0.0, 1.0], got {rate!r}")
        passed = frozenset(self.passed_ids)
        failed = frozenset(self.failed_ids)
        declared = frozenset(self.declared_ids)
        if passed & failed:
            raise CampaignError("a test id cannot both pass and fail in one snapshot")
        if not (passed | failed) <= declared:
            raise CampaignError("snapshot ids escape the declared test id set")
        if (passed | failed) != declared:
            missing = sorted(declared - (passed | failed))
            raise CampaignError(f"snapshot omits declared test ids: {missing}")
        expected = (len(passed) / len(declared)) if declared else 0.0
        if abs(float(rate) - expected) > 1e-9:
            raise CampaignError(
                f"pass_rate {rate!r} disagrees with passed/declared ({expected!r})"
            )


@dataclass(frozen=True)
class CampaignResult:
    """SR-049 classification evidence for one post-DEV campaign."""

    snapshot: TestSnapshot
    regressions: tuple[str, ...]
    pre_existing_failures: tuple[str, ...]
    flaky_ids: tuple[str, ...]
    registry_candidates: tuple[str, ...]
    classification_reruns: dict[str, int]
    pass_rate_gate_passed: bool
    fixer_iterations_consumed: int = 0
    failed_ids: frozenset[str] = frozenset()
    declared_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        declared = frozenset(self.declared_ids) | frozenset(self.snapshot.declared_ids)
        if not declared:
            raise CampaignError("campaign result cannot omit the declared test id set")
        failed = frozenset(self.failed_ids)
        if not failed <= declared:
            raise CampaignError("campaign result failure ids escape the declared set")
        if failed != frozenset(self.snapshot.failed_ids):
            raise CampaignError("campaign result failed_ids disagree with its snapshot")
        for test_id, count in self.classification_reruns.items():
            if count != 1:
                raise CampaignError(
                    f"{test_id!r} must get exactly one classification re-run, got {count}"
                )


@dataclass
class TestCampaign:
    """Baseline capture and post-DEV classification (production, ``src/``)."""

    # Production class under src/: keep pytest from trying to collect it.
    __test__ = False

    runner: TestCampaignRunner
    flaky_registry: FlakyRegistry
    _baseline: TestSnapshot | None = field(default=None, init=False, repr=False)

    def capture_baseline(self, contract: ExecutionContract) -> TestSnapshot:
        """Run the required suite exactly once, before DEV."""
        baseline = self.runner.run(contract)
        self._baseline = baseline
        return baseline

    def evaluate_after_dev(
        self, contract: ExecutionContract, baseline: TestSnapshot
    ) -> CampaignResult:
        """Compare against the baseline and classify every failure."""
        current = self.runner.run(contract)
        failed = set(current.failed_ids)

        # A declared test that passed before and fails now is a regression,
        # independent of any registry entry.
        regressions = set(baseline.passed_ids) & failed
        # A test that failed before and still fails is pre-existing, not injected.
        pre_existing = set(baseline.failed_ids) & failed
        # Registered known-flaky failures run non-blocking and are recorded.
        flaky_ids = {test_id for test_id in failed if self.flaky_registry.is_registered(test_id)}

        reruns: dict[str, int] = {}
        candidates: list[str] = []
        explained = regressions | pre_existing | flaky_ids
        for test_id in sorted(failed - explained):
            # An id with no baseline history (new or undeclared) is the only
            # ambiguous case: exactly one bounded classification re-run.
            reruns[test_id] = 1
            confirmation = self.runner.run(contract)
            if test_id in confirmation.failed_ids:
                regressions.add(test_id)
            else:
                candidates.append(test_id)

        return CampaignResult(
            snapshot=current,
            regressions=tuple(sorted(regressions)),
            pre_existing_failures=tuple(sorted(pre_existing)),
            flaky_ids=tuple(sorted(flaky_ids)),
            registry_candidates=tuple(sorted(candidates)),
            classification_reruns=reruns,
            pass_rate_gate_passed=not failed,
            fixer_iterations_consumed=0,
            failed_ids=frozenset(current.failed_ids),
            declared_ids=frozenset(current.declared_ids),
        )


__all__ = [
    "CampaignError",
    "CampaignResult",
    "FlakyRegistry",
    "TestCampaign",
    "TestCampaignRunner",
    "TestSnapshot",
]
