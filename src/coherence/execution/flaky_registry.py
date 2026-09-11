"""SR-034 human-only known-flaky registry (decision 1, 2026-09-11).

One JSON record per quarantined test lives at
``flaky-tests/<safe-test-id-slug>.json`` with schema ``1`` and the fields
``test_id``, ``reason``, ``decided_by``, ``decided_at`` and a nullable
``review_after`` expiry. There is no separate ``owner`` key: the entry's owner
*is* ``decided_by`` (the human who curated it) together with ``review_after``
(its expiry) -- the same owner/expiry pair the reused ``Deferral`` shape carries.

``read_flaky`` is the driver path and never writes. ``register_flaky`` is the
only writer, rejects every ``decided_by`` other than ``human``, validates the
safe slug and the exact test id, and writes atomically. Malformed, unsafe or
non-human records raise :class:`FlakyRegistryError` -- never a silent default.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from coherence.deferrals import _parse_instant

SCHEMA = 1
FLAKY_DIRNAME = "flaky-tests"
_SAFE_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_FIELDS = ("schema", "test_id", "reason", "decided_by", "decided_at", "review_after")


class FlakyRegistryError(RuntimeError):
    """A known-flaky record is malformed, unsafe, non-human, or absent."""


class FlakyNotRegisteredError(FlakyRegistryError):
    """No known-flaky record exists for the requested test id."""


@dataclass(frozen=True)
class FlakyRecord:
    """One human-curated known-flaky entry (``decided_by`` + ``review_after``)."""

    schema: int
    test_id: str
    reason: str
    decided_by: str
    decided_at: str
    review_after: str | None


def test_id_slug(test_id: str) -> str:
    """Deterministic safe slug for a pytest node id (never a path fragment)."""
    _validate_test_id(test_id)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", test_id).strip("-").lower()
    if not _SAFE_SLUG.match(slug):
        raise FlakyRegistryError(f"test id cannot be slugged safely: {test_id!r}")
    return slug


def flaky_path(root: Path, test_id: str) -> Path:
    """The one record path for a test id, proven to stay under ``flaky-tests/``."""
    slug = test_id_slug(test_id)
    flaky_dir = (root / FLAKY_DIRNAME).resolve()
    path = flaky_dir / f"{slug}.json"
    if not path.resolve().is_relative_to(flaky_dir):
        raise FlakyRegistryError(f"test id escapes the flaky-tests directory: {test_id!r}")
    return path


def read_flaky(root: Path, test_id: str) -> FlakyRecord:
    """Read the record for ``test_id`` (driver path). Never writes."""
    path = flaky_path(root, test_id)
    if not path.is_file():
        raise FlakyNotRegisteredError(f"no known-flaky record for {test_id!r}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FlakyRegistryError(f"{path.name}: not valid JSON") from exc
    return _validate_record(payload, test_id)


def is_registered_flaky(root: Path, test_id: str) -> bool:
    """Whether ``test_id`` is a registered known-flaky test (driver read path)."""
    try:
        read_flaky(root, test_id)
    except FlakyNotRegisteredError:
        return False
    return True


def register_flaky(
    root: Path,
    test_id: str,
    *,
    reason: str,
    decided_by: str,
    decided_at: str,
    review_after: str | None = None,
) -> FlakyRecord:
    """Human-only writer: validate, then atomically replace the record."""
    if decided_by != "human":
        raise FlakyRegistryError(f"decided_by must be 'human', got {decided_by!r}")
    record = _validate_record(
        {
            "schema": SCHEMA,
            "test_id": test_id,
            "reason": reason,
            "decided_by": decided_by,
            "decided_at": decided_at,
            "review_after": review_after,
        },
        test_id,
    )
    path = flaky_path(root, test_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, record)
    return record


def _validate_test_id(test_id: str) -> None:
    if not isinstance(test_id, str) or not test_id.strip():
        raise FlakyRegistryError("test id must be a non-blank string")
    if test_id.startswith(("/", "\\")) or "\\" in test_id or "\0" in test_id:
        raise FlakyRegistryError(f"unsafe test id: {test_id!r}")
    segments = test_id.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        raise FlakyRegistryError(f"unsafe test id (path escape): {test_id!r}")


def _aware_instant(value: str, field: str) -> datetime:
    """A validated, timezone-aware ISO instant; naive or non-ISO input raises."""
    try:
        _parse_instant(value)
    except ValueError as exc:
        raise FlakyRegistryError(f"invalid {field}: {value!r}") from exc
    normalized = value.strip()
    if normalized[-1] in "Zz":
        normalized = normalized[:-1] + "+00:00"
    if datetime.fromisoformat(normalized).tzinfo is None:
        raise FlakyRegistryError(f"{field} must carry a timezone offset: {value!r}")
    return _parse_instant(value)


def _validate_record(payload: object, requested_id: str) -> FlakyRecord:
    if not isinstance(payload, dict):
        raise FlakyRegistryError("flaky record must be a JSON object")
    unknown = set(payload) - set(_FIELDS)
    if unknown:
        raise FlakyRegistryError(f"unknown flaky record keys: {sorted(unknown)}")
    schema = payload.get("schema")
    if schema != SCHEMA:
        raise FlakyRegistryError(f"flaky record schema must be {SCHEMA}, got {schema!r}")
    decided_by = payload.get("decided_by")
    if decided_by != "human":
        raise FlakyRegistryError(f"decided_by must be 'human', got {decided_by!r}")
    test_id = payload.get("test_id")
    if not isinstance(test_id, str) or test_id != requested_id:
        raise FlakyRegistryError(
            f"flaky record test_id {test_id!r} does not match requested {requested_id!r}"
        )
    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise FlakyRegistryError("flaky record requires a non-blank reason")
    decided_at = payload.get("decided_at")
    if not isinstance(decided_at, str):
        raise FlakyRegistryError("flaky record requires a string decided_at")
    decided_instant = _aware_instant(decided_at, "decided_at")
    review_after = payload.get("review_after")
    if review_after is not None:
        if not isinstance(review_after, str):
            raise FlakyRegistryError("review_after must be an ISO instant or null")
        review_instant = _aware_instant(review_after, "review_after")
        if review_instant <= decided_instant:
            raise FlakyRegistryError(
                f"review_after {review_after!r} must be after decided_at {decided_at!r}"
            )
    return FlakyRecord(
        schema=SCHEMA,
        test_id=test_id,
        reason=reason,
        decided_by=decided_by,
        decided_at=decided_at,
        review_after=review_after,
    )


def _atomic_write(path: Path, record: FlakyRecord) -> None:
    payload = {
        "schema": record.schema,
        "test_id": record.test_id,
        "reason": record.reason,
        "decided_by": record.decided_by,
        "decided_at": record.decided_at,
        "review_after": record.review_after,
    }
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".flaky-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, indent=2)
            handle.write("\n")
        os.replace(tmp_name, str(path))
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


__all__ = [
    "FLAKY_DIRNAME",
    "SCHEMA",
    "FlakyNotRegisteredError",
    "FlakyRecord",
    "FlakyRegistryError",
    "flaky_path",
    "is_registered_flaky",
    "read_flaky",
    "register_flaky",
    "test_id_slug",
]
