from __future__ import annotations

import pytest

from coherence.mirrors.render import (
    END_MARKER_LINE,
    HEADING,
    MARKER_LINE,
    PLACEHOLDER_LINE,
    fingerprint_requirements,
    render_related_requirements_block,
)

pytestmark = pytest.mark.unit


def test_render_lists_entries_as_plain_links_in_frontmatter_order():
    block = render_related_requirements_block(["SR-020", "SR-019", "SR-021"])

    lines = block.split("\r\n")
    assert lines[0] == HEADING
    assert lines[1] == ""
    assert lines[2] == MARKER_LINE
    assert lines[3].startswith("<!-- fingerprint: sha256:")
    assert lines[4:7] == ["- [[SR-020]]", "- [[SR-019]]", "- [[SR-021]]"]
    assert lines[7] == END_MARKER_LINE
    # No trailing blank line; exactly one trailing CRLF.
    assert lines[8] == ""
    assert len(lines) == 9


def test_render_never_emits_an_embed():
    block = render_related_requirements_block(["SR-019"])

    assert "![[SR-019]]" not in block
    assert "- [[SR-019]]" in block


def test_render_uses_crlf_by_default():
    block = render_related_requirements_block(["SR-001"])

    assert "\r\n" in block
    # Every bare \n must be preceded by \r -- no bare LF anywhere.
    assert block.count("\n") == block.count("\r\n")


def test_render_honours_an_explicit_lf_eol():
    block = render_related_requirements_block(["SR-001", "SR-002"], eol="\n")

    assert "\r" not in block
    lines = block.split("\n")
    assert lines[0] == HEADING
    assert lines[-2] == END_MARKER_LINE
    assert lines[-1] == ""


def test_render_empty_requirements_reproduces_the_exact_placeholder():
    block = render_related_requirements_block([])

    assert PLACEHOLDER_LINE in block
    assert "- [[" not in block
    # The placeholder line is immediately followed by the end sentinel.
    assert (PLACEHOLDER_LINE + "\r\n" + END_MARKER_LINE) in block


def test_render_ends_with_the_end_sentinel():
    block = render_related_requirements_block(["SR-001"])

    assert block.endswith(END_MARKER_LINE + "\r\n")


def test_render_is_a_pure_function_of_its_input():
    ids = ["SR-020", "SR-021", "SR-022"]

    assert render_related_requirements_block(ids) == render_related_requirements_block(list(ids))


def test_fingerprint_is_order_sensitive():
    assert fingerprint_requirements(["SR-001", "SR-002"]) != fingerprint_requirements(
        ["SR-002", "SR-001"]
    )


def test_fingerprint_is_deterministic():
    ids = ["SR-001", "SR-002"]

    assert fingerprint_requirements(ids) == fingerprint_requirements(list(ids))


def test_fingerprint_uses_the_shared_sha256_scheme():
    from substrate.freshness.fingerprint import sha256_bytes

    assert fingerprint_requirements(["SR-001"]).startswith("sha256:")
    assert sha256_bytes(b"x").startswith("sha256:")


def test_marker_line_says_derived_do_not_edit():
    assert "derived" in MARKER_LINE
    assert "do not edit" in MARKER_LINE


def test_end_marker_line_is_distinct_from_the_start_marker():
    assert END_MARKER_LINE != MARKER_LINE
    assert "end derived" in END_MARKER_LINE
