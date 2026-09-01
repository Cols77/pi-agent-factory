from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from coherence.measurement.harness import Harness
from coherence.measurement.sim_harness import SimTestbenchHarness
from coherence.register.register import (
    Requirement,
    get_requirement,
    is_checksum_current,
)

__all__ = [
    "HarnessFor",
    "ValidationReportWriteError",
    "default_harness_for",
    "harness_provenance",
    "run_requirement_validation",
    "write_validation_report",
]


class ValidationReportWriteError(OSError):
    """The validation report could not be written, so the file on disk does
    not describe the run that just happened. Raised rather than swallowed --
    see :func:`write_validation_report`."""

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
        if req.binding.harness is None:
            # The measurement is decided, but the harness does not exist yet.
            # This is intentional (a WARNING state), but validation cannot proceed.
            entries.append(
                {"id": req.id, "error": "binding: no harness named yet"}
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


def harness_provenance(command: str, *, now: str | None = None) -> dict:
    """The provenance block for a report this code actually produced.

    ``recorded_by: "harness"`` is a claim only the producing code may make,
    so it is stamped here -- at the one place a validation report is built
    from a real ``run_requirement_validation`` sweep -- and never written by
    hand. A hand-recorded report says ``recorded_by: "hand"`` and must cite
    the run it transcribes; see
    ``src/substrate/schemas/validation_report.schema.json``.
    """
    return {
        "recorded_by": "harness",
        "recorded_at": now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": command,
    }


def write_validation_report(path: Path, report: dict) -> None:
    """Write the validation report atomically, or raise.

    Important 1 (review round 3): this used to swallow ``OSError``. A failed
    write left the *previous* report -- possibly one that says an SR passed --
    in place while the caller carried on as though the new one had landed,
    which is a stale claim presented as a current one (I-02). There is no
    honest "best effort" here: either the report on disk is the report just
    produced, or the caller must be told it is not.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        raise ValidationReportWriteError(
            f"could not write the validation report to {path}: {exc}. The report on "
            "disk (if any) is now stale and does not describe this run"
        ) from exc
