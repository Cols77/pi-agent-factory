"""Gate resolution service: short-circuit on a durable decision.

`resolve_gate` answers "what action should a gate take?". If a valid
`DecisionFile` already exists for the gate it returns that gate's resolved
action without requiring any new authoring (the short-circuit that makes an
explicit durable decision the single source of truth). If none exists it is
up to the caller to author a file -- in unattended mode there is no human
available, so the gate resolves to ``"blocked"``.

``--no-gates`` is the sole explicit opt-out and is handled by the caller /
CLI, not by this service.
"""
from __future__ import annotations

from pathlib import Path

from coherence.gate.model import Decision
from coherence.gate.store import decision_path, load_decision

#: Resolved action returned when a gate has no decision file and runs without
#: a human available to author one.
GATE_BLOCKED = "blocked"

#: Resolved action when every decision accepts.
GATE_ACCEPT = "accept"


def resolve_gate(run_dir: Path | str, gate_id: str, *, unattended: bool) -> str | None:
    """Return the resolved action for one assurance gate.

    * A valid `DecisionFile` exists: load it (a corrupt file surfaces the
      typed `CorruptDecisionFile` diagnostic, never a silent re-author) and
      return its resolved action -- short-circuit; nothing new is authored.
    * No file and ``unattended=False``: return ``None``; it is up to the
      caller to author a file via `write_decision`.
    * No file and ``unattended=True``: return ``"blocked"``.

    `--gates` off is the caller's explicit opt-out; this service never treats
    it as a decision.
    """
    path = decision_path(run_dir, gate_id)
    if not path.is_file():
        return GATE_BLOCKED if unattended else None
    file = load_decision(path)
    return _resolved_action(file.decisions)


def _resolved_action(decisions: tuple[Decision, ...]) -> str:
    """Collapse a decision set to one gate-level action.

    Any ``reject`` blocks the gate; else any ``defer`` defers it; else the
    gate accepts. Deterministic: first occurrence wins for ties but the
    precedence is fixed (reject > defer > accept).
    """
    if any(d.action == "reject" for d in decisions):
        return "reject"
    if any(d.action == "defer" for d in decisions):
        return "defer"
    return GATE_ACCEPT