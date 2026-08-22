"""Tests for substrate.documents.adr: ADRs as structured artifacts."""
from __future__ import annotations

from pathlib import Path

import pytest

from substrate.documents.adr import DuplicateAdrIdError, load_adrs, parse_adr


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


def test_well_formed_adr_parses_identity_status_and_sections(tmp_path: Path):
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


def test_absent_frontmatter_yields_none_identity_and_reports_it(tmp_path: Path):
    path = _write_adr(
        tmp_path / "docs" / "adr",
        "0009-legacy.md",
        "# ADR-0009: Old Style\n\nStatus: Accepted\n\n## Decision\nSomething.\n",
    )

    doc = parse_adr(path)

    assert doc.id is None
    assert doc.title is None
    assert doc.status is None
    assert doc.schema_errors != []
    assert doc.sections == [("Decision", "Something.")]


def test_schema_violation_is_reported_not_raised(tmp_path: Path):
    path = _write_adr(
        tmp_path / "docs" / "adr",
        "0010-bad-status.md",
        "---\nid: ADR-0010\ntitle: Bad\nstatus: rubbish\n---\n\n## Decision\nx.\n",
    )

    doc = parse_adr(path)

    assert doc.id == "ADR-0010"
    assert any("status" in err for err in doc.schema_errors)


def test_unreadable_file_degrades_to_an_empty_document_rather_than_raising(tmp_path: Path):
    doc = parse_adr(tmp_path / "docs" / "adr" / "0012-absent.md")

    assert doc.id is None
    assert doc.sections == []
    assert doc.schema_errors != []


def test_load_adrs_keys_by_id_and_rejects_duplicates(tmp_path: Path):
    adr_dir = tmp_path / "docs" / "adr"
    _write_adr(adr_dir, "renamed-for-readability.md", _WELL_FORMED)

    assert list(load_adrs(tmp_path)) == ["ADR-0001"]

    _write_adr(adr_dir, "0001-copy.md", _WELL_FORMED)
    with pytest.raises(DuplicateAdrIdError):
        load_adrs(tmp_path)
