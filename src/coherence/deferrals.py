"""Deferral migration value object (Increment 6 Task 3).

Historically ``trace_deferred`` was a bare reason scalar stored in artifact
frontmatter. This module adds the shared ``Deferral`` value object and a
``parse_deferral`` reader that accepts BOTH the legacy scalar and a structured
dict form carrying ``review_after``/``decided_at``/``decided_by``, so a
deferral can carry an expiry.

Reader-first contract (spec section on expiring deferrals): every reader defers
to ``parse_deferral`` so the two forms render the same present deferral; only
a structured, DUE deferral (``review_after`` at/before ``now``) is reported as
expired; a legacy scalar never expires. Unknown / malformed shapes are REJECTED
(raise) -- never silently treated as current. Expiration here is a pure query
(``deferral_is_due``); it never rewrites or clears an artifact's frontmatter.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from coherence.gate.model import _is_iso


def _parse_instant(value: str) -> datetime:
    """Parse a declared ISO form and normalize it to an aware UTC datetime."""
    if not isinstance(value, str) or not _is_iso(value):
        raise ValueError(f"not an ISO-8601 instant: {value!r}")
    s = value.strip()
    if s[-1] in "Zz":
        s = s[:-1] + "+00:00"
    try:
        instant = datetime.fromisoformat(s)
    except ValueError as exc:
        raise ValueError(f"not an ISO-8601 instant: {value!r}") from exc
    if instant.tzinfo is None:
        return instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(timezone.utc)


@dataclass(frozen=True)
class Deferral:
    """A parsed deferral. ``reason`` is required; the rest are optional and
    verbatim ISO strings. ``review_after`` is the expiry instant.
    """

    reason: str
    review_after: str | None = None
    decided_at: str | None = None
    decided_by: str | None = None


def parse_deferral(raw: object) -> Deferral:
    """Parse a ``trace_deferred`` value into a `Deferral`.

    * ``str`` (legacy scalar) -> ``Deferral(reason=raw)``.
    * ``Mapping`` with a non-blank ``reason`` (plus optional
      ``review_after``/``decided_at``/``decided_by``) -> ``Deferral``.
    * anything else (non-string, non-dict, empty dict, dict without a non-blank
      ``reason``) raises `ValueError` -- it is rejected, not seen as "no
      deferral / current".
    """
    if isinstance(raw, str):
        if not raw.strip():
            raise ValueError("deferral reason may not be blank")
        return Deferral(reason=raw)
    if isinstance(raw, dict):
        reason = raw.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("structured deferral requires a non-blank `reason`")
        review_after = raw.get("review_after")
        decided_at = raw.get("decided_at")
        decided_by = raw.get("decided_by")
        for key, val in (
            ("review_after", review_after),
            ("decided_at", decided_at),
            ("decided_by", decided_by),
        ):
            if val is not None and not isinstance(val, str):
                raise ValueError(f"structured deferral `{key}` must be a string")
        # Validate any present review_after is a real ISO instant.
        if review_after is not None:
            _parse_instant(review_after)
        return Deferral(
            reason=reason,
            review_after=review_after,
            decided_at=decided_at,
            decided_by=decided_by,
        )
    raise ValueError(f"trace_deferred must be a string or mapping, got {raw!r}")


def deferral_is_due(deferral: Deferral, now: str) -> bool:
    """Whether a deferral has expired as of ``now``.

    Only a deferral that declares a ``review_after`` can be due; a legacy
    scalar (no ``review_after``) is never due. Pure read -- never mutates the
    artifact.
    """
    if not deferral.review_after:
        return False
    return _parse_instant(deferral.review_after) <= _parse_instant(now)


__all__ = ["Deferral", "parse_deferral", "deferral_is_due"]