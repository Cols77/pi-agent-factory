"""RunSource Protocol -- read-only access to durable run producers.

``coherence.runs.store`` defines the single source interface the runs service
aggregates. Each concrete source (factory / audit / measurement / simulation /
experiment) implements ``iter_status_inputs``; adapters never expose a writer
and never perform service assembly -- they hand the internal
``RunStatusInput`` carrier to ``coherence.runs.service`` which is the only
owner that converts it to the public ``RunStatus``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from coherence.runs.model import RunStatusInput


@runtime_checkable
class RunSource(Protocol):
    """A durable run producer exposing status inputs, never a writer."""

    def iter_status_inputs(self) -> Iterable[RunStatusInput]:
        """Yield this source's run lifecycle inputs in deterministic order."""
        ...