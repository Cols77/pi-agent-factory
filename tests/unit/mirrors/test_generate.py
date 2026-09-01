from __future__ import annotations

from pathlib import Path

import pytest

from coherence.mirrors.generate import (
    MirrorDivergenceError,
    canonical_requirement_ids,
    check_all,
    check_file,
    feature_nodes,
    regenerate_all,
)
from coherence.mirrors.render import END_MARKER_LINE, PLACEHOLDER_LINE, render_related_requirements_block
from coherence.trace.graph import build_graph

pytestmark = pytest.mark.unit


def _write_feat(
    root: Path,
    feat_id: str,
    requirement_ids: list[str],
    *,
    embed_first: bool = False,
) -> Path:
    """A hand-authored-looking dossier: correct frontmatter, but a mirror
    written the way a human would have written it before this generator
    existed (plain links, or -- to reproduce NC-D -- an embed on the first
    entry). No end sentinel -- this is the "never generated" bootstrap shape.
    """
    reqs_field = (
        " []"
        if not requirement_ids
        else "\r\n" + "\r\n".join(f"  - {r}" for r in requirement_ids)
    )
    header = (
        "---\r\n"
        f"id: {feat_id}\r\n"
        'title: "Test feature"\r\n'
        "description: a test feature dossier\r\n"
        f"requirements:{reqs_field}\r\n"
        "---\r\n"
        "\r\n"
        f"# {feat_id} — TEST\r\n"
        "\r\n"
        "Status: test fixture.\r\n"
        "\r\n"
        "## Related requirements\r\n"
        "\r\n"
    )
    if not requirement_ids:
        body = PLACEHOLDER_LINE + "\r\n"
    else:
        lines = [
            f"- ![[{r}]]" if embed_first and i == 0 else f"- [[{r}]]"
            for i, r in enumerate(requirement_ids)
        ]
        body = "\r\n".join(lines) + "\r\n"
    path = root / "docs" / "features" / f"{feat_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((header + body).encode("utf-8"))
    return path


def test_regeneration_corrects_a_hand_authored_embed_defect(tmp_path):
    """The exact NC-D shape: FEAT-006 lists SR-019..SR-022, correct
    membership, but its first entry is an Obsidian embed. Regeneration must
    fix it -- not a hand-edit of that one line."""
    path = _write_feat(
        tmp_path, "FEAT-006", ["SR-019", "SR-020", "SR-021", "SR-022"], embed_first=True
    )
    assert "![[SR-019]]" in path.read_bytes().decode("utf-8")

    results = regenerate_all(tmp_path)

    assert [r.feature_id for r in results] == ["FEAT-006"]
    assert results[0].changed is True
    assert results[0].error is None
    text = path.read_bytes().decode("utf-8")
    assert "![[SR-019]]" not in text
    assert "- [[SR-019]]" in text
    assert all(f"- [[SR-0{n}]]" in text for n in (19, 20, 21, 22))
    # Regeneration only touched the block; frontmatter/prose above are intact.
    assert 'title: "Test feature"' in text
    assert "Status: test fixture." in text


def test_check_all_passes_after_regeneration(tmp_path):
    _write_feat(tmp_path, "FEAT-001", ["SR-001", "SR-002"])
    regenerate_all(tmp_path)

    text, code = check_all(tmp_path)

    assert code == 0
    assert "0 divergent" in text


def test_check_all_fails_on_a_hand_edited_block_and_names_the_file(tmp_path):
    path = _write_feat(tmp_path, "FEAT-002", ["SR-010", "SR-011"])
    regenerate_all(tmp_path)
    # Hand-edit the generated block: drop one entry.
    corrupted = path.read_bytes().decode("utf-8").replace("- [[SR-011]]\r\n", "")
    path.write_bytes(corrupted.encode("utf-8"))

    text, code = check_all(tmp_path)

    assert code == 1
    assert "FEAT-002.md" in text
    assert str(path) in text


def test_reintroducing_the_embed_fails_the_check_and_regeneration_restores_it(tmp_path):
    path = _write_feat(
        tmp_path, "FEAT-006", ["SR-019", "SR-020", "SR-021", "SR-022"], embed_first=True
    )
    regenerate_all(tmp_path)
    assert check_all(tmp_path)[1] == 0

    # Deliberately reintroduce the exact NC-D defect by hand (byte-preserving
    # read/write, never a line-ending-rewriting tool like sed -i).
    text = path.read_bytes().decode("utf-8")
    tampered = text.replace("- [[SR-019]]", "- ![[SR-019]]")
    path.write_bytes(tampered.encode("utf-8"))

    fail_text, fail_code = check_all(tmp_path)
    assert fail_code == 1
    assert "FEAT-006.md" in fail_text

    # Restore by regeneration, never by hand-editing the line back.
    regenerate_all(tmp_path)
    pass_text, pass_code = check_all(tmp_path)
    assert pass_code == 0
    assert "![[SR-019]]" not in path.read_bytes().decode("utf-8")


