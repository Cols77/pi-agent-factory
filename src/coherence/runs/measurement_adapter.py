"""Measurement-run source adapter.

Projects the durable validation report (``validation/validation-report.json``
written by ``coherence.measurement.cli.cmd_validate``) into unified
:class:`~coherence.runs.model.RunStatusInput` rows. Read-only; preserves the
native per-requirement pass/fail but never recomputes a measurement and never
synthesizes a raw artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

from substrate.observations import Diagnostic

from coherence.runs.model import RunStatusInput


def _state_from_requirements(reqs: list[object]) -> str:
    if not reqs:
        return "unknown"
    if any(isinstance(r, dict) and r.get("passed") is False for r in reqs):
        return "failed"
    if any(isinstance(r, dict) and "error" in r for r in reqs):
        return "unknown"
    return "passed"


def measurement_run_status(root: Path) -> list[RunStatusInput]:
    """Read the durable validation report as status inputs."""
    report_path = root / "validation" / "validation-report.json"
    if not report_path.is_file():
        return []
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [
            RunStatusInput(
                producer="measurement",
                run_id="validation-report",
                state="unknown",
                observation_ref="measurement:validation-report",
                diagnostics=(Diagnostic(code="MEASUREMENT_REPORT_MALFORMED", summary=str(exc)),),
                requirement_ids=(),
            )
        ]
    reqs = payload.get("requirements", []) if isinstance(payload, dict) else []
    return [
        RunStatusInput(
            producer="measurement",
            run_id=payload.get("run_id", "validation-report") if isinstance(payload, dict) else "validation-report",
            state=_state_from_requirements(reqs if isinstance(reqs, list) else []),
            observation_ref="measurement:validation-report",
            resume_cmd=None,
            updated_at=str(payload.get("generated_at", "")) if isinstance(payload, dict) else "",
            requirement_ids=(),
        )
    ]