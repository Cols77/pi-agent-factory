from __future__ import annotations

import json
from pathlib import Path

from factory.requirements.register import Binding
from factory.validation.assertions import evaluate_assertion
from factory.validation.harness import HarnessResult, TrialResult
from factory.validation.metrics.preemption import trial_preempted

# Per-trial scorers: (frames, window) -> bool. Rate = mean of the booleans.
_TRIAL_SCORERS = {
    "preemption_success_rate": trial_preempted,
}


class UnknownMetricError(ValueError):
    pass


class SimTestbenchHarness:
    """Increment-1 harness: score a static recorded trace fixture.

    Reads ``traces_dir / f"{binding.experiment}.json"`` shaped
    ``{"trials": [{"seed": int, "frames": [frame, ...]}, ...]}``.
    """

    def __init__(self, traces_dir: Path) -> None:
        self._traces_dir = traces_dir

    @classmethod
    def from_config(cls, params: dict, project_root: Path) -> "SimTestbenchHarness":
        return cls(project_root / params["traces_dir"])

    def run(self, binding: Binding, workdir: Path) -> HarnessResult:
        scorer = _TRIAL_SCORERS.get(binding.metric)
        if scorer is None:
            raise UnknownMetricError(f"no trial scorer for metric {binding.metric!r}")
        path = self._traces_dir / f"{binding.experiment}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        trials_raw = data["trials"]
        results: list[TrialResult] = []
        for tr in trials_raw:
            ok = scorer(tr["frames"], binding.window)
            results.append(TrialResult(seed=int(tr.get("seed", 0)), passed=bool(ok)))
        rate = (sum(1 for r in results if r.passed) / len(results)) if results else 0.0
        return HarnessResult(
            metric_value=rate,
            passed=evaluate_assertion(rate, binding.assert_expr),
            trials=results,
            artifacts=[],
            raw={"trace": str(path), "trials": len(results)},
        )
