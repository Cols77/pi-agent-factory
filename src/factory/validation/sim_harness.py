from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from factory.requirements.register import Binding
from factory.validation.assertions import evaluate_assertion
from factory.validation.harness import HarnessResult, TrialResult
from factory.validation.scorer_registry import load_scorers


class UnknownMetricError(ValueError):
    pass


class SimTestbenchHarness:
    """Increment-1 harness: score a static recorded trace fixture.

    Reads ``traces_dir / f"{binding.experiment}.json"`` shaped
    ``{"trials": [{"seed": int, "frames": [frame, ...]}, ...]}``.
    """

    def __init__(
        self, traces_dir: Path, scorers: dict[str, Callable[..., bool]] | None = None
    ) -> None:
        self._traces_dir = traces_dir
        # Per-trial scorers: (frames, window) -> bool. Rate = mean of the booleans.
        # An empty map means the target project has implemented no metrics yet.
        self._scorers = scorers if scorers is not None else {}

    @classmethod
    def from_config(cls, params: dict, project_root: Path) -> "SimTestbenchHarness":
        return cls(
            project_root / params["traces_dir"],
            load_scorers(params.get("scorers"), project_root),
        )

    def run(self, binding: Binding, workdir: Path) -> HarnessResult:
        scorer = self._scorers.get(binding.metric)
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
