"""Schema for the `validation/validation-report.json` requirement-validation
report -- the store that feeds the ``executed_evidence`` health dimension.

Deliberately the same shape as :mod:`substrate.evidence.model`, which gives
``evidence/runs/*.json`` its ``validate_run_manifest``: the JSON Schema lives
in ``src/substrate/schemas/``, this module resolves it once and exposes one
``validate_*`` function that raises ``ValueError`` naming every violation.

Why this exists (review round 3, Critical 2). The report was read with no
shape check at all, and the copy in this repository was hand-authored: its
entries carry harness-output fields (``metric``, ``assert``, ``trials``,
``declared_trials``, ``passed``, ``stale``) that **no code in this repository
can produce** for the SRs concerned, because every one of them is
binding-less and ``run_requirement_validation`` returns an error entry and
exits before measuring. That made it derived state with no derivation (I-10)
whose fields assert a measurement nothing computed (I-02).

The schema closes both halves:

* every report must carry a ``provenance`` block naming who or what recorded
  it and with what command, and any non-``harness`` ``recorded_by`` value
  (``hand`` or ``agent``) must cite the run id, commit and evidence manifest
  of the run it transcribes -- so a hand- or agent-recorded result is legible
  as such rather than passing for harness output;
* entries are shape-checked: known fields only (a misspelled ``pased`` is
  rejected rather than silently read as "not passed"), correct types, and
  ``passed``/``error`` mutually exclusive, since ``_entry_state`` reads
  ``error`` first and ``passed`` second and an entry carrying both is a
  claim whose meaning depends on the reader.

Deliberately NOT enforced here: that a ``passed`` entry also carries
``metric``/``assert``/``trials``. That is a real tightening, but it changes
what counts as a well-formed *entry* rather than what the store says about
its own origin, and the review that asked for this schema scoped it to
provenance and shape. It belongs to whoever revisits ``_entry_state``.
"""

from __future__ import annotations

from substrate.validators.schema import SCHEMA_DIR, validate

_SCHEMA = SCHEMA_DIR / "validation_report.schema.json"

__all__ = ["validation_report_errors", "validate_validation_report"]


def validation_report_errors(report: object) -> list[str]:
    """Every schema violation in ``report``, as human-readable strings.

    A report that is not a JSON object at all (a bare list, a string) is one
    error, not an exception: callers degrade on it exactly as they do on any
    other malformed report.
    """
    if not isinstance(report, dict):
        return [f"<root>: expected a JSON object, got {type(report).__name__}"]
    return validate(report, _SCHEMA)


def validate_validation_report(report: object) -> None:
    errors = validation_report_errors(report)
    if errors:
        raise ValueError(f"invalid validation report: {'; '.join(errors)}")
