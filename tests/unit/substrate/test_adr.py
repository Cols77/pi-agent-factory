from __future__ import annotations

from pathlib import Path

import pytest

from substrate.documents.adr import parse_adr


pytestmark = pytest.mark.unit


def test_substrate_adr_parser_preserves_identity_and_sections(tmp_path: Path):
    path = tmp_path / "docs" / "adr" / "0001-contract.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\n"
        "id: ADR-0001\n"
        "title: Contract spine\n"
        "status: accepted\n"
        "superseded_by: null\n"
        "---\n\n"
        "## Decision\nKeep the typed contract spine.\n",
        encoding="utf-8",
    )

    document = parse_adr(path)

    assert document.id == "ADR-0001"
    assert document.title == "Contract spine"
    assert document.sections == [("Decision", "Keep the typed contract spine.")]
    assert document.schema_errors == []
