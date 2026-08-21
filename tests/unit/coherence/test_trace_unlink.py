from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest

from coherence.trace.cli import main
from coherence.trace.write import unlink_relation


pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _repo(tmp_path: Path) -> Path:
    _write(
        tmp_path / "tasks" / "T-001.md",
        "---\n"
        "id: T-001\n"
        "title: Thing\n"
        "satisfies:\n"
        "  - SR-001\n"
        "  - SR-002\n"
        "upstream: BR-001\n"
        "---\n"
        "\n"
        "# Body\n"
        "\n"
        "Keep these bytes.\n",
    )
    _write(
        tmp_path / "requirements" / "SR-001.md",
        "---\n"
        "id: SR-001\n"
        "title: Requirement\n"
        "upstream: BR-002\n"
        "satisfies: SR-900\n"
        "---\n"
        "\n"
        "Requirement body.\n",
    )
    return tmp_path


def test_unlink_satisfies_preserves_other_relations_order_and_body_bytes(tmp_path):
    root = _repo(tmp_path)
    path = root / "tasks" / "T-001.md"
    original_body = frontmatter.load(str(path)).content.encode("utf-8")

    result = unlink_relation(root, "T-001", satisfies="SR-001")

    assert result == path
    post = frontmatter.load(str(path))
    assert post["satisfies"] == ["SR-002"]
    assert post["upstream"] == "BR-001"
    assert post.content.encode("utf-8") == original_body


def test_unlink_upstream_removes_scalar_without_touching_other_frontmatter_or_body(
    tmp_path,
):
    root = _repo(tmp_path)
    path = root / "requirements" / "SR-001.md"
    original_body = frontmatter.load(str(path)).content.encode("utf-8")

    unlink_relation(root, "SR-001", upstream="BR-002")

    post = frontmatter.load(str(path))
    assert "upstream" not in post.metadata
    assert post["satisfies"] == "SR-900"
    assert post.content.encode("utf-8") == original_body


def test_unlink_relation_preserves_raw_body_bytes(tmp_path):
    root = _repo(tmp_path)
    path = root / "tasks" / "T-001.md"
    body = b"\r\n# Body\r\nKeep these bytes.\x00\r\n"
    path.write_bytes(
        b"---\r\n"
        b"id: T-001\r\n"
        b"title: Thing\r\n"
        b"satisfies:\r\n"
        b"  - SR-001\r\n"
        b"  - SR-002\r\n"
        b"upstream: BR-001\r\n"
        b"---\r\n"
        + body
    )

    unlink_relation(root, "T-001", satisfies="SR-001")

    updated = path.read_bytes()
    closing_delimiter = updated.index(b"---\r\n", 4) + len(b"---\r\n")
    assert updated[closing_delimiter:] == body


@pytest.mark.parametrize(
    "kwargs",
    [{"satisfies": "SR-001", "upstream": "BR-002"}, {}],
)
def test_unlink_relation_requires_exactly_one_relation_kind(tmp_path, kwargs):
    with pytest.raises(ValueError, match="exactly one"):
        unlink_relation(_repo(tmp_path), "T-001", **kwargs)


def test_unlink_relation_rejects_missing_relation_without_writing(tmp_path):
    root = _repo(tmp_path)
    path = root / "tasks" / "T-001.md"
    before = path.read_bytes()

    with pytest.raises(ValueError, match="SR-999"):
        unlink_relation(root, "T-001", satisfies="SR-999")

    assert path.read_bytes() == before


def test_unlink_relation_rejects_missing_node_without_writing_existing_files(tmp_path):
    root = _repo(tmp_path)
    path = root / "tasks" / "T-001.md"
    before = path.read_bytes()

    with pytest.raises(LookupError, match="T-404"):
        unlink_relation(root, "T-404", satisfies="SR-001")

    assert path.read_bytes() == before


def test_unlink_cli_prints_deterministic_result(tmp_path, capsys):
    root = _repo(tmp_path)

    assert main(["unlink", "T-001", "--satisfies", "SR-001", "--project-root", str(root)]) == 0

    assert capsys.readouterr().out == "unlinked satisfies SR-001 from T-001\n"


@pytest.mark.parametrize(
    "args",
    [
        ["unlink", "T-001", "--satisfies", "SR-001", "--upstream", "BR-002"],
        ["unlink", "T-001"],
    ],
)
def test_unlink_cli_rejects_both_or_neither_relation_flags(tmp_path, args):
    with pytest.raises(SystemExit) as exc_info:
        main([*args, "--project-root", str(_repo(tmp_path))])

    assert exc_info.value.code == 2


@pytest.mark.parametrize(
    "args, expected",
    [
        (["T-404", "--satisfies", "SR-001"], "T-404"),
        (["T-001", "--satisfies", "SR-999"], "SR-999"),
    ],
)
def test_unlink_cli_returns_two_and_preserves_bytes_on_missing_target(
    tmp_path, capsys, args, expected
):
    root = _repo(tmp_path)
    path = root / "tasks" / "T-001.md"
    before = path.read_bytes()

    assert main(["unlink", *args, "--project-root", str(root)]) == 2

    assert capsys.readouterr().out == f"error: {'unknown node: ' if expected == 'T-404' else 'relation not found: '}" + expected + "\n"
    assert path.read_bytes() == before


def test_canonical_help_uses_coherence_trace_prog_name(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    assert exc_info.value.code == 0
    assert "usage: coherence-trace" in capsys.readouterr().out