def test_regeneration_is_idempotent_byte_identical_on_the_second_run(tmp_path):
    _write_feat(tmp_path, "FEAT-003", ["SR-030", "SR-031", "SR-032"])

    first = regenerate_all(tmp_path)
    assert first[0].changed is True
    bytes_after_first = (tmp_path / "docs" / "features" / "FEAT-003.md").read_bytes()

    second = regenerate_all(tmp_path)
    assert second[0].changed is False
    bytes_after_second = (tmp_path / "docs" / "features" / "FEAT-003.md").read_bytes()

    assert bytes_after_first == bytes_after_second


def test_regenerating_an_already_correct_file_changes_nothing(tmp_path):
    path = tmp_path / "docs" / "features" / "FEAT-004.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    block = render_related_requirements_block(["SR-040"])
    text = (
        "---\r\nid: FEAT-004\r\ntitle: \"T\"\r\ndescription: d\r\n"
        "requirements:\r\n  - SR-040\r\n---\r\n\r\n# FEAT-004\r\n\r\n" + block
    )
    path.write_bytes(text.encode("utf-8"))
    before = path.read_bytes()

    results = regenerate_all(tmp_path)

    assert results[0].changed is False
    assert path.read_bytes() == before


def test_empty_requirements_regenerates_to_the_exact_placeholder(tmp_path):
    path = _write_feat(tmp_path, "FEAT-018", [])
    before = path.read_bytes()
    assert PLACEHOLDER_LINE.encode("utf-8") in before

    # First regeneration adds the marker/fingerprint/sentinel (the fixture
    # starts out hand-authored, pre-generator, like the real FEAT-018/019/020
    # today) -- the placeholder text itself must survive untouched.
    first = regenerate_all(tmp_path)
    assert first[0].changed is True
    once = path.read_bytes()
    assert PLACEHOLDER_LINE.encode("utf-8") in once
    assert b"- [[" not in once

    # Regenerating an already-derived empty-requirements dossier is a no-op.
    second = regenerate_all(tmp_path)
    assert second[0].changed is False
    assert path.read_bytes() == once


def test_multiple_dossiers_only_the_divergent_one_is_reported(tmp_path):
    good = _write_feat(tmp_path, "FEAT-001", ["SR-001"])
    bad = _write_feat(tmp_path, "FEAT-002", ["SR-002"])
    regenerate_all(tmp_path)
    corrupted = bad.read_bytes().decode("utf-8").replace("- [[SR-002]]", "- [[SR-999]]")
    bad.write_bytes(corrupted.encode("utf-8"))

    text, code = check_all(tmp_path)

    assert code == 1
    assert "FEAT-002.md" in text
    assert "FEAT-001.md" not in text
    assert good.read_bytes()  # untouched, still readable


def test_missing_heading_is_reported_per_file_not_raised(tmp_path):
    path = tmp_path / "docs" / "features" / "FEAT-099.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"---\r\nid: FEAT-099\r\ntitle: \"T\"\r\ndescription: d\r\n"
        b"requirements:\r\n  - SR-001\r\n---\r\n\r\n# FEAT-099\r\n\r\nNo heading here.\r\n"
    )
    before = path.read_bytes()

    results = regenerate_all(tmp_path)

    assert len(results) == 1
    assert results[0].changed is False
    assert results[0].error is not None
    assert "FEAT-099.md" in results[0].error
    # Left completely untouched -- no partial write on a format error.
    assert path.read_bytes() == before


def test_divergence_error_message_names_the_file_explicitly(tmp_path):
    path = _write_feat(tmp_path, "FEAT-005", ["SR-050"])
    regenerate_all(tmp_path)
    tampered = path.read_bytes().decode("utf-8").replace("- [[SR-050]]", "- [[SR-999]]")
    path.write_bytes(tampered.encode("utf-8"))

    graph = build_graph(tmp_path)
    node = feature_nodes(graph)[0]
    with pytest.raises(MirrorDivergenceError) as excinfo:
        check_file(node, canonical_requirement_ids(node, graph))
    assert str(path) in str(excinfo.value)


def test_trailing_prose_after_the_entry_list_is_preserved(tmp_path):
    """FEAT-017.md's real shape: a hand-authored sentence after the entry
    list, inside the same '## Related requirements' section. Regeneration
    must not delete it."""
    path = _write_feat(tmp_path, "FEAT-017", ["SR-043", "SR-044"])
    text = path.read_bytes().decode("utf-8")
    text += "\r\nShared contracts consumed by this feature: [[SR-035]], [[SR-036]].\r\n"
    path.write_bytes(text.encode("utf-8"))

    results = regenerate_all(tmp_path)

    assert results[0].changed is True
    after = path.read_bytes().decode("utf-8")
    assert "Shared contracts consumed by this feature: [[SR-035]], [[SR-036]]." in after
    assert "- [[SR-043]]" in after
    assert "- [[SR-044]]" in after

    # And it is now idempotent / passes the check with that sentence intact.
    assert check_all(tmp_path)[1] == 0
    second = regenerate_all(tmp_path)
    assert second[0].changed is False


