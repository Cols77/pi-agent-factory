"""Audit-run source adapter.

Projects consolidated coverage-review runs (``coverage-reviews/<feat>-<run_id>``
with ``report.json`` / ``audit.json`` written by
``coherence.audit.cli.cmd_audit``/``cmd_consolidate``) into unified
:class:`~coherence.runs.model.RunStatusInput` rows. Read-only; preserves the
native feature/run identity and the report's own outcome, never recomputes an
audit, and never synthesizes a raw artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

from substrate.observations import Diagnostic

from coherence.runs.model import RunStatusInput


def _state_from_report(payload: dict[str, object]) -> str:
    # Audit state reflects how the run would gate. A run that never produced a
    # consolidated report with any SR is a diagnostic, not a pass.
    states = payload.get("states")
    if not isinstance(states, dict) or not states:
        return "unknown"
    failed = any(
        isinstance(entry, (list, tuple)) and entry and entry[0] in ("unlinked", "not_implemented", "dishonest")
        for entry in states.values()
    )
    if failed:
        return "failed"
    unknown = any(
        isinstance(entry, (list, tuple)) and entry and entry[0] in ("unverified", "suspect", "unmeasured", "declined")
        for entry in states.values()
    )
    if unknown:
        return "unknown"
    return "passed"


def _status_for_report(root: Path, feat: str, run_id: str, payload: dict[str, object]) -> RunStatusInput:
    obs_ref = f"audit:{feat}:{run_id}"
    return RunStatusInput(
        producer="audit",
        run_id=run_id,
        state=_state_from_report(payload),
        observation_ref=obs_ref,
        resume_cmd=(f"coherence audit run {feat} --project-root {root}" if _state_from_report(payload) != "passed" else None),
        updated_at=str(payload.get("generated_at", "")),
        requirement_ids=(),
    )


def audit_run_status(root: Path) -> list[RunStatusInput]:
    """Read every consolidated coverage-review run as status inputs."""
    reviews_dir = root / "coverage-reviews"
    if not reviews_dir.is_dir():
        return []
    rows: list[RunStatusInput] = []
    for run_dir in sorted(reviews_dir.glob("*")):
        if not run_dir.is_dir():
            continue
        feat, _, run_id = run_dir.name.partition("-")
        payload_path = run_dir / "report.json"
        if not payload_path.exists():
            payload_path = run_dir / "audit.json"
        if not payload_path.exists():
            rows.append(
                RunStatusInput(
                    producer="audit",
                    run_id=run_dir.name,
                    state="unknown",
                    observation_ref=f"audit:{run_dir.name}",
                    diagnostics=(
                        Diagnostic(code="AUDIT_RUN_NO_REPORT", summary="run dir has no report.json/audit.json"),
                    ),
                    requirement_ids=(),
                )
            )
            continue
        try:
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            rows.append(
                RunStatusInput(
                    producer="audit",
                    run_id=run_id,
                    state="unknown",
                    observation_ref=f"audit:{feat}:{run_dir.name}",
                    diagnostics=(Diagnostic(code="AUDIT_RUN_MALFORMED", summary=str(exc)),),
                    requirement_ids=(),
                )
            )
            continue
        rows.append(_status_for_report(root, feat, str(payload.get("run_id", run_id)), payload))
    return rows