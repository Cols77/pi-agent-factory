"""Factory-run source adapter.

Projects the durable factory run session store -- ``sessions/.factory-runs/``
``by-session`` (each a ``journal.jsonl`` + ``checkpoint.json`` written by
``factory.orchestrator.journal.RunJournal``) -- into unified
:class:`~coherence.runs.model.RunStatusInput` rows, preserving native identity
and a real resume command for interrupted runs. Read-only; never synthesizes a
raw artifact and never centralises data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from substrate.observations import Diagnostic

from coherence.runs.model import RunStatusInput
from factory.orchestrator.journal import RunJournal


def _state_from_node(node: str, interruption: str | None) -> str:
    if node in ("completed", "closed"):
        return "passed"
    if interruption or node in ("interrupted", "abandoned"):
        return "interrupted"
    return "running"


def _status_for_dir(root: Path, run_dir: Path) -> RunStatusInput:
    run_id = run_dir.name
    journal = RunJournal(run_dir)
    checkpoint = journal.latest()
    node = checkpoint.node if checkpoint is not None else "unknown"
    interruption = checkpoint.interruption if checkpoint is not None else None
    state = _state_from_node(node, interruption)
    updated_at = checkpoint.head_commit or "" if checkpoint is not None else ""
    return RunStatusInput(
        producer="factory",
        run_id=run_id,
        state=state,
        observation_ref=f"run:{run_id}",
        resume_cmd=(
            f"{sys.executable} -m factory.orchestrator run-state inspect {run_id} --repo {root}"
        )
        if state == "interrupted"
        else None,
        updated_at=updated_at,
        requirement_ids=(),
    )


def factory_run_status(root: Path) -> list[RunStatusInput]:
    """Read every durable factory run session as status inputs.

    A directory with a corrupt checkpoint degrades to ``unknown`` plus a
    diagnostic rather than raising -- a malformed source is not a pass.
    """
    by_session = root / "sessions" / ".factory-runs" / "by-session"
    if not by_session.is_dir():
        return []
    rows: list[RunStatusInput] = []
    for run_dir in sorted(by_session.glob("*")):
        if not run_dir.is_dir():
            continue
        try:
            rows.append(_status_for_dir(root, run_dir))
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            rows.append(
                RunStatusInput(
                    producer="factory",
                    run_id=run_dir.name,
                    state="unknown",
                    observation_ref=f"run:{run_dir.name}",
                    diagnostics=(Diagnostic(code="FACTORY_RUN_MALFORMED", summary=str(exc)),),
                    requirement_ids=(),
                )
            )
    return rows