"""The `validation/validation-report.json` store has a schema and a provenance
block (review round 3, Critical 2).

Before this, the file was hand-authored, schema-unvalidated and
un-rebuildable: `load_validation` read it with no shape check and
`_entry_state` returned "passed" from a bare truthy `passed` key. Nothing on
disk said the entries were transcribed by a human from a pytest run rather
than emitted by a harness -- and no code in this repository can emit them,
because every FEAT-001 SR is binding-less and `run_requirement_validation`
returns an error entry and exits before measuring for those.

I-10 (derived state is rebuildable) and I-02 (evidence before claim) are both
about being able to say where a number came from. These tests pin that the
file says so itself, in a shape a schema enforces.
"""

from __future__ import annotations

import json

import pytest

from coherence.trace.validation_status import load_validation, report_path
from substrate.paths import factory_root
from substrate.validation.model import validate_validation_report

pytestmark = pytest.mark.unit


_PASSING_ENTRY = {
    "id": "SR-001",
    "metric": "pytest.mark.sr acceptance-criteria pass rate",
    "value": 1.0,
    "assert": "every kind:test_marker acceptance criterion's referenced test passes",
    "passed": True,
    "trials": 1,
    "declared_trials": 1,
    "stale": False,
    "artifacts": ["tests/unit/x.py::test_y"],
}

_GOOD_PROVENANCE = {
    "recorded_by": "hand",
    "recorded_at": "2026-09-01T11:40:28Z",
    "command": 'rtk proxy uv run pytest -m sr -v -o addopts=""',
    "run_id": "T-6-evidence-execution-20260901T114021Z",
    "evidence_manifest": "evidence/runs/T-6-evidence-execution-20260901T114021Z.json",
    "commit": "44d585a5a0898ed52b8aa296b387cac3c948120b",
    "note": "transcribed by hand from the run above; no harness emitted these fields",
}


def _write_report(root, payload) -> None:
    (root / "validation").mkdir(parents=True, exist_ok=True)
    (root / "validation" / "validation-report.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


# --- the repository's own report ---------------------------------------


def test_the_repositorys_validation_report_validates_against_the_schema():
    raw = json.loads(report_path(factory_root()).read_text(encoding="utf-8"))
    validate_validation_report(raw)  # raises ValueError if it does not


def test_the_repositorys_validation_report_says_it_was_recorded_by_an_agent():
    """The whole point of Critical 2, corrected: the entries are faithful,
    but nothing on disk said what actually produced them, and the bootstrap
    feature this run exists to specify will read this file as the reference
    for what evidence looks like. An agent ran the command and transcribed
    the results -- no human did, and no human has attested to them. Pinning
    `recorded_by: "hand"` here would be exactly the false claim of human
    authorship this fix exists to remove, so this test also fails if the
    report ever claims human attribution (`hand`) without a real human
    decision backing it -- checked against the evidence manifest's own
    `decisions` record, since a human decision that happened would show up
    there."""
    root = factory_root()
    raw = json.loads(report_path(root).read_text(encoding="utf-8"))
    provenance = raw["provenance"]
    assert provenance["recorded_by"] == "agent"
    assert "human" not in provenance["note"].lower() or "no human" in provenance["note"].lower()

    manifest_path = root / provenance["evidence_manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if provenance["recorded_by"] == "hand":
        assert manifest.get("decisions"), (
            "provenance claims recorded_by: hand (human attribution) but the "
            "evidence manifest it cites records no human decision"
        )
    else:
        # Matches reality for this run: both human gates (authoring consent,
        # human review) are still open -- no human has acted on this branch.
        assert manifest.get("decisions") == []


def test_the_repositorys_validation_report_cites_the_run_that_produced_it():
    """The two files are the only record of the same event; the validation
    report must point at the evidence manifest carrying the run id, commit
    and per-SR file hashes."""
    root = factory_root()
    raw = json.loads(report_path(root).read_text(encoding="utf-8"))
    provenance = raw["provenance"]
    assert provenance["run_id"] == "T-6-evidence-execution-20260901T114021Z"
    manifest_path = root / provenance["evidence_manifest"]
    assert manifest_path.is_file(), manifest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_id"] == provenance["run_id"]
    assert provenance["commit"] == manifest["result_commit"]
    assert provenance["command"] == manifest["validation"][0]["command"]


# --- the schema itself --------------------------------------------------


def test_a_report_with_no_provenance_is_rejected():
    with pytest.raises(ValueError, match="provenance"):
        validate_validation_report({"requirements": []})


def test_a_report_whose_recorded_by_is_not_hand_or_harness_is_rejected():
    with pytest.raises(ValueError):
        validate_validation_report(
            {"provenance": {**_GOOD_PROVENANCE, "recorded_by": "magic"}, "requirements": []}
        )


def test_a_hand_recorded_report_must_cite_a_run_and_a_manifest():
    minimal = {
        k: v
        for k, v in _GOOD_PROVENANCE.items()
        if k not in ("run_id", "evidence_manifest", "commit")
    }
    with pytest.raises(ValueError):
        validate_validation_report({"provenance": minimal, "requirements": []})


def test_a_harness_emitted_report_need_not_cite_a_run():
    validate_validation_report(
        {
            "provenance": {
                "recorded_by": "harness",
                "recorded_at": "2026-09-01T11:40:28Z",
                "command": "coherence-measurement run",
            },
            "requirements": [],
        }
    )


def test_an_entry_with_a_misspelled_field_is_rejected():
    with pytest.raises(ValueError):
        validate_validation_report(
            {
                "provenance": _GOOD_PROVENANCE,
                "requirements": [{"id": "SR-001", "pased": True}],
            }
        )


def test_an_entry_with_a_non_boolean_passed_is_rejected():
    with pytest.raises(ValueError):
        validate_validation_report(
            {
                "provenance": _GOOD_PROVENANCE,
                "requirements": [{"id": "SR-001", "passed": "yes"}],
            }
        )


def test_an_entry_cannot_both_pass_and_carry_an_error():
    """`_entry_state` reads `error` first and `passed` second, so an entry
    carrying both is a claim whose reading depends on the reader. Rejected."""
    with pytest.raises(ValueError):
        validate_validation_report(
            {
                "provenance": _GOOD_PROVENANCE,
                "requirements": [{"id": "SR-001", "passed": True, "error": "boom"}],
            }
        )


# --- validation on load -------------------------------------------------


def test_load_validation_reports_nothing_for_a_provenance_less_report(tmp_path):
    """Fail-closed: an unvalidatable report yields no statuses at all, so no
    SR can be reported measured-passing out of a store whose shape nothing
    checked. (The navigator surfaces the corruption separately -- see
    `_validation_report_is_corrupt`.)"""
    _write_report(
        tmp_path,
        {"requirements": [_PASSING_ENTRY]},
    )

    assert load_validation(tmp_path) == {}


def test_load_validation_reads_a_provenanced_report(tmp_path):
    _write_report(
        tmp_path,
        {
            "provenance": _GOOD_PROVENANCE,
            "requirements": [_PASSING_ENTRY],
        },
    )

    statuses = load_validation(tmp_path)

    assert statuses["SR-001"].state == "passed"


def test_a_corrupt_report_is_still_visible_to_the_navigator(tmp_path):
    from coherence.navigate.queries import _validation_report_is_corrupt

    _write_report(tmp_path, {"requirements": [{"id": "SR-001", "passed": True}]})

    assert _validation_report_is_corrupt(tmp_path) is True