# --- Review round 2 regression tests -----------------------------------
#
# Each of the six tests below reproduces one of the review's findings and,
# at the time of that review, failed against the shape-inferring locator.


def test_a_hand_authored_bullet_directly_after_the_entry_list_survives_regeneration(tmp_path):
    """Critical 1. A hand-authored bullet placed *immediately* after the
    entry list, with no blank line separating it, must never be swallowed.
    """
    path = _write_feat(tmp_path, "FEAT-050", ["SR-999"])
    text = path.read_bytes().decode("utf-8")
    assert text.endswith("- [[SR-999]]\r\n")
    text += "- Note: also relates to legacy system X.\r\n"
    path.write_bytes(text.encode("utf-8"))

    results = regenerate_all(tmp_path)

    assert results[0].error is None
    after = path.read_bytes().decode("utf-8")
    assert "- Note: also relates to legacy system X." in after
    assert "- [[SR-999]]" in after
    # And regeneration is stable from here on (idempotent with the sentinel).
    assert check_all(tmp_path)[1] == 0
    assert regenerate_all(tmp_path)[0].changed is False


def test_block_at_eof_with_no_trailing_newline_regenerates_cleanly(tmp_path):
    """Critical 2. A dossier whose file ends exactly at the last entry line,
    with no trailing newline at all, must regenerate without gluing a stale
    entry onto the new block or duplicating anything.
    """
    path = _write_feat(tmp_path, "FEAT-051", ["SR-998"])
    text = path.read_bytes().decode("utf-8")
    assert text.endswith("\r\n")
    no_trailing_newline = text[: -len("\r\n")]  # ends "...- [[SR-998]]" exactly
    path.write_bytes(no_trailing_newline.encode("utf-8"))

    results = regenerate_all(tmp_path)

    assert results[0].error is None
    after = path.read_bytes().decode("utf-8")
    assert after.count("[[SR-998]]") == 1
    assert "SR-999" not in after
    assert after.rstrip("\r\n").endswith(END_MARKER_LINE)
    assert check_all(tmp_path)[1] == 0
    assert regenerate_all(tmp_path)[0].changed is False


def test_an_lf_only_file_is_processed_correctly_and_stays_lf(tmp_path):
    """Important 3 (LF handling). Design choice: an LF-only file is detected
    and processed correctly rather than rejected -- ``_detect_eol`` reads the
    file's own dominant line ending and ``render_related_requirements_block``
    is asked to emit that same ending, so regeneration never silently
    converts a file's line endings as a side effect (which would itself be
    exactly the kind of unrequested rewrite this generator must not do).
    """
    path = _write_feat(tmp_path, "FEAT-052", ["SR-997"])
    lf_text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    path.write_bytes(lf_text.encode("utf-8"))

    results = regenerate_all(tmp_path)

    assert results[0].error is None
    after = path.read_bytes()
    assert b"\r" not in after
    assert b"- [[SR-997]]\n" in after
    assert END_MARKER_LINE.encode("utf-8") in after
    assert check_all(tmp_path)[1] == 0
    assert regenerate_all(tmp_path)[0].changed is False


def test_check_all_reports_a_format_error_per_file_and_keeps_checking_the_rest(tmp_path):
    """Important 4. A malformed dossier must not abort the whole check run --
    files after it must still be processed and reported on."""
    bad = tmp_path / "docs" / "features" / "FEAT-060.md"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(
        b"---\r\nid: FEAT-060\r\ntitle: \"T\"\r\ndescription: d\r\n"
        b"requirements:\r\n  - SR-001\r\n---\r\n\r\n# FEAT-060\r\n\r\nNo heading here.\r\n"
    )
    good = _write_feat(tmp_path, "FEAT-061", ["SR-002"])
    regenerate_all(tmp_path)  # FEAT-061 becomes correctly generated; FEAT-060 stays malformed
    # Corrupt the good one too, so both are expected to report.
    corrupted = good.read_bytes().decode("utf-8").replace("- [[SR-002]]", "- [[SR-999]]")
    good.write_bytes(corrupted.encode("utf-8"))

    text, code = check_all(tmp_path)

    assert code == 1
    assert "FEAT-060.md" in text
    assert "FEAT-061.md" in text


def test_regeneration_is_idempotent_with_the_new_end_sentinel_format(tmp_path):
    """Idempotence explicitly re-verified against the sentinel-carrying block
    format introduced in review round 2."""
    _write_feat(tmp_path, "FEAT-070", ["SR-100", "SR-101"])

    first = regenerate_all(tmp_path)
    assert first[0].changed is True
    once = (tmp_path / "docs" / "features" / "FEAT-070.md").read_bytes()
    assert END_MARKER_LINE.encode("utf-8") in once

    second = regenerate_all(tmp_path)
    assert second[0].changed is False
    twice = (tmp_path / "docs" / "features" / "FEAT-070.md").read_bytes()
    assert once == twice
