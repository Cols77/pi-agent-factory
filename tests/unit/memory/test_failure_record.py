"""Tests for factory.memory.failure_record: FR-* records as structured artifacts.

A failure record carries machine-readable identity in YAML frontmatter
(validated against `failure.schema.json`) and prose in the body. Identity is
the `id` (``FR-...``), never the filename. Every root cause cites evidence or
an ADR; nothing is inferred from prose.

The record is *recorded, never inferred*: `reproduced_by` is a run id /
reproduction task ref, `root_cause` cites evidence or an ADR, and rejected
hypotheses carry their own evidence. A malformed record degrades into
`scope_errors` instead of crashing the set.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from factory.memory.failure_record import (
    DuplicateFailureIdError,
    load_failure,
    load_failures,
)

pytestmark = pytest.mark.unit


def _write_failure(failures_dir: Path, filename: str, text: str) -> Path:
    failures_dir.mkdir(parents=True, exist_ok=True)
    path = failures_dir / filename
    path.write_text(text, encoding="utf-8")
    return path


_WELL_FORMED = """---
id: FR-NAV-0001
title: False re-acquisition after pre-emption handoff
reproduced_by: RUN-20260811-1702
root_cause: "Pre-emption cleared the acquisition latch without re-arming it on resume (ADR-0002, code:navigation/preemption.py)."
fix: "Re-arm the latch in the resume path; regression covered by acceptance test."
regression_link: null
linked_req: [SR-017]
linked_feature: [FEAT-NAV-017]
rejected_hypotheses:
  - hypothesis: "Sensor noise caused the re-acquisition"
    why_rejected: "Replay of RUN-20260811-1702 reproduced it deterministically without noise"
    evidence: "run:RUN-20260811-1702"
---

## Symptom
After a pre-emption handoff the drone re-acquires a target it had already locked.

## Root cause
The acquisition latch is cleared by pre-emption and never re-armed on resume.
"""


def test_well_formed_failure_parses_identity_and_fields(tmp_path):
    path = _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0001.md", _WELL_FORMED)

    rec = load_failure(path)

    assert rec.id == "FR-NAV-0001"
    assert rec.title == "False re-acquisition after pre-emption handoff"
    assert rec.reproduced_by == "RUN-20260811-1702"
    assert "ADR-0002" in rec.root_cause
    assert rec.fix.startswith("Re-arm the latch")
    assert rec.regression_link is None
    assert rec.linked_req == ["SR-017"]
    assert rec.linked_feature == ["FEAT-NAV-017"]
    assert rec.scope_errors == []
    assert rec.rejected_hypotheses == [
        {
            "hypothesis": "Sensor noise caused the re-acquisition",
            "why_rejected": "Replay of RUN-20260811-1702 reproduced it deterministically without noise",
            "evidence": "run:RUN-20260811-1702",
        }
    ]


def test_missing_root_cause_is_reported_not_raised(tmp_path):
    path = _write_failure(
        tmp_path / "docs" / "failures",
        "FR-NAV-0002.md",
        "---\nid: FR-NAV-0002\ntitle: Bad\nfix: x\n---\n\nProse.\n",
    )

    rec = load_failure(path)

    assert rec.id == "FR-NAV-0002"
    assert any("root_cause" in err for err in rec.scope_errors)


def test_absent_frontmatter_yields_scope_errors_and_no_identity(tmp_path):
    path = _write_failure(
        tmp_path / "docs" / "failures",
        "FR-NAV-0003.md",
        "# FR-NAV-0003: Old style\n\n## Root cause\nSomething.\n",
    )

    rec = load_failure(path)

    assert rec.id is None
    assert rec.scope_errors != []


def test_unreadable_file_degrades_to_scope_errors_rather_than_raising(tmp_path):
    missing = tmp_path / "docs" / "failures" / "FR-NAV-0004-absent.md"

    rec = load_failure(missing)

    assert rec.id is None
    assert rec.scope_errors != []


def test_bad_hypothesis_entries_are_reported_in_scope_errors(tmp_path):
    path = _write_failure(
        tmp_path / "docs" / "failures",
        "FR-NAV-0005.md",
        "---\nid: FR-NAV-0005\ntitle: T\nroot_cause: x\nfix: y\nrejected_hypotheses:\n  - hypothesis: \"no evidence field\"\n---\n\nProse.\n",
    )

    rec = load_failure(path)

    assert any("rejected_hypotheses" in err for err in rec.scope_errors)


def test_load_failures_keys_by_id_not_filename(tmp_path):
    failures_dir = tmp_path / "docs" / "failures"
    _write_failure(failures_dir, "renamed-for-readability.md", _WELL_FORMED)

    records = load_failures(tmp_path)

    assert list(records) == ["FR-NAV-0001"]
    assert records["FR-NAV-0001"].path.name == "renamed-for-readability.md"


def test_load_failures_on_absent_directory_is_a_legitimate_empty_state(tmp_path):
    assert load_failures(tmp_path) == {}


def test_duplicate_ids_fail_loudly(tmp_path):
    failures_dir = tmp_path / "docs" / "failures"
    _write_failure(failures_dir, "FR-NAV-0001-a.md", _WELL_FORMED)
    _write_failure(failures_dir, "FR-NAV-0001-b.md", _WELL_FORMED)

    with pytest.raises(DuplicateFailureIdError):
        load_failures(tmp_path)


def test_an_fr_missing_its_frontmatter_is_skipped_by_load_failures(tmp_path):
    failures_dir = tmp_path / "docs" / "failures"
    _write_failure(failures_dir, "FR-NAV-0001.md", _WELL_FORMED)
    _write_failure(
        failures_dir,
        "FR-NAV-0006-legacy.md",
        "# FR-NAV-0006: Old style\n\n## Root cause\nx.\n",
    )

    records = load_failures(tmp_path)

    assert list(records) == ["FR-NAV-0001"]
