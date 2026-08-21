from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import frontmatter

from coherence.register.register import content_checksum, parse_requirement


class ReasonRequiredError(ValueError):
    """A disposition or reaffirmation was attempted with a blank reason."""


class UnboundRequirementError(ValueError):
    """A reaffirmation was attempted against a requirement that has no binding."""


def _require_reason(reason: str) -> str:
    reason = reason.strip()
    if not reason:
        raise ReasonRequiredError("a reason is required and cannot be blank")
    return reason


def stamp_checksum(path: Path) -> None:
    """Recompute a requirement's checksum from what is on disk and write it."""
    post = frontmatter.load(str(path))
    post["checksum"] = content_checksum(parse_requirement(path))
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


def write_binding(
    path: Path,
    *,
    experiment: str,
    metric: str,
    assert_expr: str,
    harness: str | None,
    trials: int,
    window: dict | None,
) -> None:
    """Write an explicit binding and stamp its current checksum."""
    post = frontmatter.load(str(path))
    existing = post.get("binding")
    binding: dict = dict(existing) if isinstance(existing, dict) else {}
    binding.update({"experiment": experiment, "metric": metric, "assert": assert_expr, "trials": trials})
    if harness is not None:
        binding["harness"] = harness
    if window is not None:
        binding["window"] = window
    post["binding"] = binding
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    stamp_checksum(path)


def reaffirm(path: Path, reason: str) -> None:
    """Re-judge a stale binding as current, recording the explicit reason."""
    reason = _require_reason(reason)
    if parse_requirement(path).binding is None:
        raise UnboundRequirementError(f"{path.stem}: proposed requirement has no binding to reaffirm")
    post = frontmatter.load(str(path))
    post["reaffirmed"] = {
        "reason": reason,
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    stamp_checksum(path)


def write_deferral(path: Path, reason: str) -> None:
    """Record a deliberate deferral without changing the checksum."""
    reason = _require_reason(reason)
    post = frontmatter.load(str(path))
    post["trace_deferred"] = reason
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


__all__ = [
    "ReasonRequiredError",
    "UnboundRequirementError",
    "reaffirm",
    "stamp_checksum",
    "write_binding",
    "write_deferral",
]
