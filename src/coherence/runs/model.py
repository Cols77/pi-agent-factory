"""Coherence long-run unified status: the frozen source-discriminated model.

Increment 7 (Tasks 1, 2, 3, 5 + addendum) presents factory, audit, measurement,
simulation and experiment runs through one status protocol and mission-control
surface while preserving every native durable store and raw artifact reference.

This module owns two frozen contracts:

- ``RunStatusInput`` (addendum) -- the INTERNAL carrier that source adapters
  return to the service. It carries ``requirement_ids`` (the native requirement
  id list; only the simulation adapter populates it today) plus diagnostics and
  terminal-observation identity. It is internal; service.py is the only owner
  that reads it and converts it into the public object. ``requirement_ids`` is
  not a ``RunStatus`` field and is not a serialized JSON key.

- ``RunStatus`` (Task 1) -- the PUBLIC, obligation-enriched status row. The
  status probe, ``coherence status --json``, ``coherence.runs.transport`` and
  the extension all consume this shape.

Neither type inspects file mtimes nor modifies an artifact; the adapters only
project existing source records into these values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from substrate.artifacts import ArtifactRef
from substrate.observations import Diagnostic

__all__ = ["RunStatus", "RunStatusInput", "Producer", "RunState"]

Producer = Literal["factory", "audit", "measurement", "simulation", "experiment"]
RunState = Literal["running", "interrupted", "passed", "failed", "unknown"]

_PRODUCERS: frozenset[str] = frozenset(
    {"factory", "audit", "measurement", "simulation", "experiment"}
)
_STATES: frozenset[str] = frozenset(
    {"running", "interrupted", "passed", "failed", "unknown"}
)


def _validate_state_run(producer: str, run_id: str, state: str, observation_ref: str) -> None:
    if producer not in _PRODUCERS:
        raise ValueError(f"producer must be one of {sorted(_PRODUCERS)}")
    if not run_id or not run_id.strip():
        raise ValueError("run_id must be a nonblank string")
    if state not in _STATES:
        raise ValueError(f"state must be one of {sorted(_STATES)}")
    if not observation_ref or not observation_ref.strip():
        raise ValueError("observation_ref must be a nonblank string")
    if state in ("passed", "failed") and not observation_ref:
        raise ValueError("a terminal run requires an observation reference")


def _validate_artifacts(artifacts: tuple[ArtifactRef, ...]) -> None:
    seen: list[str] = []
    for ref in artifacts:
        if ref.ref in seen:
            raise ValueError(f"duplicate artifact ref: {ref.ref}")
        seen.append(ref.ref)


@dataclass(frozen=True)
class RunStatusInput:
    """Internal source-adapter carrier consumed only by the runs service.

    Adapters return this, never a partially-assembled ``RunStatus``.
    ``requirement_ids`` is immutable internal carrier data -- the native
    requirement id list (simulation only today) -- read by
    ``coherence.runs.service`` to compute the three obligation fields. It is
    NOT a ``RunStatus`` field and is never serialised.
    """

    producer: str
    run_id: str
    state: str
    observation_ref: str
    artifacts: tuple[ArtifactRef, ...] = ()
    resume_cmd: str | None = None
    updated_at: str = ""
    diagnostics: tuple[Diagnostic, ...] = ()
    terminal_observation_id: str | None = None
    requirement_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_state_run(self.producer, self.run_id, self.state, self.observation_ref)
        _validate_artifacts(self.artifacts)


@dataclass(frozen=True)
class RunStatus:
    """Public, immutable, obligation-enriched one-row status."""

    producer: str
    run_id: str
    state: str
    observation_ref: str
    artifacts: tuple[ArtifactRef, ...] = ()
    resume_cmd: str | None = None
    updated_at: str = ""
    diagnostics: tuple[Diagnostic, ...] = ()
    terminal_observation_id: str | None = None
    blocking_obligation: str | None = None
    blocking_obligation_resolve_cmd: tuple[str, ...] | None = None
    rerun_allowed: bool = False

    def __post_init__(self) -> None:
        _validate_state_run(self.producer, self.run_id, self.state, self.observation_ref)
        _validate_artifacts(self.artifacts)