from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import frontmatter

from factory.requirements.register import content_checksum, parse_requirement


class ReasonRequiredError(ValueError):
    """A disposition or reaffirmation was attempted with a blank reason.

    Both are judgement calls that must be recorded, not silently accepted --
    an empty reason is indistinguishable from no reason at all.
    """


def _require_reason(reason: str) -> str:
    reason = reason.strip()
    if not reason:
        raise ReasonRequiredError("a reason is required and cannot be blank")
    return reason


def _stamp_checksum(path: Path) -> None:
    # Re-read so the checksum covers exactly what is on disk.
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
    """Decide a requirement's measurement, and stamp a checksum that is current by construction.

    The only place a binding is written: `harness` and `window` are omitted
    entirely when absent, since `harness: null` and "no harness key" would
    otherwise be two on-disk spellings of the same "not decided yet" state.
    """
    binding: dict = {"experiment": experiment, "metric": metric, "assert": assert_expr, "trials": trials}
    if harness is not None:
        binding["harness"] = harness
    if window is not None:
        binding["window"] = window
    post = frontmatter.load(str(path))
    post["binding"] = binding
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    _stamp_checksum(path)


def reaffirm(path: Path, reason: str) -> None:
    """Re-judge a stale requirement's binding as still correct, without changing it.

    Records who decided that and why -- `reaffirmed` -- so a later reader can
    see the checksum was re-stamped on purpose, not silently kept current.
    """
    reason = _require_reason(reason)
    post = frontmatter.load(str(path))
    post["reaffirmed"] = {
        "reason": reason,
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    _stamp_checksum(path)


def write_deferral(path: Path, reason: str) -> None:
    """Record that a requirement is deliberately not yet being delivered.

    A disposition, not a measurement: it never touches the checksum, so it
    cannot stale a requirement that is already bound.
    """
    reason = _require_reason(reason)
    post = frontmatter.load(str(path))
    post["trace_deferred"] = reason
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
