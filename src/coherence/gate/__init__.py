"""Explicit durable gate decisions (Coherence Increment 6, Task 1).

Every assurance gate requires an explicit durable decision. This package
provides the versioned ``DecisionFile`` model, the atomic store, and the
``resolve_gate`` service that short-circuits re-prompting when a valid
decision file already exists for a gate.
"""
from __future__ import annotations

from coherence.gate.content import artifact_content_checksum, resolve_decision_currency
from coherence.gate.model import (
    CorruptDecisionFile,
    Decision,
    DecisionFile,
    DecisionValidationError,
    validate_decisions,
)
from coherence.gate.service import resolve_gate
from coherence.gate.store import decision_path, load_decision, write_decision

__all__ = [
    "CorruptDecisionFile",
    "Decision",
    "DecisionFile",
    "DecisionValidationError",
    "validate_decisions",
    "resolve_gate",
    "decision_path",
    "load_decision",
    "write_decision",
    "artifact_content_checksum",
    "resolve_decision_currency",
]