"""Tests for substrate.documents.adr: ADRs as structured artifacts.

An ADR carries machine-readable identity in frontmatter and prose in the
body. Identity is the `id`, never the filename, so a file can be renamed
without breaking every bundle that references it.

Ported from tests/unit/system/test_adr.py's coverage of `parse_adr` --
`load_adrs`/`adr_dir`/`DuplicateAdrIdError` stay factory-side (they embed
the `docs/adr` directory convention) and are not re-tested here.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from substrate.documents.adr import parse_adr

pytestmark = pytest.mark.unit


def _write_adr(adr_dir: Path, filename: str, text: str) -> Path:
    adr_dir.mkdir(parents=True, exist_ok=True)
    path = adr_dir / filename
    path.write_text(text, encoding="utf-8")
    return path


_WELL_FORMED = """---
id: ADR-0001
title: Evolve the Existing Packages Through a Typed Contract Spine
status: accepted
superseded_by: null
---

## Decision
Keep `src/drone` and `src/sim`.

## Consequences
No parallel `src/paad` tree exists.
"""


def test_well_formed_adr_parses_identity_status_and_sections(tmp_path):
    path = _write_adr(tmp_path / "docs" / "adr", "0001-contract-spine.md", _WELL_FORMED)

    doc = parse_adr(path)

    assert doc.id == "ADR-0001"
    assert doc.title == "Evolve the Existing Packages Through a Typed Contract Spine"
    assert doc.status == "accepted"
    assert doc.superseded_by is None
    assert doc.schema_errors == []
    assert doc.sections == [
        ("Decision", "Keep `src/drone` and `src/sim`."),
        ("Consequences", "No parallel `src/paad` tree exists."),
    ]


def test_absent_frontmatter_yields_none_identity_and_reports_it(tmp_path):
    path = _write_adr(
        tmp_path / "docs" / "adr",
        "0009-legacy.md",
        "# ADR-0009: Old Style\n\nStatus: Accepted\n\n## Decision\nSomething.\n",
    )

    doc = parse_adr(path)

    # Nothing is recovered from prose: identity is frontmatter or nothing.
    assert doc.id is None
    assert doc.title is None
    assert doc.status is None
    assert doc.schema_errors != []
    # The body still renders -- a bad header does not erase the document.
    assert doc.sections == [("Decision", "Something.")]


def test_schema_violation_is_reported_not_raised(tmp_path):
    path = _write_adr(
        tmp_path / "docs" / "adr",
        "0010-bad-status.md",
        "---\nid: ADR-0010\ntitle: Bad\nstatus: rubbish\n---\n\n## Decision\nx.\n",
    )

    doc = parse_adr(path)

    assert doc.id == "ADR-0010"
    assert any("status" in err for err in doc.schema_errors)


def test_adr_with_no_sections_parses_with_an_empty_section_list(tmp_path):
    path = _write_adr(
        tmp_path / "docs" / "adr",
        "0011-bare.md",
        "---\nid: ADR-0011\ntitle: Bare\nstatus: proposed\n---\n\nJust prose, no headings.\n",
    )

    doc = parse_adr(path)

    assert doc.sections == []


def test_unreadable_file_degrades_to_an_empty_document_rather_than_raising(tmp_path):
    missing = tmp_path / "docs" / "adr" / "0012-absent.md"

    doc = parse_adr(missing)

    assert doc.id is None
    assert doc.sections == []
    assert doc.schema_errors != []
