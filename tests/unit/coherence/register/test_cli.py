from __future__ import annotations

import pytest

from coherence.register.cli import _validation_state

pytestmark = pytest.mark.unit


def _manifest(entries: list[dict]) -> dict:
    return {"validation": [{"requirements": entries}]}


def test_validation_state_of_all_passing_entries_is_passing():
    manifest = _manifest([{"id": "SR-001", "passed": True}, {"id": "SR-001", "passed": True}])
    assert _validation_state([manifest], "SR-001") == "passing"


def test_validation_state_with_a_false_entry_is_still_failing():
    manifest = _manifest([{"id": "SR-001", "passed": True}, {"id": "SR-001", "passed": False}])
    assert _validation_state([manifest], "SR-001") == "failing"


def test_validation_state_of_a_null_entry_mixed_with_passing_entries_is_passing_not_failing():
    # Regression for the audit finding: "not entry['passed']" is True for
    # None too, so a genuinely-unmeasured ("passed": null) entry must not
    # flip an otherwise-passing requirement to "failing".
    manifest = _manifest(
        [
            {"id": "SR-001", "passed": True},
            {"id": "SR-001", "passed": None},
        ]
    )
    assert _validation_state([manifest], "SR-001") == "passing"


def test_validation_state_of_an_all_null_manifest_falls_through_to_an_older_measured_manifest():
    newest = _manifest([{"id": "SR-001", "passed": None}])
    older = _manifest([{"id": "SR-001", "passed": True}])
    # list_run_manifests returns newest-first; an all-null newest manifest
    # must not mask a genuine older measurement as "unknown"/"passing" by
    # accident -- it should be skipped as if it said nothing about SR-001.
    assert _validation_state([newest, older], "SR-001") == "passing"


def test_validation_state_of_an_all_null_manifest_with_nothing_older_is_none():
    manifest = _manifest([{"id": "SR-001", "passed": None}])
    assert _validation_state([manifest], "SR-001") is None
