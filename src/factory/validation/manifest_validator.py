from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from factory.evidence.connectors import DEFAULT_REGISTRY
from factory.evidence.coverage import coverage_errors as _evidence_coverage_errors
from factory.evidence.types import EvidenceContext
from substrate.validators.manifest import validate_manifest_document

if TYPE_CHECKING:
    from substrate.ledger.tasks import Task


def validate_manifest(
    manifest: dict,
    repo_root: Path,
    *,
    task: "Task | None" = None,
    ctx: EvidenceContext | None = None,
) -> list[str]:
    """Two-layer coherence gate. `coherence.proven` is DERIVED: the manifest
    passes iff this returns []. Agent-supplied `proven`/`pass`/`evidence`
    are silently stripped before schema validation -- they are untrusted
    self-reports. The real coherence gate (connector evaluation, coverage
    floor, context-ref existence) runs on the normalized manifest.

    Layer 1 (coverage) runs only when `task` is supplied. Layer 2 (connectors)
    always runs; `ctx` defaults to a repo-root-only context (dynamic connectors
    needing a gate runner then fail with a clear message).

    Delegates the pure schema/normalize/context-ref logic to
    `substrate.validators.manifest.validate_manifest_document`, injecting
    connector evaluation and coverage-floor checks as callables since both
    depend on `factory.evidence` machinery substrate must not import.
    """
    if ctx is None:
        ctx = EvidenceContext(repo_root=repo_root, gates=None, kb_dir=repo_root / "kb")

    def _check_errors(normalized: dict) -> list[str]:
        checks = normalized.get("coherence", {}).get("checks", [])
        return DEFAULT_REGISTRY.evaluate_checks(checks, ctx)

    def _coverage_errors(normalized: dict) -> list[str]:
        if task is None:
            return []
        return _evidence_coverage_errors(task.body, normalized.get("context", {}), repo_root)

    return validate_manifest_document(manifest, repo_root, _check_errors, _coverage_errors)


__all__ = ["validate_manifest"]
