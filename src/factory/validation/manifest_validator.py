from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from factory.evidence.connectors import DEFAULT_REGISTRY
from factory.evidence.coverage import coverage_errors
from factory.evidence.types import EvidenceContext
from factory.validation.schema_validator import SCHEMA_DIR, validate

if TYPE_CHECKING:
    from factory.orchestrator.ledger import Task

_SCHEMA = SCHEMA_DIR / "context_manifest.schema.json"


def _strip_anchor(ref: str) -> str:
    return ref.split("#", 1)[0]


_AGENT_JUNK_FIELDS = ("proven", "pass", "evidence")


def _normalize_manifest(manifest: dict) -> dict:
    """Tolerate agent output-format drift that the schema would otherwise reject.

    The context-gatherer prompt forbids self-reported verdict fields
    (``proven``/``pass``) and requires each check to have ``kind``/``args``,
    but flash-class models sometimes emit ``evidence``/``pass``-style checks
    anyway. Those fields are UNTRUSTED self-reports -- the factory derives the
    verdict itself -- so they are stripped, never trusted:

    - ``coherence.proven`` and ``coherence.pass`` are removed.
    - Each check keeps only ``name``/``kind``/``args``; stray ``evidence``/
      ``pass`` fields are removed.
    - Checks that still lack ``kind`` or ``args`` cannot be evaluated and are
      dropped entirely (they carry no machine-verifiable claim).

    The real coherence gate -- connector evaluation of the surviving checks,
    the Modify:-coverage floor, and context-ref existence -- still runs on the
    normalized manifest, so hollow manifests buy nothing.
    """
    coherence = manifest.get("coherence")
    if not isinstance(coherence, dict):
        return manifest

    for junk in _AGENT_JUNK_FIELDS:
        coherence.pop(junk, None)

    raw_checks = coherence.get("checks", [])
    if isinstance(raw_checks, list):
        kept: list[dict] = []
        for check in raw_checks:
            if not isinstance(check, dict):
                continue
            clean = {k: v for k, v in check.items() if k not in _AGENT_JUNK_FIELDS}
            if "kind" in clean and "args" in clean:
                kept.append(clean)
        coherence["checks"] = kept

    return manifest


def _context_ref_errors(manifest: dict, repo_root: Path) -> list[str]:
    ctx = manifest.get("context", {})
    refs: list[str] = []
    if ctx.get("task"):
        refs.append(ctx["task"])
    if ctx.get("prior_session"):
        refs.append(ctx["prior_session"])
    for key in ("source_files", "spec", "plan"):
        refs.extend(ctx.get(key, []))
    missing: list[str] = []
    for ref in refs:
        rel = _strip_anchor(ref)
        if not (repo_root / rel).exists():
            missing.append(f"context path missing: {rel}")
    return missing


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
    needing a gate runner then fail with a clear message)."""
    manifest = _normalize_manifest(manifest)
    errors = validate(manifest, _SCHEMA)
    if errors:
        return errors

    if ctx is None:
        ctx = EvidenceContext(repo_root=repo_root, gates=None, kb_dir=repo_root / "kb")

    out: list[str] = []
    if task is not None:
        out += coverage_errors(task.body, manifest.get("context", {}), repo_root)
    checks = manifest.get("coherence", {}).get("checks", [])
    out += DEFAULT_REGISTRY.evaluate_checks(checks, ctx)
    out += _context_ref_errors(manifest, repo_root)
    return out
