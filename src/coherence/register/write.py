from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

import frontmatter

from coherence.register.register import content_checksum, parse_requirement


class ReasonRequiredError(ValueError):
    """A disposition or reaffirmation was attempted with a blank reason."""


class UnboundRequirementError(ValueError):
    """A reaffirmation was attempted against a requirement that has no binding."""


_ID_RE = re.compile(r"SR-(\d+)")


def _next_requirement_id(requirements_dir: Path) -> str:
    numbers = [
        int(match.group(1))
        for path in requirements_dir.glob("SR-*.md")
        if (match := _ID_RE.search(path.name))
    ]
    return f"SR-{(max(numbers) + 1) if numbers else 1:03d}"


def write_proposed_requirement(
    requirements_dir: Path,
    *,
    source: str,
    title: str,
    statement: str,
    domain: str,
) -> Path:
    """Write a proposed requirement and return its allocated path."""
    requirements_dir.mkdir(parents=True, exist_ok=True)
    req_id = _next_requirement_id(requirements_dir)
    post = frontmatter.Post(
        "\n## Rationale\n",
        id=req_id,
        title=title,
        statement=statement,
        domain=domain,
        upstream=[],
        source=source,
    )
    path = requirements_dir / f"{req_id}.md"
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path


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


def write_deferral(
    path: Path,
    reason: str,
    *,
    review_after: str | None = None,
    decided_at: str | None = None,
    decided_by: str | None = None,
) -> None:
    """Record a deliberate deferral without changing the checksum.

    Bread-and-butter (legacy) write of just a ``reason`` persists the bare
    scalar ``trace_deferred: <reason>`` unchanged. Supplying any of
    ``review_after``/``decided_at``/``decided_by`` switches to the structured
    dict form carrying that expiring/attestation metadata (Inc 6 Task 3).
    """
    reason = _require_reason(reason)
    post = frontmatter.load(str(path))
    if review_after is None and decided_at is None and decided_by is None:
        post["trace_deferred"] = reason
    else:
        structured = {"reason": reason}
        if review_after is not None:
            structured["review_after"] = review_after
        if decided_at is not None:
            structured["decided_at"] = decided_at
        if decided_by is not None:
            structured["decided_by"] = decided_by
        post["trace_deferred"] = structured
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


__all__ = [
    "ReasonRequiredError",
    "UnboundRequirementError",
    "reaffirm",
    "stamp_checksum",
    "write_binding",
    "write_deferral",
    "write_proposed_requirement",
]
