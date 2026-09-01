"""Explicit, durable gate decisions (Coherence Increment 6, Task 1).

`DecisionFile` is a versioned, atomically-persisted record of an explicit
decision over a gate's items. This module pins the item model, the validation
rules every decision file must satisfy, the atomic store (same-directory temp
+ ``os.replace``), the typed corrupt-file diagnostic, and the `resolve_gate`
short-circuit / blocked contract.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence.gate.model import (
    CorruptDecisionFile,
    Decision,
    DecisionFile,
    DecisionValidationError,
    validate_decisions,
)
from coherence.gate.service import resolve_gate
from coherence.gate.store import decision_path, load_decision, write_decision

pytestmark = pytest.mark.unit


# --- helpers ----------------------------------------------------------------


def _decision(**over) -> Decision:
    base = dict(item_id="coverage:FEAT-001:proposal:SR-001", action="accept")
    base.update(over)
    return Decision(**base)


def _file(**over) -> DecisionFile:
    base = dict(
        gate_id="coverage:FEAT-001",
        artifact_ref="artifact:coverage-reviews/FEAT-001/report.json",
        decisions=(_decision(),),
        decided_at="2026-08-20T00:00:00Z",
        decided_by="human@example.invalid",
    )
    base.update(over)
    return DecisionFile(**base)


def _store_path(run_dir: Path, gate_id: str) -> Path:
    return decision_path(run_dir, gate_id)


def _write_valid(run_dir: Path, f: DecisionFile) -> Path:
    p = _store_path(run_dir, f.gate_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(f.to_dict(), indent=2), encoding="utf-8")
    return p


# --- model: verbatim ISO strings, defaults, schema ---------------------------


def test_decision_file_serializes_verbatim_iso_strings():
    f = _file()
    data = f.to_dict()
    assert data["schema"] == 1
    assert data["decided_at"] == "2026-08-20T00:00:00Z"
    assert data["decisions"][0]["action"] == "accept"


def test_decision_defaults():
    d = Decision(item_id="trace:000", action="accept")
    assert d.reason == ""
    assert d.review_after is None
    assert d.decided_by is None


def test_from_dict_round_trip_preserves_exact_strings():
    f = _file()
    again = DecisionFile.from_dict(f.to_dict())
    assert again == f
    assert again.decided_at == "2026-08-20T00:00:00Z"


# --- validation: empty set, unknown action, item-id prefixes ---------------


def test_empty_decision_set_rejected():
    with pytest.raises(DecisionValidationError):
        validate_decisions(())


def test_unknown_action_rejected():
    with pytest.raises(DecisionValidationError):
        validate_decisions((Decision(item_id="trace:001", action="bogus"),))


def test_unknown_action_rejected_by_file_constructor():
    with pytest.raises(DecisionValidationError):
        _file(decisions=(Decision(item_id="trace:001", action="bogus"),))


def test_non_canonical_item_id_prefix_rejected():
    with pytest.raises(DecisionValidationError):
        validate_decisions((Decision(item_id="unknown:001", action="accept"),))


def test_allowed_trace_prefix_accepted():
    validate_decisions((Decision(item_id="trace:0001", action="accept"),))


def test_allowed_doctor_prefix_accepted():
    validate_decisions((Decision(item_id="doctor:d-1", action="accept"),))


def test_allowed_coverage_proposal_prefix_accepted():
    validate_decisions(
        (Decision(item_id="coverage:FEAT-001:proposal:SR-001", action="accept"),)
    )


def test_allowed_coverage_warning_prefix_accepted():
    validate_decisions(
        (Decision(item_id="coverage:FEAT-001:warning:SR-002", action="accept"),)
    )


def test_allowed_review_prefix_accepted():
    validate_decisions((Decision(item_id="review:7", action="accept"),))


def test_allowed_suspect_prefix_accepted():
    # Its purpose is an inbox critical-edge `accept`: the one policy-authorized
    # action that can restore `valid` (spec section 4, §13 amendment row 3).
    validate_decisions((Decision(item_id="suspect:SR-001", action="accept"),))


def test_allowed_canonical_sr_authoring_consent_item_round_trips():
    decision = Decision(item_id="sr:SR-001", action="accept")
    validate_decisions((decision,))
    file = DecisionFile(
        gate_id="sr:SR-001",
        artifact_ref="artifact:requirements/SR-001.md",
        decisions=(decision,),
        decided_at="2026-09-01T00:00:00Z",
        decided_by="human@example.invalid",
    )
    assert DecisionFile.from_dict(file.to_dict()) == file


# --- validation: accept / reject / defer rules ------------------------------


def test_reject_requires_reason():
    with pytest.raises(DecisionValidationError):
        validate_decisions((Decision("doctor:001", "reject", reason=""),))


def test_defer_requires_reason():
    with pytest.raises(DecisionValidationError):
        validate_decisions((Decision("doctor:001", "defer", reason=""),))


def test_defer_requires_reason_blank_also_rejected():
    with pytest.raises(DecisionValidationError):
        validate_decisions((Decision("doctor:001", "defer", reason="   "),))


def test_accept_may_be_reasonless():
    validate_decisions((Decision("doctor:001", "accept"),))


def test_defer_requires_iso_review_after():
    with pytest.raises(DecisionValidationError):
        validate_decisions((Decision("doctor:001", "defer", reason="later"),))


def test_defer_accepts_iso_review_after():
    validate_decisions(
        (Decision("doctor:001", "defer", reason="later", review_after="2026-09-01T00:00:00Z"),)
    )


def test_defer_rejects_junk_review_after():
    # A defer whose review_after is not a real ISO shape must be refused, not
    # silently persisted (the store's "a file it accepts is always valid"
    # claim depends on _is_iso being a genuine shape check).
    with pytest.raises(DecisionValidationError):
        validate_decisions(
            (Decision("doctor:001", "defer", reason="later", review_after="hello world 123"),)
        )


def test_defer_accepts_date_and_space_separated_iso():
    # Date-only and space-separated ISO forms the repo legitimately stores
    # verbatim are accepted.
    validate_decisions(
        (Decision("doctor:001", "defer", reason="later", review_after="2026-09-01"),)
    )
    validate_decisions(
        (Decision("doctor:001", "defer", reason="later", review_after="2026-09-01 12:00:00+00:00"),)
    )


def test_reject_with_reason_is_valid():
    validate_decisions((Decision("doctor:001", "reject", reason="missing evidence"),))


def test_review_after_ignored_for_accept():
    validate_decisions((Decision("doctor:001", "accept", review_after="2026-09-01T00:00:00Z"),))


# --- validation: duplicates -------------------------------------------------


def test_duplicate_item_ids_rejected():
    with pytest.raises(DecisionValidationError):
        validate_decisions(
            (
                Decision("coverage:FEAT-001:proposal:SR-001", "accept"),
                Decision("coverage:FEAT-001:proposal:SR-001", "reject", reason="dup"),
            )
        )


# --- store: atomic write, validate-before-write -----------------------------


def test_write_decision_creates_file_at_expected_path(tmp_path: Path):
    f = _file()
    p = write_decision(tmp_path, f)
    assert p == _store_path(tmp_path, f.gate_id)
    assert p.is_file()
    assert json.loads(p.read_text(encoding="utf-8"))["schema"] == 1


def test_load_decision_returns_same_decisions(tmp_path: Path):
    f = _file(
        decisions=(
            Decision("coverage:FEAT-001:proposal:SR-001", "accept", reason=""),
            Decision(
                "coverage:FEAT-001:warning:SR-002",
                "defer",
                reason="re-check",
                review_after="2026-09-01T00:00:00Z",
            ),
        )
    )
    p = write_decision(tmp_path, f)
    loaded = load_decision(p)
    assert loaded == f
    assert loaded.schema == 1
    assert [d.reason for d in loaded.decisions] == ["", "re-check"]


def test_write_decision_writes_atomically_no_temp_residue(tmp_path: Path):
    # A valid write leaves no same-directory temporary file behind; the
    # atomic path (temp + os.replace) must never observe a partial file and
    # never leak a residue on success.
    f = _file()
    p = write_decision(tmp_path, f)
    assert p.is_file()
    leftovers = list((tmp_path / "gate-decisions").glob(".*.tmp-*"))
    assert leftovers == []


def test_write_decision_is_always_validated_before_persist(tmp_path: Path):
    # The store re-validates at its boundary (defence-in-depth over
    # construction): a DecisionFile that cannot validate can never be written.
    # Because DecisionFile.__post_init__ already rejects invalid decisions,
    # the honest, reachable assertion is that an invalid decision can never
    # reach the store -- constructing it raises before any path is touched.
    with pytest.raises(DecisionValidationError):
        _file(
            decisions=(
                Decision("coverage:FEAT-001:proposal:SR-001", "defer", reason="x"),  # no review_after
            )
        )
    # And nothing was created on disk by that attempt.
    assert not (tmp_path / "gate-decisions").exists()


def test_write_decision_refuses_invalid_payload_without_touching_existing_file(tmp_path: Path):
    # A store write is strictly validate-before-persist: an invalid payload
    # can never overwrite a prior valid file. We simulate an invalid payload
    # reaching the store boundary (as `write_decision` would receive it only
    # if construction validation were bypassed) and assert the store re-check
    # rejects it and leaves the existing file untouched.
    import os

    good = _file()
    p = write_decision(tmp_path, good)
    original = p.read_text(encoding="utf-8")

    # Build an invalid file that cannot validate (empty decisions), forced past
    # construction only to prove the store boundary also guards.
    invalid = object.__new__(DecisionFile)
    invalid.__dict__.update(
        schema=1,
        gate_id="coverage:FEAT-001",
        artifact_ref="artifact:x",
        decisions=(),
        decided_at="2026-08-20T00:00:00Z",
        decided_by="human",
    )
    with pytest.raises(DecisionValidationError):
        write_decision(tmp_path, invalid)

    # The prior valid file is byte-for-byte untouched; no temp residue.
    assert p.read_text(encoding="utf-8") == original
    leftovers = list((tmp_path / "gate-decisions").glob(".*.tmp-*"))
    assert leftovers == []
    assert os.path.exists(p)


def test_load_missing_file_raises_typed_error(tmp_path: Path):
    with pytest.raises(CorruptDecisionFile):
        load_decision(_store_path(tmp_path, "does-not-exist"))


def test_load_advance(tmp_path: Path):
    f = _file()
    p = _write_valid(tmp_path, f)
    assert load_decision(p).gate_id == f.gate_id


# --- store: corrupt file typing ---------------------------------------------


def test_load_corrupt_json_raises_typed_diagnostic(tmp_path: Path):
    p = _store_path(tmp_path, "coverage:FEAT-001")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ not json", encoding="utf-8")
    with pytest.raises(CorruptDecisionFile):
        load_decision(p)


def test_load_wrong_shape_raises_typed_diagnostic(tmp_path: Path):
    p = _store_path(tmp_path, "coverage:FEAT-001")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"not": "a file"}), encoding="utf-8")
    with pytest.raises(CorruptDecisionFile):
        load_decision(p)


def test_corrupt_file_never_degrades_to_empty_dict(tmp_path: Path):
    # The store must surface a typed diagnostic, not a silent {} / empty set.
    p = _store_path(tmp_path, "coverage:FEAT-001")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("definitely not json", encoding="utf-8")
    with pytest.raises(CorruptDecisionFile):
        load_decision(p)


# --- resolve_gate contract --------------------------------------------------


def test_resolve_gate_short_circuits_existing_file(tmp_path: Path):
    f = _file(decisions=(Decision("coverage:FEAT-001:proposal:SR-001", "accept"),))
    write_decision(tmp_path, f)
    assert resolve_gate(tmp_path, f.gate_id, unattended=False) == "accept"


def test_resolve_gate_defer_reads_lowest_non_accept(tmp_path: Path):
    f = _file(
        decisions=(
            Decision("coverage:FEAT-001:proposal:SR-001", "accept"),
            Decision("coverage:FEAT-001:warning:SR-002", "reject", reason="x"),
        )
    )
    write_decision(tmp_path, f)
    assert resolve_gate(tmp_path, f.gate_id, unattended=False) == "reject"


def test_resolve_gate_precedence_reject_over_defer(tmp_path: Path):
    # reject blocks the gate outright even when a defer is present.
    f = _file(
        decisions=(
            Decision(
                "coverage:FEAT-001:warning:SR-001",
                "defer",
                reason="later",
                review_after="2026-09-01",
            ),
            Decision("coverage:FEAT-001:proposal:SR-002", "reject", reason="fails"),
        )
    )
    write_decision(tmp_path, f)
    assert resolve_gate(tmp_path, f.gate_id, unattended=False) == "reject"


def test_resolve_gate_returns_defer_when_only_defer(tmp_path: Path):
    # The defer branch of _resolved_action: a decision set containing ONLY
    # defer (no reject) resolves to "defer".
    f = _file(
        decisions=(
            Decision(
                "coverage:FEAT-001:warning:SR-002",
                "defer",
                reason="re-check",
                review_after="2026-09-01T00:00:00Z",
            ),
        )
    )
    write_decision(tmp_path, f)
    assert resolve_gate(tmp_path, f.gate_id, unattended=False) == "defer"


def test_resolve_gate_unattended_without_file_returns_blocked(tmp_path: Path):
    assert resolve_gate(tmp_path, "coverage:FEAT-999", unattended=True) == "blocked"


def test_resolve_gate_no_file_returns_none_for_caller(tmp_path: Path):
    assert resolve_gate(tmp_path, "coverage:FEAT-999", unattended=False) is None


def test_resolve_gate_missing_file_ignored_then_blocked(tmp_path: Path):
    assert resolve_gate(tmp_path, "coverage:FEAT-999", unattended=True) == "blocked"


# --- decision_path layout ---------------------------------------------------


def test_decision_path_is_under_gate_decisions(tmp_path: Path):
    assert _store_path(tmp_path, "coverage:FEAT-001") == (
        tmp_path / "gate-decisions" / "coverage-FEAT-001.json"
    )


def test_decision_path_keeps_gate_id_in_safe_filename(tmp_path: Path):
    # The filename must be windows-safe (no colon); the canonical gate id is
    # preserved verbatim inside the JSON payload for round-trip.
    assert _store_path(tmp_path, "coverage:FEAT-001").name == "coverage-FEAT-001.json"
    assert _store_path(tmp_path, "review:7").name == "review-7.json"