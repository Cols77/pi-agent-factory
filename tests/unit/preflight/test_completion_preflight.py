from __future__ import annotations

import json

import pytest

from factory.freshness.model import FreshnessSeverity
from factory.orchestrator.ledger import Task
from factory.preflight.checks import Override, apply_override, run_completion_preflight

pytestmark = pytest.mark.unit


def task(tmp_path, satisfies=None):
    return Task(
        "T-001", "Complete", "todo", ["validated"], "body",
        tmp_path / "tasks" / "T-001.md", satisfies or ["SR-001"],
    )


def requirement(tmp_path, *, proposed=False):
    root = tmp_path / "requirements"
    root.mkdir(parents=True, exist_ok=True)
    binding = "" if proposed else """binding:
  harness: sim-testbench
  experiment: exp
  metric: score
  assert: ">= 1"
  trials: 1
"""
    (root / "SR-001.md").write_text(
        f"---\nid: SR-001\ntitle: Requirement\nstatement: It works\ndomain: sim\n{binding}---\n",
        encoding="utf-8",
    )


def write_report(transcript, entries):
    transcript.mkdir(parents=True, exist_ok=True)
    (transcript / "validation-report.json").write_text(
        json.dumps({"requirements": entries}), encoding="utf-8"
    )


def codes(report):
    return {item.code for item in report.issues}


def test_current_passing_validation_allows_completion(tmp_path):
    requirement(tmp_path)
    transcript = tmp_path / "runtime"
    write_report(transcript, [{"id": "SR-001", "passed": True, "stale": False}])
    assert run_completion_preflight(
        tmp_path, task(tmp_path), transcript, require_review=False
    ).ok is True


@pytest.mark.parametrize(
    ("entries", "code"),
    [
        ([], "validation_missing"),
        ([{"id": "SR-001", "passed": False}], "validation_failed"),
        ([{"id": "SR-001", "error": "harness unavailable"}], "validation_failed"),
        ([{"id": "SR-001", "passed": True, "stale": True}], "validation_stale"),
    ],
)
def test_missing_failed_error_and_stale_validation_block(tmp_path, entries, code):
    requirement(tmp_path)
    transcript = tmp_path / "runtime"
    write_report(transcript, entries)
    report = run_completion_preflight(tmp_path, task(tmp_path), transcript, require_review=False)
    assert code in codes(report)
    assert report.ok is False


def test_proposed_requirement_does_not_manufacture_a_validation_result(tmp_path):
    requirement(tmp_path, proposed=True)
    report = run_completion_preflight(
        tmp_path, task(tmp_path), tmp_path / "runtime", require_review=False
    )
    assert report.ok is True
    assert report.issues == []


def test_interactive_run_requires_persisted_review_and_blocks_must_fix(tmp_path):
    requirement(tmp_path, proposed=True)
    transcript = tmp_path / "runtime"
    report = run_completion_preflight(tmp_path, task(tmp_path), transcript, require_review=True)
    assert "review_missing" in codes(report)

    reviews = transcript / "reviews"
    reviews.mkdir(parents=True)
    (reviews / "review-001.json").write_text(json.dumps({
        "decision": "approve",
        "annotations": [{"severity": "must-fix", "body": "fix it"}],
    }), encoding="utf-8")
    report = run_completion_preflight(tmp_path, task(tmp_path), transcript, require_review=True)
    assert "must_fix_unresolved" in codes(report)


def test_override_requires_identity_refuses_integrity_unknown_and_nonoverridable(tmp_path):
    requirement(tmp_path, proposed=True)
    report = run_completion_preflight(
        tmp_path, task(tmp_path), tmp_path / "runtime", require_review=True
    )
    override = Override(["review_missing"], "legacy UI outage", "human@example", "2026-08-07T00:00:00Z")
    overridden = apply_override(report, override)
    assert overridden.ok is True
    assert overridden.issues[0].severity is FreshnessSeverity.WARNING

    with pytest.raises(ValueError, match="unknown"):
        apply_override(report, Override(["not-real"], "why", "actor", "at"))
    with pytest.raises(ValueError, match="blank"):
        apply_override(report, Override(["review_missing"], " ", "actor", "at"))
