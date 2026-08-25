"""Unified long-run mission-control surface over durable run producers.

Present factory, audit, measurement, simulation and experiment runs through one
status protocol while preserving every native durable store and raw artifact
reference. The adapters in this package read only existing source records
(checkpoints, journals, coverage reviews, validation reports, simulation
registry/evidence) and attach existing observation refs -- never synthesizing
raw artifacts or centralizing data -- and ``coherence.runs.service`` is the
sole integration registry.
"""

from coherence.runs.model import RunState, RunStatus, RunStatusInput
from coherence.runs.store import RunSource

__all__ = ["RunState", "RunStatus", "RunStatusInput", "RunSource"]