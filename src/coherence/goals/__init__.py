"""Goals core for the engineering-context layer.

A `goal` is a first-class engineering contract (spec §13 lifecycle, brief §5.3
measurable contract), not a natural-language wish. The package is additive on
top of v1: it reuses `factory.trace.model`, `factory.system` claims/freshness
and `factory.trace.validation_status`, and never re-writes existing surface.
"""

