from __future__ import annotations

from pathlib import Path

from factory.validation.schema_validator import SCHEMA_DIR, validate

_SCHEMA = SCHEMA_DIR / "context_manifest.schema.json"


def _strip_anchor(ref: str) -> str:
    return ref.split("#", 1)[0]


def validate_manifest(manifest: dict, repo_root: Path) -> list[str]:
    errors = validate(manifest, _SCHEMA)
    if errors:
        return errors

    coherence = manifest.get("coherence", {})
    if coherence.get("proven") is not True:
        return ["coherence.proven must be true for the gate to pass"]

    failing_checks = [
        c.get("name", "<unnamed>")
        for c in coherence.get("checks", [])
        if c.get("pass") is not True
    ]
    if failing_checks:
        return [f"coherence.proven is true but check(s) failed: {', '.join(failing_checks)}"]

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
