"""Pure, neutral context-manifest validation.

Schema validation, agent-output normalization, and context-ref existence
checks are pure functions of the manifest and the repo root -- they need
nothing from `factory.evidence` or the orchestrator. Coverage-floor checks
and connector-based coherence checks are NOT pure (they read task bodies,
evaluate registered connectors, touch the filesystem for gates); the
factory-side caller supplies them as callables so this module never imports
`factory` or `coherence`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from substrate.validators.schema import SCHEMA_DIR, validate

_SCHEMA = SCHEMA_DIR / "context_manifest.schema.json"

_AGENT_JUNK_FIELDS = ("proven", "pass", "evidence")


def _strip_anchor(ref: str) -> str:
    return ref.split("#", 1)[0]


def normalize_manifest(manifest: dict) -> dict:
    """Tolerate agent output-format drift that the schema would otherwise reject.

    The context-gatherer prompt forbids self-reported verdict fields
    (``proven``/``pass``) and requires each check to have ``kind``/``args``,
    but flash-class models sometimes emit ``evidence``/``pass``-style checks
    anyway. Those fields are UNTRUSTED self-reports -- the caller derives the
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


def context_ref_errors(manifest: dict, repo_root: Path) -> list[str]:
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


def identity_errors(manifest: dict, task_id: str | None) -> list[str]:
    """The manifest's declared task_id must match the task it was gathered for.

    `task_id=None` means the caller has no task context (e.g. ad-hoc manifest
    validation outside a dispatched task) -- nothing to cross-check against.
    """
    if task_id is None:
        return []
    declared = manifest.get("task_id")
    if declared != task_id:
        return [f"task_id: manifest declares {declared!r}, but this is task {task_id!r}"]
    return []


def validate_manifest_document(
    manifest: dict,
    repo_root: Path,
    check_errors: Callable[[dict], list[str]],
    coverage_errors: Callable[[dict], list[str]],
    *,
    task_id: str | None = None,
) -> list[str]:
    """Two-layer coherence gate over a normalized manifest. The manifest
    passes iff this returns [].

    Agent-supplied `proven`/`pass`/`evidence` are silently stripped before
    schema validation -- they are untrusted self-reports. Schema validation
    gates everything else: on schema error, `check_errors`/`coverage_errors`
    are never invoked. Once the manifest is normalized and schema-valid,
    context-ref existence and task-id identity are checked, and
    `coverage_errors`/`check_errors` are invoked with the normalized manifest
    and their results merged in -- these two callables carry whatever
    caller-specific machinery (task bodies, evidence connectors, gate
    runners) produced them; this function knows only that each returns a
    list of error strings.
    """
    manifest = normalize_manifest(manifest)
    errors = validate(manifest, _SCHEMA)
    if errors:
        return errors

    out: list[str] = list(context_ref_errors(manifest, repo_root))
    out += identity_errors(manifest, task_id)
    out += coverage_errors(manifest)
    out += check_errors(manifest)
    return out
