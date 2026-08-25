"""Canonical serialization for the unified long-run mission-control protocol.

``coherence.runs.transport.serialize_run_statuses`` is the sole public JSON
entrypoint. ``coherence status --json`` calls it and the extension fixture
consumes its payload shape; no second serializer may be maintained elsewhere.

Contract (Increment 7 addendum):

- Input is the public ``RunStatus`` rows in service sort order; the internal
  ``RunStatusInput`` carrier is never exposed here.
- Each emitted row carries the public fields, including ``blocking_obligation``,
  ``blocking_obligation_resolve_cmd``, ``rerun_allowed`` and ``resume_cmd``.
- A Python ``None`` ``resume_cmd`` is always emitted as JSON ``null``, never
  omitted.
- ``blocking_obligation_resolve_cmd`` -- the structured ``tuple[str, ...]`` -- is
  preserved as a JSON array (or ``null``), never flattened into a string.
- The internal ``requirement_ids`` carrier is omitted.
"""

from __future__ import annotations

from collections.abc import Iterable

from coherence.runs.model import RunStatus


def _run_row(status: RunStatus) -> dict[str, object]:
    return {
        "producer": status.producer,
        "run_id": status.run_id,
        "state": status.state,
        "observation_ref": status.observation_ref,
        "artifacts": [
            {
                "ref": ref.ref,
                "kind": ref.kind,
                "location": ref.location,
                "content_hash": ref.content_hash,
                "scope_refs": list(ref.scope_refs),
                "media_type": ref.media_type,
            }
            for ref in status.artifacts
        ],
        "resume_cmd": status.resume_cmd,
        "updated_at": status.updated_at,
        "diagnostics": [
            {
                "code": diagnostic.code,
                "summary": diagnostic.summary,
            }
            for diagnostic in status.diagnostics
        ],
        "terminal_observation_id": status.terminal_observation_id,
        "blocking_obligation": status.blocking_obligation,
        "blocking_obligation_resolve_cmd": (
            list(status.blocking_obligation_resolve_cmd)
            if status.blocking_obligation_resolve_cmd is not None
            else None
        ),
        "rerun_allowed": status.rerun_allowed,
    }


def serialize_run_statuses(statuses: Iterable[RunStatus]) -> dict[str, object]:
    """Return ``{"runs": [...]}`` in the service's sort order."""
    return {"runs": [_run_row(status) for status in statuses]}