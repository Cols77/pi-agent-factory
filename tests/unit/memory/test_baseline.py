"""Milestone baseline records (Increment 6 Task 7).

A `Baseline` is an optional product/high_assurance-only semantic snapshot at
`docs/baselines/BASELINE-*.md`. Structurally parallel to the `FR-*`/`NC-*`
record types: identity is the `id` in YAML frontmatter, never the filename; a
malformed record degrades into `scope_errors` instead of crashing the set; an
absent directory is legitimate (baselines are optional per spec section 4).

Scope refs name the accepted needs/requirements/decisions the snapshot pins,
using the `sr:`/`adr:`/`feat:` prefix vocabulary. This module is the loader
only; `expired_baselines` (Task 7 Step 3, in coherence.trace.suspect) queries
these records against the live graph.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from factory.memory.baseline import DuplicateBaselineIdError, load_baselines

pytestmark = pytest.mark.unit


def _write_baseline(root: Path, filename: str, body: str) -> None:
    (root / "docs" / "baselines").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "baselines" / filename).write_text(body, encoding="utf-8")


def test_no_directory_returns_empty(tmp_path):
    # Baselines are optional: an absent dir is a legitimate state, not an error.
    assert load_baselines(tmp_path) == {}


def test_load_valid_baseline(tmp_path):
    _write_baseline(
        tmp_path,
        "BASELINE-0001.md",
        "---\nid: BASELINE-0001\ntitle: v2 nav freeze\ngit_ref: abc1234\n"
        "scope:\n- sr:SR-001\n- adr:ADR-002\n- feat:FEAT-NAV-017\n"
        "approved_by: jane\n---\nbody\n",
    )
    records = load_baselines(tmp_path)
    bl = records["BASELINE-0001"]
    assert bl.git_ref == "abc1234"
    assert bl.scope == ["sr:SR-001", "adr:ADR-002", "feat:FEAT-NAV-017"]
    assert bl.approved_by == "jane"
    assert bl.scope_errors == []


def test_malformed_record_degrades_to_scope_errors(tmp_path):
    # A malformed record (missing required id/title/git_ref/approved_by) does
    # not crash the load: it degrades to scope_errors like every other record
    # type in this repo.
    _write_baseline(tmp_path, "BASELINE-0002.md", "---\ntitle: no id\n---\nbody\n")
    records = load_baselines(tmp_path)
    assert records == {}  # no id -> not keyed, but load must not crash


def test_valid_but_incomplete_baseline_carries_scope_errors(tmp_path):
    _write_baseline(
        tmp_path,
        "BASELINE-0003.md",
        "---\nid: BASELINE-0003\ntitle: t\ngit_ref: deadbeef\n---\nbody\n",
    )
    records = load_baselines(tmp_path)
    bl = records["BASELINE-0003"]
    assert bl.scope == []
    assert bl.approved_by is None
    # Missing approved_by -> still loaded (id present) but flagged by the schema.
    assert bl.scope_errors  # schema flags the missing required field


def test_duplicate_id_raises(tmp_path):
    _write_baseline(tmp_path, "a.md", "---\nid: BASELINE-0004\ntitle: a\ngit_ref: x\napproved_by: j\n---\n")
    _write_baseline(tmp_path, "b.md", "---\nid: BASELINE-0004\ntitle: b\ngit_ref: y\napproved_by: k\n---\n")
    with pytest.raises(DuplicateBaselineIdError):
        load_baselines(tmp_path)
