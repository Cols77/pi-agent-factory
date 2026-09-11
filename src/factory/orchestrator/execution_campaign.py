"""SR-034/SR-049 baseline, campaign and flaky/regression classification.

A campaign captures one pre-DEV baseline, runs the required test suite after
DEV, and compares the two. A declared test that passed in the baseline and
fails after DEV is a deterministic regression introduced by the change -- it is
a regression regardless of any registry entry. A failure with no baseline
history gets exactly one bounded classification re-run: a confirmation pass
becomes a human-visible registry candidate, a repeated failure becomes a
regression. That re-run is never a DEV fix attempt and never consumes the fixer
budget. A registered known-flaky failure with no baseline history keeps
running non-blocking and is recorded as ``flaky_ids``. A registered flaky test
that PASSED in the baseline and fails after DEV is STILL a regression: the
registry never covers a deterministic failure introduced by the change. Such a
test is blocking and is additionally surfaced in ``registry_candidates`` so the
stale entry stays visible to the human (fix-or-delete at expiry).

Classification is recomputed on every call from the live registry, so a
registry change is never served a stale verdict. The only memo is the bounded
confirmation outcome, which caches a runner result and is registry-independent.

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
        # Every failed id is classified exactly once among the three mutually
        # exclusive dispositions. ``registry_candidates`` is a curation signal
        # rather than a disposition: the one legal overlap is a stale entry
        # that a deterministic regression overtook -- the same id is reported
        # as a blocking regression AND kept visible for registry curation.
        dispositioned: dict[str, str] = {}
        for name, ids in (
            ("regressions", self.regressions),
            ("pre_existing_failures", self.pre_existing_failures),
            ("flaky_ids", self.flaky_ids),
        ):
            unknown = frozenset(ids) - failed
            if unknown:
                raise CampaignError(f"{name} escape the failed test id set: {sorted(unknown)}")
            for test_id in ids:
                if test_id in dispositioned:
                    raise CampaignError(
                        f"{test_id!r} cannot be both {dispositioned[test_id]} and {name}"
                    )
                dispositioned[test_id] = name
        unknown_candidates = frozenset(self.registry_candidates) - failed
        if unknown_candidates:
            raise CampaignError(
                f"registry_candidates escape the failed test id set: {sorted(unknown_candidates)}"
            )
        for test_id in self.registry_candidates:
            existing = dispositioned.get(test_id)
            if existing is not None and existing != "regressions":
                raise CampaignError(
                    f"{test_id!r} cannot be both {existing} and registry_candidates"
                )
            dispositioned.setdefault(test_id, "registry_candidates")
        unclassified = failed - set(dispositioned)

        if unclassified:
            raise CampaignError(f"failed ids carry no disposition: {sorted(unclassified)}")
        # Quarantined known-flaky failures are non-blocking: only a failure that
        # is not a registered flake can contradict a passed pass-rate gate.
        blocking = failed - frozenset(self.flaky_ids)
        if self.pass_rate_gate_passed and blocking:
            raise CampaignError(
                f"pass rate gate cannot pass while blocking failures remain: {sorted(blocking)}"
            )


@dataclass
class TestCampaign:
    """Baseline capture and post-DEV classification (production, ``src/``)."""

    # Production class under src/: keep pytest from trying to collect it.
    __test__ = False

    runner: TestCampaignRunner
    flaky_registry: FlakyRegistry
    _baseline: TestSnapshot | None = field(default=None, init=False, repr=False)
    # The bounded confirmation memo, keyed on (pass snapshot, unlisted failed
    # id). It caches a RUNNER OUTCOME -- registry-independent evidence, so it
    # survives a registry change -- and is what keeps a repeated evaluation of a
    # pass from issuing a second confirmation. Classification itself is never
    # cached: it is recomputed from the live registry on every call, so a
    # registry change is never served a stale verdict.
    _confirmations: dict[TestSnapshot, dict[str, TestSnapshot]] = field(
        default_factory=dict, init=False, repr=False
    )

    def capture_baseline(self, contract: ExecutionContract) -> TestSnapshot:
        """Run the required suite exactly once, before DEV."""
        baseline = self.runner.run(contract)
        self._baseline = baseline
        return baseline

    def evaluate_after_dev(
        self, contract: ExecutionContract, baseline: TestSnapshot
    ) -> CampaignResult:
        """Compare against the captured baseline and classify every failure.

        ``baseline`` must be the snapshot this campaign captured: a substituted
        (or never captured) baseline would silently corrupt the dispositions, so
        anything else raises :class:`CampaignError`.

        Classification is recomputed on every call from the live registry --
        never served from a cache -- so a registry change is picked up
        immediately. Each unlisted failed id still gets AT MOST ONE bounded
        confirmation re-run per pass snapshot: that runner outcome is memoised
        on (snapshot, id) the moment it is observed, so a repeated evaluation --
        or a retry after an error path -- reuses it instead of issuing another
        runner call.
        """
        if baseline is not self._baseline:
            raise CampaignError(
                "evaluate_after_dev requires the baseline captured by this campaign"
            )
        current = self.runner.run(contract)
        failed = set(current.failed_ids)
        declared = set(current.declared_ids)
        registered = {
            test_id for test_id in failed if self.flaky_registry.is_registered(test_id)
        }

        # A declared test that passed before and fails now is a regression,
        # independent of any registry entry: registry membership must never
        # subtract from this set ("a deterministic failure introduced by the
        # current change is a regression regardless of any entry").
        regressions = set(baseline.passed_ids) & failed
        # A registered known-flaky failure that did NOT regress runs
        # non-blocking and is recorded as flaky.
        flaky_ids = registered - regressions
        # A test that failed before and still fails is pre-existing, not
        # injected; a registered flake is dispositioned as flaky only.
        pre_existing = (set(baseline.failed_ids) & failed) - flaky_ids
        # A registered entry that a deterministic regression overtook is stale:
        # the regression stays blocking and goes to the fixer, while the id is
        # kept visible to the human for curation (fix-or-delete at expiry).
        stale_registered = registered & regressions

        reruns: dict[str, int] = {}
        candidates: list[str] = sorted(stale_registered)
        explained = regressions | pre_existing | flaky_ids
        memo = self._confirmations.setdefault(current, {})
        for test_id in sorted(failed - explained):
            # An id with no baseline history (new or undeclared) is the only
            # ambiguous case: exactly one bounded classification re-run per pass
            # snapshot. The outcome is memoised on (snapshot, id) the moment it
            # is observed, so a repeated evaluation -- or a retry after an error
            # path -- reuses it instead of issuing another runner call.
            confirmation = memo.get(test_id)
            if confirmation is None:
                confirmation = self.runner.run(contract)
                memo[test_id] = confirmation
            reruns[test_id] = 1
            if not declared <= set(confirmation.declared_ids):
                missing = sorted(declared - set(confirmation.declared_ids))
                raise CampaignError(
                    f"confirmation run omits declared test ids: {missing}"
                )
            if test_id in confirmation.failed_ids:
                regressions.add(test_id)
            else:
                candidates.append(test_id)

        return CampaignResult(
            snapshot=current,
            regressions=tuple(sorted(regressions)),
            pre_existing_failures=tuple(sorted(pre_existing)),
            flaky_ids=tuple(sorted(flaky_ids)),
            registry_candidates=tuple(sorted(set(candidates))),
            classification_reruns=reruns,
            pass_rate_gate_passed=not (failed - flaky_ids),
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
