from __future__ import annotations

from pathlib import Path

import pytest

from coherence.mirrors.generate import (
    MirrorDivergenceError,
    MirrorFormatError,
    check_all,
    regenerate_all,
)
from coherence.mirrors.render import PLACEHOLDER_LINE, render_related_requirements_block

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
    entry).
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

    # Deliberately reintroduce the exact NC-D defect by hand.
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

    # First regeneration adds the marker/fingerprint (the fixture starts out
    # hand-authored, pre-generator, like the real FEAT-018/019/020 today) --
    # the placeholder text itself must survive untouched.
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


def test_missing_heading_raises_a_format_error(tmp_path):
    path = tmp_path / "docs" / "features" / "FEAT-099.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"---\r\nid: FEAT-099\r\ntitle: \"T\"\r\ndescription: d\r\n"
        b"requirements:\r\n  - SR-001\r\n---\r\n\r\n# FEAT-099\r\n\r\nNo heading here.\r\n"
    )

    with pytest.raises(MirrorFormatError):
        regenerate_all(tmp_path)


def test_divergence_error_message_names_the_file_explicitly(tmp_path):
    path = _write_feat(tmp_path, "FEAT-005", ["SR-050"])
    regenerate_all(tmp_path)
    tampered = path.read_bytes().decode("utf-8").replace("- [[SR-050]]", "- [[SR-999]]")
    path.write_bytes(tampered.encode("utf-8"))

    from coherence.mirrors.generate import canonical_requirement_ids, check_file, feature_nodes
    from coherence.trace.graph import build_graph

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
