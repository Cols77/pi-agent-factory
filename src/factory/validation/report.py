from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from factory.requirements.register import (
    Requirement,
    get_requirement,
    is_checksum_current,
)
from factory.validation.harness import Harness
from factory.validation.sim_harness import SimTestbenchHarness

HarnessFor = Callable[[str], Harness]


def default_harness_for(
    traces_dir: Path, scorers: dict[str, Callable[..., bool]] | None = None
) -> HarnessFor:
    def _factory(harness_name: str) -> Harness:
        if harness_name == "sim-testbench":
            return SimTestbenchHarness(traces_dir, scorers)
        raise ValueError(f"unknown harness: {harness_name}")

    return _factory


def run_requirement_validation(
    satisfies: list[str],
    reqs: list[Requirement],
    harness_for: HarnessFor,
    workdir: Path,
) -> dict:
    entries: list[dict] = []
    for req_id in satisfies:
        req = get_requirement(reqs, req_id)
        if req is None:
            entries.append({"id": req_id, "error": "unknown requirement"})
            continue
        if req.binding is None:
            # Reached only when a task names a proposed requirement directly.
            # An honest error beats an AttributeError from deep in the harness.
            entries.append(
                {"id": req.id, "error": "proposed requirement: no binding to validate"}
            )
            continue
        try:
            harness = harness_for(req.binding.harness)
            result = harness.run(req.binding, workdir)
        except Exception as exc:  # isolate a bad harness/metric/trace to this requirement
            entries.append({"id": req.id, "error": str(exc)})
            continue
        actual_trials = len(result.trials)
        entries.append(
            {
                "id": req.id,
                "domain": req.domain,
                "metric": req.binding.metric,
                "value": result.metric_value,
                "assert": req.binding.assert_expr,
                "passed": result.passed and actual_trials >= req.binding.trials,
                "trials": actual_trials,
                "declared_trials": req.binding.trials,
                "stale": not is_checksum_current(req),
                "artifacts": [str(a) for a in result.artifacts],
            }
        )
    return {"requirements": entries}


def write_validation_report(path: Path, report: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass  # best-effort, mirrors review_guide.write_review_guide
